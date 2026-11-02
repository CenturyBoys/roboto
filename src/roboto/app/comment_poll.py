"""Gatilho por COMENTÁRIO `@potter <comando>` (Trilha B, #166) — polling, SEM webhook.

Humano comenta `@potter implementa` / `@potter revisa` / `@potter refina` numa issue/PR → o poller
(sem conta de bot dedicada) dispara o run correspondente. **Anti-loop por MARCADOR**: o bot nunca
escreve `@potter` e assina os comentários com `BOT_MARKER`; o poller ignora comentário com o
marcador. Portável (todo sistema tem comentário) — é um adapter de plataforma.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from roboto.orchestrator.model import Error, GithubEvent
from roboto.orchestrator.store import Store
from roboto.result import Ok, Result

BOT_MARKER = "<!-- potter:bot -->"  # assinatura invisível nos comentários do fleet (anti-loop)

# `@potter <comando>` -> agente do run
_COMMANDS: dict[str, str] = {
    "refina": "refine", "refinar": "refine",
    "implementa": "impl", "implementar": "impl", "coda": "impl",
    "revisa": "correct", "revisar": "correct", "corrige": "correct", "corrigir": "correct",
}


@dataclass(frozen=True)
class CommentCmd:
    comment_id: int
    issue_number: int
    agent: str


def decide_comment_commands(
    comments: list[tuple[int, int, str]], cursor: int, *, marker: str = BOT_MARKER
) -> tuple[list[CommentCmd], int]:
    """PURO (testável): dado [(comment_id, issue_number, body)] e o cursor do último já visto,
    devolve os comandos a disparar + o novo cursor. Ignora o do bot (marcador) e o sem comando."""
    cmds: list[CommentCmd] = []
    new_cursor = cursor
    for cid, issue, body in comments:
        new_cursor = max(new_cursor, cid)
        if cid <= cursor or marker in body:
            continue
        low = body.lower()
        if "@potter" not in low:
            continue
        resto = low.split("@potter", 1)[1].strip().split()
        agent = _COMMANDS.get(resto[0]) if resto else None
        if agent:
            cmds.append(CommentCmd(cid, issue, agent))
    return cmds, new_cursor


class CommentLister(Protocol):
    # [(comment_id, issue_number, body)] dos comentários recentes do repo
    async def list_recent_comments(
        self, repo: str
    ) -> Result[list[tuple[int, int, str]], Error]: ...


async def process_comment_poll_tick(
    github: CommentLister,
    store: Store,
    *,
    tenant: str,
    repos: list[str],
    now: Callable[[], datetime],
) -> None:
    """Laço do gatilho por comentário (#166): por repo, lê os comentários novos e dispara os
    `@potter <comando>` como runs. Cursor por repo via channel_offset (não reprocessa)."""
    moment = now()
    for repo in repos:
        cursor = await store.get_channel_offset(tenant, f"ghc:{repo}") or 0
        res = await github.list_recent_comments(repo)
        if not isinstance(res, Ok):
            continue
        cmds, new_cursor = decide_comment_commands(res.value, cursor)
        for c in cmds:
            ev = GithubEvent(
                tenant=tenant,
                repo=repo,
                issue_id=str(c.issue_number),
                agent=c.agent,
                idempotency_key=f"cmd:{repo}:{c.comment_id}",
            )
            await store.insert_run_if_absent(ev, moment)
        if new_cursor > cursor:
            await store.set_channel_offset(tenant, f"ghc:{repo}", new_cursor, moment)
