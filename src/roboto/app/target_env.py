"""Prepara o ambiente de teste do repo-ALVO lendo o CI DELE (harness-first, determinismo 1º).

Resiliência (pedido do dono): em vez de CHUTAR "infra" e pular o teste, o fleet LÊ o workflow de
CI do alvo (`.github/workflows/*.yml`) e aprende, do próprio repo:
- o **env** que os testes usam (`DATABASE_URL`, `REDIS_URL`, …);
- os **services** que o CI sobe (postgres/redis) — só p/ mensagem honesta de "o que faltou";
- os comandos de **setup** (`db:generate`/`db:migrate`) via `package.json`.

Com isso, o `repo_ci` aplica o que consegue localmente e **re-roda** o teste — o resultado REAL
decide (não um regex): verde = validado de verdade; vermelho de código = realimenta o motor; só
degrada p/ "indisponível" (honesto, nomeando o serviço) se nem subindo o ambiente resolver.

Tudo PURO/injetável (parser testável em tier-1; a execução dos comandos fica no `repo_ci`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# scripts de package.json que PREPARAM o ambiente de teste, em ordem canônica (gerar client do ORM
# → migrar schema → push/deploy → seed). É o que o CI roda antes do `test` (ver ci.yml do alvo).
_SETUP_FAMILY = (
    "db:generate", "generate", "db:migrate", "migrate", "db:push",
    "prisma:migrate", "db:deploy", "db:seed", "seed", "setup:test", "test:setup",
)
_SETUP_ORDER = {name: i for i, name in enumerate(_SETUP_FAMILY)}


@dataclass(frozen=True)
class CiService:
    """Um serviço que o CI do alvo sobe (ex.: postgres/redis) — p/ provisionar efêmero por-run."""

    name: str  # nome do serviço no workflow (postgres, redis…)
    image: str  # imagem docker (postgres:18, redis:8…)
    env: dict[str, str] = field(default_factory=dict)  # env do serviço (POSTGRES_USER…)


def parse_ci_services(text: str) -> list[CiService]:
    """Extrai os `services:` do workflow com imagem + env (p/ `docker run` por-run). Puro/testável.
    Ignora serviços sem `image` e valores dinâmicos `${{ … }}`."""
    try:
        import yaml  # lazy: sem pyyaml, degrada p/ vazio

        doc: Any = yaml.safe_load(text)
    except Exception:  # noqa: BLE001 — YAML inválido/sem lib → sem serviços
        return []
    if not isinstance(doc, dict):
        return []
    out: dict[str, CiService] = {}
    for job in (doc.get("jobs") or {}).values() if isinstance(doc.get("jobs"), dict) else []:
        services = job.get("services") if isinstance(job, dict) else None
        for name, spec in (services or {}).items() if isinstance(services, dict) else []:
            if not isinstance(spec, dict) or not spec.get("image"):
                continue
            senv = {
                k: str(v) for k, v in (spec.get("env") or {}).items()
                if isinstance(v, (str, int)) and "${{" not in str(v)
            }
            out.setdefault(str(name), CiService(str(name), str(spec["image"]), senv))
    return list(out.values())


@dataclass(frozen=True)
class TargetEnv:
    """Receita de ambiente de teste extraída do repo-alvo (vazio = nada a preparar; no-op)."""

    env: dict[str, str] = field(default_factory=dict)  # vars que os testes/ setup usam
    services: tuple[str, ...] = ()  # nomes de serviços do CI (postgres/redis) — p/ msg honesta
    setup: tuple[tuple[str, str], ...] = ()  # (nome, cmd) de setup, em ordem canônica


def _workflow_paths(workdir: str) -> list[Path]:
    """Workflows de CI do alvo, `ci*` primeiro (o de PR), depois o resto. Sem dir → vazio."""
    wf = Path(workdir) / ".github" / "workflows"
    if not wf.is_dir():
        return []
    files = [*wf.glob("*.yml"), *wf.glob("*.yaml")]
    # ci.yml tem prioridade (é o workflow de PR); e2e/deploy/etc vêm depois só p/ completar env.
    files.sort(key=lambda p: (0 if p.stem.startswith("ci") else 1, p.name))
    return files


def parse_ci_env(text: str) -> tuple[dict[str, str], tuple[str, ...]]:
    """Extrai o `env:` (nível de job) + os nomes de `services:` do YAML do workflow. Puro/testável.

    Só pega valores escalares (ignora `${{ secrets.X }}` dinâmicos — inúteis localmente). Falha de
    parse (ou pyyaml ausente) → vazio (best-effort: um workflow exótico não derruba o ciclo)."""
    try:
        import yaml  # lazy: sem pyyaml, o ImportError cai no except e degrada p/ vazio

        doc: Any = yaml.safe_load(text)
    except Exception:  # noqa: BLE001 — YAML inválido/exótico/sem lib → sem env (degrada normal)
        return {}, ()
    if not isinstance(doc, dict):
        return {}, ()
    env: dict[str, str] = {}
    services: list[str] = []
    jobs = doc.get("jobs")
    for job in jobs.values() if isinstance(jobs, dict) else []:
        if not isinstance(job, dict):
            continue
        job_env = job.get("env")
        if isinstance(job_env, dict):
            for k, v in job_env.items():
                # pula valores dinâmicos do GitHub (`${{ ... }}`): não resolvem localmente.
                if isinstance(v, (str, int)) and "${{" not in str(v) and k not in env:
                    env[k] = str(v)
        job_services = job.get("services")
        if isinstance(job_services, dict):
            for sname in job_services:
                if sname not in services:
                    services.append(str(sname))
    return env, tuple(services)


def discover_setup_commands(workdir: str) -> tuple[tuple[str, str], ...]:
    """Scripts de setup de ambiente de teste do `package.json` raiz, em ordem canônica. Puro.

    Como `repo_ci.discover_ci_commands`: roda via `pnpm -s <script>` (= o que o CI roda via turbo).
    Sem package.json legível ou sem scripts de setup → vazia (nada a preparar)."""
    try:
        pkg = json.loads((Path(workdir) / "package.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — sem package.json legível → nada a preparar
        return ()
    scripts = pkg.get("scripts", {}) if isinstance(pkg, dict) else {}
    found = sorted((n for n in scripts if n in _SETUP_ORDER), key=lambda n: _SETUP_ORDER[n])
    return tuple((n, f"pnpm -s {n}") for n in found)


def read_target_services(workdir: str) -> list[CiService]:
    """Serviços (postgres/redis…) declarados nos workflows do alvo — p/ provisionar efêmero por-run.
    Junta de todos os workflows; o 1º a declarar um nome vence. Vazio se não houver."""
    out: dict[str, CiService] = {}
    for p in _workflow_paths(workdir):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        for s in parse_ci_services(text):
            out.setdefault(s.name, s)
    return list(out.values())


def read_target_env(workdir: str) -> TargetEnv:
    """Lê o CI do alvo + `package.json` e monta o `TargetEnv` (best-effort; vazio = no-op).

    Junta o `env:` de todos os workflows (o 1º a definir uma chave vence — `ci*` tem prioridade) e
    pega os `services:` do 1º workflow que os declara."""
    env: dict[str, str] = {}
    services: tuple[str, ...] = ()
    for p in _workflow_paths(workdir):
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001 — arquivo ilegível → pula
            continue
        e, s = parse_ci_env(text)
        for k, v in e.items():
            env.setdefault(k, v)
        if s and not services:
            services = s
    return TargetEnv(env=env, services=services, setup=discover_setup_commands(workdir))
