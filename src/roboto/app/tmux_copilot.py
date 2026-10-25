"""Co-piloto via **tmux + Claude Code CLI** (trilha O).

Alternativa ao driver via SDK (`copilot.drive_session`): aqui o motor roda como **CLI interativo
numa tmux POR-RUN**. Ganhos: o terminal web (ttyd) **anexa nessa tmux** e você vê/opera a sessão
REAL; o chat do cockpit injeta as mensagens por `tmux send-keys` (chat manda, terminal espelha).

Mantém a MESMA interface do SDK (`LiveSession`/`SessionHub`) — o console não muda. O feed ao vivo é
alimentado pelo **transcript JSONL** que o CLI grava (`~/.claude/projects/<cwd>/<session>.jsonl`),
parseado em `session_event` (message/tool_call). Pré-requisitos semeados no entrypoint (onboarding,
trust do projeto, skip do bypass) + launch sem `ANTHROPIC_API_KEY` (evita o prompt da chave).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from roboto.app.session_hub import SessionHub
from roboto.orchestrator.model import Engine, Run
from roboto.orchestrator.store import Store

# ferramentas de escrita/execução bloqueadas no refino (read-only) — espelha o copilot via SDK
_READ_ONLY_BLOCKED = ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash")


@dataclass
class _Activity:
    """Estado compartilhado tailer↔watchdog p/ os limites de custo/recurso (Fix 2)."""

    last: float  # epoch da última atividade do motor (nova linha no transcript)
    tools: int = 0  # tool-calls desde a última mensagem do humano (cap de burst)


def session_name(run_id: int) -> str:
    """Nome da tmux por-run; é também o `?arg=` que o ttyd usa p/ anexar o terminal."""
    return f"roboto-run-{run_id}"


def _transcript_dir(workdir: str) -> Path:
    # o CLI grava o transcript em ~/.claude/projects/<workdir com '/' e '.' virando '-'>
    mangled = workdir.replace("/", "-").replace(".", "-")
    return Path.home() / ".claude" / "projects" / mangled


def _one_line(text: str) -> str:
    # o REPL submete a cada newline; colapsa p/ UMA linha (o contexto grande vira linha só — o motor
    # ainda lê o repo pra fundamentar). Evita múltiplos "Enter" partindo a mensagem.
    return " ".join(text.replace("\r", " ").split("\n")).strip()


async def _tmux(*args: str) -> int:
    proc = await asyncio.create_subprocess_exec(
        "tmux", *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()
    return proc.returncode or 0


async def _alive(name: str) -> bool:
    return await _tmux("has-session", "-t", name) == 0


async def _start(name: str, workdir: str, *, read_only: bool, code_intel: bool) -> None:
    await _tmux("kill-session", "-t", name)  # limpa resíduo de um run anterior
    base = os.environ.get("ANTHROPIC_BASE_URL", "http://127.0.0.1:3456")
    token = os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get(
        "ANTHROPIC_API_KEY", "sk-ccr-noop"
    )
    flags = "--permission-mode bypassPermissions"
    if read_only:
        flags += " --disallowedTools " + " ".join(_READ_ONLY_BLOCKED)
    if code_intel:
        # busca semântica (symbols/refs) em vez de ler arquivo inteiro → economia de token (F).
        cfg = '{"mcpServers":{"code-intel":{"command":"code-intel-mcp"}}}'
        flags += f" --mcp-config '{cfg}'"
    # env -u ANTHROPIC_API_KEY: sem a chave "custom" o CLI não para no prompt de aprovação da key;
    # AUTH_TOKEN + base_url bastam p/ o ccr rotear (validado no spike).
    cmd = (
        f"cd {workdir} && env -u ANTHROPIC_API_KEY "
        f"ANTHROPIC_BASE_URL={base} ANTHROPIC_AUTH_TOKEN={token} "
        f"claude {flags}"
    )
    await _tmux("new-session", "-d", "-s", name, "-x", "220", "-y", "50", cmd)


async def _send(name: str, text: str) -> None:
    # texto literal e, num 2º comando, o Enter (casa com o fluxo validado no spike)
    await _tmux("send-keys", "-t", name, "-l", _one_line(text))
    await asyncio.sleep(0.2)
    await _tmux("send-keys", "-t", name, "Enter")


async def _tail_transcript(
    store: Store,
    run: Run,
    workdir: str,
    now: Callable[[], datetime],
    *,
    stop: asyncio.Event,
    since: float,
    activity: _Activity,
) -> None:
    """Acha o transcript desta sessão (jsonl mais novo no dir do projeto após o start) e faz tail,
    convertendo `assistant` (text/tool_use) em `session_event` — é o que alimenta o feed ao vivo."""
    d = _transcript_dir(workdir)
    path: Path | None = None
    for _ in range(90):  # espera o arquivo nascer (REPL subindo + 1ª resposta)
        if stop.is_set():
            return
        if d.exists():
            cands = [p for p in d.glob("*.jsonl") if p.stat().st_mtime >= since - 2]
            if cands:
                path = max(cands, key=lambda p: p.stat().st_mtime)
                break
        await asyncio.sleep(1)
    if path is None:
        return
    # o nome do arquivo É a sessão nativa (D23) — mapeia de uma vez
    await _map_native(store, run, now, path.stem)
    pos = 0
    while not stop.is_set():
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            await asyncio.sleep(1)
            continue
        for ln in lines[pos:]:
            await _emit_line(store, run, now, ln, activity)
        pos = len(lines)
        await asyncio.sleep(1)


async def _map_native(
    store: Store, run: Run, now: Callable[[], datetime], native: str
) -> None:
    if not native:
        return
    session = await store.create_session(run.tenant, run.id, Engine.CLAUDE_CODE, now())
    await store.set_native_session(session.id, native, now())


async def _emit_line(
    store: Store, run: Run, now: Callable[[], datetime], line: str, activity: _Activity
) -> None:
    try:
        e = json.loads(line)
    except ValueError:
        return
    msg = e.get("message") if isinstance(e.get("message"), dict) else None
    # só `assistant`: as mensagens do humano o console já persiste como kind="user" (sem duplicar)
    if e.get("type") != "assistant" or msg is None:
        return
    activity.last = time.time()  # o motor produziu algo → reseta o relógio de idle
    for b in msg.get("content") or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and str(b.get("text", "")).strip():
            await store.append_session_event(
                run.tenant, run.id, "message", now(), text=str(b["text"])
            )
        elif b.get("type") == "tool_use":
            await store.append_session_event(
                run.tenant, run.id, "tool_call", now(), tool=str(b.get("name", ""))
            )
            activity.tools += 1  # conta o burst p/ o cap de turnos


async def drive_session_tmux(
    store: Store,
    hub: SessionHub,
    *,
    run: Run,
    chat_id: str,
    workdir: str,
    now: Callable[[], datetime],
    read_only: bool = False,
    code_intel: bool = False,
    initial_prompt: str | None = None,
) -> None:
    """Sobe o CLI na tmux por-run, injeta a 1ª mensagem e depois faz steer das próximas (via hub).
    Interromper → Escape; encerrar → mata a tmux. Espelha a estrutura de `copilot.drive_session`."""
    live = hub.get(run.id) or hub.open(run.id)
    name = session_name(run.id)
    stop = asyncio.Event()
    since = time.time()  # mesma base (epoch) que o st_mtime do transcript — evita viés de timezone
    activity = _Activity(last=since)
    # limites de custo/recurso (Fix 2): env com defaults seguros. O CLI interativo não tem
    # --max-turns, então o cap de "burst" é imposto por fora (Escape); o idle/vida matam a sessão.
    idle_ttl = float(os.environ.get("COPILOT_IDLE_SECONDS", "900"))  # 15 min sem atividade → mata
    max_life = float(os.environ.get("COPILOT_MAX_LIFETIME_SECONDS", "3600"))  # 1 h → mata
    max_tools = int(os.environ.get("COPILOT_MAX_TOOLS_PER_TURN", "60"))  # burst → Escape
    try:
        await _start(name, workdir, read_only=read_only, code_intel=code_intel)
        tailer = asyncio.create_task(
            _tail_transcript(store, run, workdir, now, stop=stop, since=since, activity=activity)
        )
        await asyncio.sleep(4)  # deixa o REPL subir antes do 1º texto
        prompt = initial_prompt or f"Trabalhe a issue {run.issue_id} do repo {run.repo}."
        await _send(name, prompt)
        activity.last = time.time()
        activity.tools = 0

        # controles imediatos: interromper manda Escape; encerrar sai do laço
        async def _controls() -> None:
            while True:
                await live.wait_control()
                await _tmux("send-keys", "-t", name, "Escape")
                if live.ended:
                    return
                live.clear_interrupt()

        # watchdog de limites: mata por idle/vida; corta burst de tool-calls com Escape (token).
        async def _limits() -> None:
            while not stop.is_set():
                await asyncio.sleep(5)
                t = time.time()
                if t - since > max_life or (t - activity.last > idle_ttl and not live.has_input()):
                    live.request_end()  # tear-down limpo pela máquina existente (next_input→None)
                    return
                if activity.tools > max_tools:
                    await _tmux("send-keys", "-t", name, "Escape")  # corta o "faz coisa demais"
                    activity.tools = 0

        watcher = asyncio.create_task(_controls())
        limiter = asyncio.create_task(_limits())
        try:
            while True:
                nxt = await live.next_input()  # próxima msg do humano; None = encerrar
                if nxt is None or not await _alive(name):
                    break
                await _send(name, nxt)
                activity.last = time.time()
                activity.tools = 0  # nova mensagem do humano reinicia o cap de burst
        finally:
            watcher.cancel()
            limiter.cancel()
            tailer.cancel()
    finally:
        stop.set()
        await _tmux("kill-session", "-t", name)
        hub.close(run.id)
