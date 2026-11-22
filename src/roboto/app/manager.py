"""Escada worker→gerente→humano (fatia 1 do épico #322, orquestração autônoma).

Quando o TRABALHADOR (motor barato) esgota as tentativas num gate (ex.: CI local vermelho), antes de
escalar pro HUMANO um GERENTE (motor FORTE, agêntico) pega o estado travado e tenta resolver.
Determinismo-primeiro: o harness decide QUANDO chamar o gerente; o gerente tem liberdade
(ferramentas, mais turnos) pra RESOLVER. Validado na T1 (#330 arenavalendo): o Sonnet resolveu —
typecheck + 224 testes verdes — o que o qwen-coder-30b não fechou (`noUncheckedIndexedAccess`).

O gerente NÃO commita (o harness commita e re-verifica o gate) — quem dá o veredito "resolveu" é o
chamador, re-rodando o CI. Assim o guarda-corpo (não abrir PR vermelho) segue valendo.
"""

from __future__ import annotations

from collections.abc import Callable

from roboto.app.engine_loop import guarded_events
from roboto.engines.port import CodingEngine, RunSpec
from roboto.result import Err

# fábrica do motor-gerente (modelo FORTE) — injetável (runtime constrói; teste passa um fake)
MakeManager = Callable[[], CodingEngine]


def manager_prompt(which: str, red: str, issue_title: str, issue_body: str) -> str:
    """Prompt de supervisor: o trabalhador empacou num gate; resolva o estado travado pela spec.
    Mandato AMPLO de propósito — "deixe o gate verde pela spec", não uma regra por erro (hardcodar
    regra por erro é frágil; o gerente raciocina)."""
    return (
        "You are the SENIOR ENGINEER / MANAGER picking up a task a junior worker could NOT finish. "
        "Resolve it fully. Only hand back to a human if it genuinely needs a human DECISION "
        "(ambiguous requirement, missing access/credential, product call) — a technical failure "
        "you fix yourself.\n\n"
        f"TASK: {issue_title}\n{issue_body}\n\n"
        f"The worker's local check `{which}` is RED after its own attempts and it gave up. "
        f"Output of `{which}`:\n\n{red}\n\n"
        "YOUR JOB:\n"
        f"1. Read the relevant code/tests/docs. Diagnose the ROOT cause of the `{which}` failure.\n"
        "2. Fix the code and/or tests so the check passes, consistent with the task spec and repo "
        "conventions (read any referenced ADR/docs — they are the source of truth). Do NOT weaken "
        "or delete tests just to make it green.\n"
        f"3. VERIFY by running the same check the repo uses for `{which}`. Iterate until GREEN.\n"
        "4. When green, STOP. Do NOT commit or push (the harness commits).\n\n"
        "Write any human-facing text in PORTUGUESE; think and act freely like a senior engineer."
    )


async def run_manager(
    make_manager: MakeManager, *, tenant: str, repo: str, workdir: str, prompt: str,
    idle_timeout: float | None = None,
) -> bool:
    """Roda o GERENTE no workdir travado até terminar. `True` se o motor arrancou (NÃO é o veredito
    do gate — quem re-verifica é o chamador, re-rodando o CI). `False` se o motor nem iniciou."""
    engine = make_manager()
    started = await engine.start(RunSpec(tenant=tenant, repo=repo, workdir=workdir, prompt=prompt))
    if isinstance(started, Err):
        return False
    async for _ev in guarded_events(engine.events(), idle_timeout):
        pass  # deixa o gerente editar/rodar/iterar; o watchdog de inatividade corta stall
    return True
