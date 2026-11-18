"""Política de 2 eixos — o gate determinístico que decide auto/ask/off por ação (#267, D28/H).

Troca o least-privilege **estático e binário** (`tool_policy`) por uma decisão **por chamada**:
- **eixo classe** (`ToolClass`: read/write/sensitive) — o que a ferramenta faz;
- **eixo autonomia** (`ActionMode` ask/auto/off por `ActionKind`: commit/push/pr/merge/delete),
  graduada por nível (`Autonomy` careful/normal/free), resolvida most-specific-first
  (regra por ação do agente → default do nível).

Invariantes (não negociáveis, independem do nível): **high-risk sempre pede humano**; **merge/delete
nunca são auto** (D7/irreversível); e o **outside-content guard** — depois de ler conteúdo externo,
ação *outbound* volta a pedir OK (anti prompt-injection). `verdict()` é **puro** — a decisão é
código testável, não LLM (determinismo primeiro). Derivado do `verdict()` do Tucano (Apache-2.0;
`research/tucano-reuso.md`), adaptado: nosso eixo de visibilidade é a tool-class (não "connectors").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ToolClass(StrEnum):
    READ = "read"  # navegação/leitura: não muda estado
    WRITE = "write"  # edita o repo / roda comando com efeito
    SENSITIVE = "sensitive"  # execução arbitrária sem ação reconhecida


class ActionKind(StrEnum):
    COMMIT = "commit"
    PUSH = "push"
    PR = "pr"
    MERGE = "merge"
    DELETE = "delete"


class ActionMode(StrEnum):
    AUTO = "auto"  # executa sozinho
    ASK = "ask"  # pede OK humano (vira interaction — #265)
    OFF = "off"  # proibido (nega sem perguntar)


class Autonomy(StrEnum):
    CAREFUL = "careful"  # pede antes de qualquer mudança
    NORMAL = "normal"  # escreve livre; pede em sensível/outbound
    FREE = "free"  # tudo sozinho, menos high-risk e irreversível


# Ações outbound/irreversíveis que o outside-guard volta a pedir após leitura externa.
OUTBOUND: frozenset[ActionKind] = frozenset(
    {ActionKind.PUSH, ActionKind.PR, ActionKind.MERGE, ActionKind.DELETE}
)

# merge/delete ficam em `ask` mesmo no FREE (D7 / destrutivo): nunca viram auto por nível.
_LEVEL_DEFAULTS: dict[Autonomy, dict[ActionKind, ActionMode]] = {
    Autonomy.CAREFUL: dict.fromkeys(ActionKind, ActionMode.ASK),
    Autonomy.NORMAL: {
        ActionKind.COMMIT: ActionMode.AUTO,
        ActionKind.PUSH: ActionMode.ASK,
        ActionKind.PR: ActionMode.ASK,
        ActionKind.MERGE: ActionMode.ASK,
        ActionKind.DELETE: ActionMode.ASK,
    },
    Autonomy.FREE: {
        ActionKind.COMMIT: ActionMode.AUTO,
        ActionKind.PUSH: ActionMode.AUTO,
        ActionKind.PR: ActionMode.AUTO,
        ActionKind.MERGE: ActionMode.ASK,
        ActionKind.DELETE: ActionMode.ASK,
    },
}

# ordem de restrição: o mais restritivo entre as ações vence.
_RESTRICTION: dict[ActionMode, int] = {ActionMode.AUTO: 0, ActionMode.ASK: 1, ActionMode.OFF: 2}


@dataclass(frozen=True)
class Policy:
    """Autonomia do agente + overrides por ação (most-specific-first)."""

    autonomy: Autonomy = Autonomy.NORMAL
    rules: dict[ActionKind, ActionMode] = field(default_factory=dict)

    def mode_for(self, kind: ActionKind) -> ActionMode:
        if kind in self.rules:  # regra explícita do agente vence o default do nível
            return self.rules[kind]
        return _LEVEL_DEFAULTS[self.autonomy][kind]


@dataclass(frozen=True)
class Decision:
    """Veredito do gate. Exatamente um de run/ask/off é verdadeiro; `why` explica o motivo."""

    run: bool
    ask: bool
    off: bool
    why: str


def _gate_mode(kinds: frozenset[ActionKind], policy: Policy) -> ActionMode:
    """O modo mais restritivo entre as ações da chamada (sem ação → auto)."""
    if not kinds:
        return ActionMode.AUTO
    return max((policy.mode_for(k) for k in kinds), key=lambda mode: _RESTRICTION[mode])


def verdict(
    cls: ToolClass,
    kinds: frozenset[ActionKind],
    policy: Policy,
    *,
    high_risk: bool = False,
    outside: bool = False,
) -> Decision:
    """Decide auto/ask/off p/ uma chamada classificada. Puro — a política decide, não o modelo."""
    if cls is ToolClass.READ and not kinds:
        return Decision(run=True, ask=False, off=False, why="read")
    if high_risk:  # caminho sensível (migrations/CI/auth): sempre humano, qualquer nível
        return Decision(run=False, ask=True, off=False, why="risk")
    mode = _gate_mode(kinds, policy)
    if mode is ActionMode.OFF:
        return Decision(run=False, ask=False, off=True, why="off")
    if mode is ActionMode.ASK:
        return Decision(run=False, ask=True, off=False, why="rule")
    if outside and (kinds & OUTBOUND):  # outside-guard: outbound após ler conteúdo externo
        return Decision(run=False, ask=True, off=False, why="guard")
    if cls is ToolClass.SENSITIVE:  # execução arbitrária sem ação reconhecida → humano
        return Decision(run=False, ask=True, off=False, why="class")
    if cls is ToolClass.WRITE and policy.autonomy is Autonomy.CAREFUL and not kinds:
        return Decision(run=False, ask=True, off=False, why="class")
    return Decision(run=True, ask=False, off=False, why="auto")
