"""Verify determinístico shift-left: pergunta ao code-intel (tsgo, SEM script) quais erros de tipo
a mudança do motor introduziu — ANTES de abrir o PR (anota no corpo; não bloqueia, D7/decisão).

Truque sem mutar o disco: `simulate_edit(file, new_content=<versão BASE>)` roda em memória e volta;
o campo `errors_resolved` = erros que a versão ATUAL (do motor) tem e a base não = os introduzidos.
Tudo best-effort: qualquer falha vira "verify indisponível" e o ciclo segue.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field

# só arquivos que o tsgo analisa; o resto do diff é ignorado pelo verify.
_EXT_TS = (".ts", ".tsx", ".mts", ".cts")


@dataclass(frozen=True)
class VerifyResult:
    disponivel: bool  # o code-intel respondeu?
    introduzidos: list[str] = field(default_factory=list)  # "arquivo:linha msg"
    detalhe: str = ""  # motivo quando indisponível

    @property
    def ok(self) -> bool:
        return self.disponivel and not self.introduzidos


def arquivos_ts(paths: list[str]) -> list[str]:
    return [p for p in paths if p.endswith(_EXT_TS)]


def _introduzidos_de(resultado: dict) -> list[str]:
    """Extrai os erros introduzidos de um resultado de simulate_edit (new_content=base)."""
    return [str(e) for e in resultado.get("errors_resolved", []) if e]


def secao_verify(r: VerifyResult) -> str:
    """Bloco markdown pro corpo do PR (modo anota-e-segue)."""
    if not r.disponivel:
        return f"## Verify (code-intel)\n_indisponível: {r.detalhe}_"
    if not r.introduzidos:
        return "## Verify (code-intel · tsgo)\n✅ a mudança não introduz novos erros de tipo."
    linhas = "\n".join(f"- `{e}`" for e in r.introduzidos[:30])
    extra = "" if len(r.introduzidos) <= 30 else f"\n- _(+{len(r.introduzidos) - 30} outros)_"
    return (
        f"## Verify (code-intel · tsgo)\n"
        f"⚠️ **{len(r.introduzidos)} novo(s) erro(s) de tipo** introduzido(s) pela mudança:\n"
        f"{linhas}{extra}"
    )


class _McpClient:
    """Cliente MCP stdio mínimo (JSON-RPC por linha) só p/ o simulate_edit do code-intel."""

    def __init__(self, cmd: str, cwd: str) -> None:
        self._p = subprocess.Popen(  # noqa: S603 — cmd é config do fleet, não input do modelo
            [cmd], cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        self._id = 0

    def _send(self, obj: dict) -> None:
        assert self._p.stdin is not None
        self._p.stdin.write(json.dumps(obj) + "\n")
        self._p.stdin.flush()

    def _read(self, id_alvo: int, timeout: float) -> dict | None:
        assert self._p.stdout is not None
        fim = time.monotonic() + timeout
        while time.monotonic() < fim:
            linha = self._p.stdout.readline()
            if not linha:
                return None
            linha = linha.strip()
            if not linha.startswith("{"):
                continue
            try:
                msg = json.loads(linha)
            except ValueError:
                continue
            if msg.get("id") == id_alvo:
                return msg
        return None

    def handshake(self, timeout: float) -> bool:
        self._id += 1
        self._send({
            "jsonrpc": "2.0", "id": self._id, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "roboto-verify", "version": "0"}},
        })
        if self._read(self._id, timeout) is None:
            return False
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return True

    def simulate_edit(self, project: str, file: str, new_content: str, timeout: float) -> dict:
        self._id += 1
        self._send({
            "jsonrpc": "2.0", "id": self._id, "method": "tools/call",
            "params": {"name": "simulate_edit",
                       "arguments": {"project": project, "file": file, "new_content": new_content}},
        })
        msg = self._read(self._id, timeout) or {}
        blocos = msg.get("result", {}).get("content", [])
        texto = " ".join(b.get("text", "") for b in blocos if isinstance(b, dict))
        try:
            return json.loads(texto)
        except ValueError:
            return {}

    def close(self) -> None:
        try:
            if self._p.stdin:
                self._p.stdin.close()
            self._p.wait(timeout=5)
        except Exception:  # noqa: BLE001 — encerramento best-effort
            self._p.kill()


def verificar(
    project: str,
    pares: list[tuple[str, str]],  # (arquivo_rel, conteúdo_na_base)
    *,
    cmd: str = "code-intel-mcp",
    timeout: float = 120.0,
) -> VerifyResult:
    """Roda o verify via code-intel; SÍNCRONO (chame com asyncio.to_thread). Nunca levanta."""
    if not pares:
        return VerifyResult(True, [])
    cli = None
    try:
        cli = _McpClient(cmd, project)
        if not cli.handshake(timeout=30.0):
            return VerifyResult(False, detalhe="handshake do code-intel falhou")
        introduzidos: list[str] = []
        for arquivo, base in pares:
            res = cli.simulate_edit(project, arquivo, base, timeout=timeout)
            introduzidos.extend(_introduzidos_de(res))
        return VerifyResult(True, introduzidos)
    except Exception as exc:  # noqa: BLE001 — verify é best-effort; falha não derruba o ciclo
        return VerifyResult(False, detalhe=f"{type(exc).__name__}: {exc}"[:200])
    finally:
        if cli is not None:
            cli.close()
