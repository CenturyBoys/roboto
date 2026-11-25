"""Carregador do graph doctor: raw do GitHub → nós do grafo, e o orquestrador github-backed.

Separa o I/O (buscar issues/PRs) da DETECÇÃO pura (``graph_doctor``). O mapeamento é PURO/testável
(recebe os dicts crus que o REST devolve); só ``audit_repo`` toca o github.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from roboto.app.deps import blocked_by
from roboto.app.graph_doctor import (
    GraphFinding,
    HealAction,
    IssueNode,
    PrNode,
    audit_graph,
    plan_heal,
)
from roboto.app.self_heal import named_deps
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result

# "Closes/Fixes/Resolves #N" (fecha a issue ao mergear) — a convenção que o GitHub honra.
_CLOSES = re.compile(
    r"\b(?:clos(?:e|es|ed)|fix(?:es|ed)?|resolv(?:e|es|ed))\s+#(\d+)", re.IGNORECASE
)
_REVERT = re.compile(r"\brevert", re.IGNORECASE)
_HASHREF = re.compile(r"#(\d+)")


def _days_since(iso: object, now: datetime) -> int:
    if not isinstance(iso, str) or not iso:
        return 0
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, (now - dt).days)


def build_nodes(
    issues_raw: list[dict[str, Any]], prs_raw: list[dict[str, Any]], *, now: datetime,
) -> tuple[list[IssueNode], list[PrNode]]:
    """PURO: mapeia os dicts crus do REST do GitHub para os nós do grafo. ``is_auto`` vem do label
    `auto`; ``refined=False`` quando o esqueleto ainda tem o placeholder '(a definir no refino)'."""
    issues: list[IssueNode] = []
    for x in issues_raw:
        body = str(x.get("body") or "")
        labels = [
            str(lbl.get("name", "")) for lbl in x.get("labels", []) if isinstance(lbl, dict)
        ]
        state = str(x.get("state", "open"))
        is_auto = "auto" in labels
        issues.append(IssueNode(
            number=int(x["number"]),
            title=str(x.get("title") or ""),
            state=state,
            deps=blocked_by(body),
            named_deps=[d.label for d in named_deps(body)],
            state_reason=str(x.get("state_reason") or ""),
            is_auto=is_auto,
            refined=not (is_auto and "(a definir no refino)" in body),
            age_days=_days_since(x.get("created_at"), now) if state == "open" else 0,
        ))
    # 1ª passada: detecta os PRs de REVERT (título/body "revert" + #N → o #N é o PR revertido).
    revert_de: dict[int, int] = {}
    for p in prs_raw:
        texto = f"{p.get('title') or ''}\n{p.get('body') or ''}"
        if _REVERT.search(texto):
            for alvo in _HASHREF.findall(texto):
                revert_de.setdefault(int(alvo), int(p["number"]))
    prs: list[PrNode] = []
    for p in prs_raw:
        num = int(p["number"])
        merged = p.get("merged_at") is not None
        estado = "merged" if merged else str(p.get("state", "open"))
        corpo = f"{p.get('title') or ''}\n{p.get('body') or ''}"
        prs.append(PrNode(
            number=num, state=estado, title=str(p.get("title") or ""),
            closes=[int(n) for n in _CLOSES.findall(corpo)],
            reverted_by=revert_de.get(num),
        ))
    return issues, prs


async def audit_repo(
    github: object, repo: str, *, now: datetime,
) -> Result[list[GraphFinding], Error]:
    """Github-backed: busca issues (abertas+fechadas) e PRs (todos) e roda a auditoria. Erra se
    qualquer busca falhar (sem grafo parcial — o doctor não chuta)."""
    iss = await github.list_issues_audit(repo)  # type: ignore[attr-defined]
    if isinstance(iss, Err):
        return Err(iss.error)
    prs = await github.list_prs_audit(repo)  # type: ignore[attr-defined]
    if isinstance(prs, Err):
        return Err(prs.error)
    nodes_i, nodes_p = build_nodes(iss.value, prs.value, now=now)
    return Ok(audit_graph(nodes_i, nodes_p))


@dataclass(frozen=True)
class DoctorReport:
    findings: list[GraphFinding]
    applied: list[HealAction]  # curas AUTO aplicadas (reabrir) — protetoras
    pending: list[HealAction]  # propostas que esperam gerente/humano (fechar/repontar/refino/ciclo)


async def doctor_repo(github: object, repo: str, *, now: datetime) -> Result[DoctorReport, Error]:
    """Audita + CURA o que é auto-seguro (só reabrir — protetor, não perde trabalho) e devolve as
    demais propostas PENDENTES p/ o gerente/humano. É o gate 'graph doctor' da escada: determinismo
    acha, reabre o que é seguro, e surfa o resto (fechar redundante, repontar, refino, ciclo)."""
    aud = await audit_repo(github, repo, now=now)
    if isinstance(aud, Err):
        return Err(aud.error)
    acoes = plan_heal(aud.value)
    aplicadas: list[HealAction] = []
    pendentes: list[HealAction] = []
    for a in acoes:
        if a.auto and a.action == "reopen":
            r = await github.set_issue_state(repo, a.issue, "open")  # type: ignore[attr-defined]
            (aplicadas if isinstance(r, Ok) else pendentes).append(a)
        else:
            pendentes.append(a)
    return Ok(DoctorReport(findings=aud.value, applied=aplicadas, pending=pendentes))
