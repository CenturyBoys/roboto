"""Enforcement de aprovação por ação (D24, Trilha H): liga o `can_use_tool` do motor ao gate humano.

Os primitivos já existem separados — este módulo é a **cola** que faltava (ver `engines/claude_code`
TODO): transforma um pedido de uso de ferramenta do motor numa `interaction` de aprovação PENDENTE,
espera a decisão humana (pelo `SessionHub`, resolvida no console/Telegram) e **verifica por digest**
antes de liberar. Camadas reusadas:
- `approval_guard` — assina a ação (digest sha256 canônico) e compara EXATO no uso (anti-loopjack).
- `orchestrator.store.interaction` — registro durável da aprovação (sobrevive a restart).
- `app.session_hub.LiveSession` — a espera em-processo (`Future`) que o `can_use_tool` aguarda.

**Puro de SDK**: recebe `tool`+`args` e devolve `GateDecision(allow, reason)`. O motor mapeia o
resultado pro `PermissionResultAllow/Deny` do Agent SDK (seam fino em `claude_code`), então o
enforcement é testável sem o SDK vivo. A verificação por digest fica isolada em `verify_and_decide`
(pura), pra os dois caminhos — liberar e negar — serem exercitáveis em teste.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from roboto.app.approval_guard import ApprovedAction, canonical_action, matches
from roboto.app.classify import classify
from roboto.app.policy import Policy, verdict
from roboto.app.session_hub import LiveSession
from roboto.orchestrator.model import InteractionKind
from roboto.orchestrator.store import Store

_ALLOW = "allow"
_DENY = "deny"


@dataclass(frozen=True)
class GateDecision:
    """Veredito do gate: libera ou nega, com o motivo (que o motor re-injeta no deny)."""

    allow: bool
    reason: str = ""


# O motor fornece esta assinatura ao SDK: dada (tool, args), decide allow/deny aguardando o humano.
ApprovalCallback = Callable[[str, dict[str, object]], Awaitable[GateDecision]]


def verify_and_decide(
    approved_action: ApprovedAction, tool: str, args: dict[str, object], *, approved: bool
) -> GateDecision:
    """Decisão PURA: só libera se o humano aprovou **e** a ação a executar é EXATAMENTE a aprovada.

    `approved=False` → negado pelo humano. `approved=True` mas a ação divergiu da assinada
    (estado mexido entre aprovar e usar) → negado por anti-loopjacking. Na dúvida, nega.
    """
    if not approved:
        return GateDecision(allow=False, reason="negado pelo humano")
    if not matches(approved_action, tool, args):
        return GateDecision(allow=False, reason="ação divergente da aprovada (anti-loopjacking)")
    return GateDecision(allow=True)


async def decide_tool_use(
    *,
    store: Store,
    live: LiveSession,
    tenant: str,
    execution_id: int,
    tool: str,
    args: dict[str, object],
    now: Callable[[], datetime],
    session_id: int | None = None,
    answered_by: str = "human",
) -> GateDecision:
    """Gateia uma ação do motor: cria a `interaction`, espera o humano e verifica antes de liberar.

    Cada chamada cria a SUA interação (o binding anti-loopjacking é o `interaction_id`: só se aprova
    a ação exata pendente). Persiste o veredito e devolve `GateDecision` pro motor.
    """
    signed = ApprovedAction.sign(tool, args)
    interaction = await store.create_interaction(
        tenant,
        execution_id,
        InteractionKind.APPROVAL,
        canonical_action(tool, args),
        [_ALLOW, _DENY],
        now(),
        session_id=session_id,
    )
    approved = await live.request_approval(interaction.id)
    decision = verify_and_decide(signed, tool, args, approved=approved)
    answer = _ALLOW if decision.allow else f"{_DENY}: {decision.reason}"
    await store.answer_interaction(interaction.id, answer, answered_by, now())
    return decision


def make_approval_callback(
    *,
    store: Store,
    live: LiveSession,
    tenant: str,
    execution_id: int,
    now: Callable[[], datetime],
    session_id: int | None = None,
    answered_by: str = "human",
) -> ApprovalCallback:
    """Cola o gate a um run concreto: devolve o callback que o motor entrega ao `can_use_tool`."""

    async def _approve(tool: str, args: dict[str, object]) -> GateDecision:
        return await decide_tool_use(
            store=store,
            live=live,
            tenant=tenant,
            execution_id=execution_id,
            tool=tool,
            args=args,
            now=now,
            session_id=session_id,
            answered_by=answered_by,
        )

    return _approve


def make_policy_callback(
    *,
    store: Store,
    live: LiveSession,
    tenant: str,
    execution_id: int,
    policy: Policy,
    now: Callable[[], datetime],
    session_id: int | None = None,
    answered_by: str = "human",
    outside: bool = False,
) -> ApprovalCallback:
    """Callback com a policy de 2 eixos (#267) na frente do humano: a `verdict` decide o destino.

    `run` → libera sozinho (sem interação); `off` → nega sozinho; `ask` → cai no gate humano
    (`decide_tool_use`). `outside` é estático por ora (o sinal de "leu conteúdo externo" por turno é
    follow-up do PoC); a lógica do outside-guard já está em `verdict` e testada.
    """

    async def _gate(tool: str, args: dict[str, object]) -> GateDecision:
        cls, kinds, high_risk = classify(tool, args)
        decision = verdict(cls, kinds, policy, high_risk=high_risk, outside=outside)
        if decision.run:
            return GateDecision(allow=True)
        if decision.off:
            return GateDecision(allow=False, reason=f"proibido pela política ({decision.why})")
        return await decide_tool_use(
            store=store,
            live=live,
            tenant=tenant,
            execution_id=execution_id,
            tool=tool,
            args=args,
            now=now,
            session_id=session_id,
            answered_by=answered_by,
        )

    return _gate
