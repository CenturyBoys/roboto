"""Driver de épico (fatia 3 do épico #322, orquestração autônoma).

Pega um ÉPICO como objetivo, lê o grafo das issues-filhas e **despacha as que estão PRONTAS** na
ordem das dependências; ao fechar uma, a próxima destrava. Determinismo-primeiro: o andar-no-DAG, o
"quem está pronto" e os tetos (WIP/dispatch) são CÓDIGO; quem IMPLEMENTA é a escada agêntica (fatia
1), e dependências faltantes já viraram issue pelo self-heal (fatia 2).

Primeira versão SEGURA: o driver só **despacha o próximo lote pronto** (respeitando WIP e runs
ativos). NÃO faz merge (gate humano continua) nem subdivide sozinho — fica como guarda-corpo das
próximas iterações. Re-rodar o driver pega o que destravou desde a última passada.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from roboto.agents.breakdown import is_epic
from roboto.app.deps import blocked_by, blocking_labels
from roboto.app.issue_graph import epic_parents

# issue aberta crua: (número, título, corpo, labels, estado) — casa list_open_issues_full.
OpenIssue = tuple[int, str, str, list[str], str]


@dataclass(frozen=True)
class EpicChild:
    number: int
    deps: list[int]  # #N de que depende ("Depende de #N")
    blocked: bool  # tem label de bloqueio (status:blocked)
    is_epic: bool = False  # a própria filha é um ÉPICO → subdividir, não implementar


@dataclass(frozen=True)
class EpicPlan:
    epic: int
    ready: list[int] = field(default_factory=list)  # prontas p/ despachar AGORA
    waiting: list[int] = field(default_factory=list)  # esperando (label ou dep aberta)
    to_subdivide: list[int] = field(default_factory=list)  # filhas que são épico → subdividir
    total: int = 0  # total de filhas abertas do épico


def ready_issues(children: list[EpicChild], open_numbers: set[int]) -> list[int]:
    """Filhas PRONTAS: não-bloqueadas por label e com TODAS as deps resolvidas (dep resolvida = não
    está mais ABERTA — fechou/mergeou). ``children`` já vêm abertas (vindas da lista de abertas)."""
    return [
        c.number
        for c in children
        if not c.blocked and all(d not in open_numbers for d in c.deps)
    ]


def plan_epic(epic: int, open_issues: list[OpenIssue]) -> EpicPlan:
    """Puro: a partir das issues ABERTAS, acha as filhas do ``epic`` ("Parte do épico #N") e separa
    PRONTAS de ESPERANDO. Dep já fechada não aparece nas abertas → conta como resolvida."""
    open_numbers = {n for n, *_ in open_issues}
    children = [
        EpicChild(n, blocked_by(body), bool(blocking_labels(labels)), is_epic(title, body))
        for (n, title, body, labels, _state) in open_issues
        if epic in epic_parents(body)
    ]
    subdividir = [c.number for c in children if c.is_epic]  # filha-épico → subdividir, não codar
    nao_epico = [c for c in children if not c.is_epic]
    ready = ready_issues(nao_epico, open_numbers)
    ready_set = set(ready)
    waiting = [c.number for c in nao_epico if c.number not in ready_set]
    return EpicPlan(
        epic=epic, ready=ready, waiting=waiting, to_subdivide=subdividir, total=len(children),
    )


@dataclass(frozen=True)
class DriveResult:
    plan: EpicPlan
    dispatched: list[int] = field(default_factory=list)  # as que DISPAREI agora
    subdivided: list[int] = field(default_factory=list)  # filhas-épico que subdividi (novos filhos)
    spent_usd: float = 0.0  # gasto acumulado das filhas do épico (US$)
    budget_usd: float = 0.0  # teto configurado (0 = sem teto)
    budget_blocked: bool = False  # True = parei de despachar porque o teto estourou


# callables injetáveis (teste passa fakes; o harness liga no github/store reais)
ListFull = Callable[[str], Awaitable[list[OpenIssue]]]  # (repo) -> issues abertas (com corpo)
IsActive = Callable[[int], Awaitable[bool]]  # (número) -> já tem impl ativo?
Dispatch = Callable[[int], Awaitable[bool]]  # (número) -> enfileirou impl? True/False
SpendFor = Callable[[list[int]], Awaitable[float]]  # (números) -> gasto acumulado US$
Subdivide = Callable[[int], Awaitable[list[int]]]  # (épico-filho) -> sub-issues criadas


async def drive_epic(
    *, repo: str, epic: int, list_full: ListFull, is_active: IsActive, dispatch: Dispatch,
    wip_limit: int = 0, max_dispatch: int = 0,
    budget_usd: float = 0.0, spend_for: SpendFor | None = None,
    subdivide: Subdivide | None = None,
) -> DriveResult:
    """Planeja o épico e DESPACHA as filhas prontas que ainda não têm impl ativo (respeitando WIP,
    ``max_dispatch`` e o TETO DE BUDGET do épico). Não mergeia nem subdivide (guarda-corpos). O teto
    (``budget_usd``) é um freio AUTÔNOMO: o épico rodando sozinho amplifica custo — se o gasto das
    filhas já passou do teto, NÃO despacha mais (humano decide). Re-rodar pega o que destravou."""
    plan = plan_epic(epic, await list_full(repo))
    spent = await spend_for(plan.ready + plan.waiting) if spend_for is not None else 0.0
    if budget_usd > 0 and spent >= budget_usd:
        # teto estourado: trava o despacho (o épico não queima além do limite sem humano)
        return DriveResult(
            plan=plan, dispatched=[], spent_usd=spent, budget_usd=budget_usd, budget_blocked=True,
        )
    # SUBDIVISÃO AUTOMÁTICA: filha que é ÉPICO não se implementa — quebra em sub-issues (esqueletos
    # que precisam de refino antes de codar). Agêntico (breakdown) via callable; seguro (skeletons).
    subdivididos: list[int] = []
    if subdivide is not None:
        for n in plan.to_subdivide:
            if await is_active(n):
                continue
            novos = await subdivide(n)
            if novos:
                subdivididos.append(n)
    disparados: list[int] = []
    teto = max_dispatch if max_dispatch > 0 else len(plan.ready)
    for n in plan.ready:
        if len(disparados) >= teto:
            break
        if wip_limit > 0 and len(disparados) >= wip_limit:
            break
        if await is_active(n):
            continue  # já tem impl rodando → não duplica
        if await dispatch(n):
            disparados.append(n)
    return DriveResult(
        plan=plan, dispatched=disparados, subdivided=subdivididos, spent_usd=spent,
        budget_usd=budget_usd,
    )
