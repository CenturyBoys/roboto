"""Gatilho por POLLING de atividade de PR (Trilha B, #166) — AGNÓSTICO: um adapter de plataforma
lista os PRs abertos; o NÚCLEO decide o quê revisar, com DEBOUNCE (não re-revisa a cada commit).

Sem webhook (decisão do dono): um laço periódico pergunta "o que mudou?". Para cada PR aberto:
- `head_sha` mudou vs o visto antes → marca ATIVIDADE (reinicia o debounce); guarda o sha visto.
- `head_sha` == último já revisado → nada (já avaliado neste estado).
- estável há ≥ `debounce` e ainda não revisado → ESTABILIZOU → dispara a avaliação desse sha.

A avaliação reusa o run `agent='correct'` (process_correct_tick): ele RE-REVISA o PR e, se reprovar,
corrige; se aprovar, comenta "nada a ajustar". Estado por PR vive no banco (`pr_review_state`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from roboto.orchestrator.model import Error, GithubEvent, PrState
from roboto.orchestrator.store import Store
from roboto.result import Ok, Result


@dataclass(frozen=True)
class PrDecision:
    number: int
    sha: str
    dispatch: bool  # True = estabilizou e deve ser avaliado agora
    new_state: PrState


def decide_pr(
    number: int, head_sha: str, prev: PrState | None, now: datetime, debounce: timedelta
) -> PrDecision:
    """Decisão PURA do poller para um PR (determinismo primeiro; testável sem rede/banco)."""
    if prev is None:
        # 1ª vez que vejo este PR: registra atividade, NÃO avalia ainda (espera estabilizar)
        return PrDecision(number, head_sha, False, PrState(head_sha, now, ""))
    if head_sha != prev.last_seen_sha:
        # mudou desde a última checagem → reinicia o debounce (preserva o que já foi revisado)
        return PrDecision(number, head_sha, False, PrState(head_sha, now, prev.reviewed_sha))
    if head_sha == prev.reviewed_sha:
        return PrDecision(number, head_sha, False, prev)  # já avaliado neste sha
    if now - prev.last_activity_at >= debounce:
        # estável há ≥ debounce e ainda não avaliado → dispara e marca como avaliado
        stable = PrState(head_sha, prev.last_activity_at, head_sha)
        return PrDecision(number, head_sha, True, stable)
    return PrDecision(number, head_sha, False, prev)  # estável, mas ainda dentro do debounce


class OpenPrLister(Protocol):
    # (número, head_sha) dos PRs abertos — adapter de plataforma (GitHub hoje, agnóstico depois)
    async def list_open_prs(self, repo: str) -> Result[list[tuple[int, str]], Error]: ...


async def process_pr_poll_tick(
    github: OpenPrLister,
    store: Store,
    *,
    tenant: str,
    repos: list[str],
    now: Callable[[], datetime],
    debounce_seconds: int = 1800,
) -> None:
    """Laço do gatilho por polling (#166): por repo, lista os PRs abertos, aplica o debounce e, para
    cada PR que ESTABILIZOU num sha novo, enfileira um run `agent='correct'` (re-review → corrige/
    avisa). Idempotente pelo sha (não re-dispara o mesmo estado). NÃO usa webhook."""
    moment = now()
    debounce = timedelta(seconds=debounce_seconds)
    for repo in repos:
        prs = await github.list_open_prs(repo)
        if not isinstance(prs, Ok):
            continue
        for number, head_sha in prs.value:
            prev = await store.get_pr_state(tenant, repo, number)
            decision = decide_pr(number, head_sha, prev, moment, debounce)
            await store.set_pr_state(tenant, repo, number, decision.new_state)
            if decision.dispatch:
                ev = GithubEvent(
                    tenant=tenant,
                    repo=repo,
                    issue_id=str(number),
                    agent="correct",
                    idempotency_key=f"poll-correct:{repo}:{number}:{head_sha}",
                )
                await store.insert_run_if_absent(ev, moment)
