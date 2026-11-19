"""Right-sizing semântico: a issue precisa ser QUEBRADA antes de implementar? (melhor que contar).

Problema do sinal antigo (`check_issue_size`): contava `- [ ]` de "Critérios de aceite" — proxy ruim
que dá falso-positivo em feature coesa.
Uma feature COESA (1 PR) pode ter 9 critérios sem ser épico (falso-positivo real, issue #297). Épico
não é "muitos critérios" — é **entrega mais de um artefato que poderia ser um PR separado**.

Detector em camadas (barato→caro, `determinístico → Jev → frontier`):
- **Tier 0** (`epic_signal`, puro, sem LLM): sinais estruturais — fases, spread de subsistemas,
  múltiplos entregáveis. Decide 3 baldes: `small` (não épico, nem chama Jev), `big` (épico claro),
  `ambiguous` (escala p/ Jev). Só gasta token no borderline.
- **Tier 1** (`assess_epic` + Jev): no ambíguo, pergunta ESTRUTURADA e anti-heurística-velha →
  `{decision, confidence, reason}`. O `reason` é acionável (quais entregáveis), não "9 > 7".
- **Política**: SÓ SURFA (nunca bloqueia o impl); age com confiança alta. O impl confia no refino.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from roboto.llm.decide import Decider
from roboto.result import Ok

# o que a pergunta do Jev deixa EXPLÍCITO: muitos critérios ≠ épico (mata o viés da contagem).
_JEV_QUESTION = (
    "Esta issue deve ser QUEBRADA em sub-issues antes de implementar, porque entrega MAIS DE UM "
    "artefato que poderia ser um PR separado? Responda decision=true SÓ se for claramente "
    "multi-entregável. Uma feature coesa com muitos Critérios de aceite NÃO é épico."
)
_CONF_AGE = 0.7  # só age (sugere quebrar) com confiança >= isto; abaixo, não surfa (evita falso+)

_PHASES = re.compile(r"\b(fase|etapa)\s*\d|primeiro.{0,40}\b(depois|em seguida|ent[aã]o)\b", re.I)
_DELIVERABLE = re.compile(r"(?mi)^[\s\-*]*(implementar|criar|adicionar|desenvolver|escrever)\b")
# raízes/camadas de subsistema (spread = toca várias partes do sistema).
_SUBSYS = (
    "migrations", "api", "ui", "frontend", "backend", "worker", "realtime", "infra", "schema",
    "scheduler", "auth", "db", "apps/", "packages/",
)


@dataclass(frozen=True)
class EpicSignal:
    bucket: str  # "small" | "big" | "ambiguous"
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EpicVerdict:
    is_epic: bool
    confidence: float
    reason: str
    source: str  # "heuristica" | "jev"


def epic_signal(title: str, body: str) -> EpicSignal:
    """Tier 0 determinístico: classifica em small/big/ambiguous por sinais estruturais. Puro."""
    text = f"{title}\n{body}"
    phases = bool(_PHASES.search(text))
    deliverables = len(set(m.lower() for m in _DELIVERABLE.findall(body)))
    subsys = sorted({s for s in _SUBSYS if s in text.lower()})
    reasons: list[str] = []
    if phases:
        reasons.append("tem fases/sequência")
    if deliverables >= 3:
        reasons.append(f"{deliverables} verbos de entrega distintos")
    if len(subsys) >= 2:
        reasons.append(f"toca {len(subsys)} subsistemas ({', '.join(subsys[:4])})")
    if phases and len(subsys) >= 3:
        return EpicSignal("big", reasons)
    if not phases and deliverables <= 1 and len(subsys) <= 1:
        return EpicSignal("small", reasons or ["entregável único"])
    return EpicSignal("ambiguous", reasons)


async def assess_epic(title: str, body: str, decider: Decider | None) -> EpicVerdict:
    """Tier 0 + Jev no ambíguo. Conservador: sem decider no ambíguo → NÃO épico (não trava)."""
    sig = epic_signal(title, body)
    motivo = "; ".join(sig.reasons)
    if sig.bucket == "small":
        return EpicVerdict(False, 0.9, motivo or "entregável único", "heuristica")
    if sig.bucket == "big":
        return EpicVerdict(True, 0.9, motivo, "heuristica")
    if decider is None:
        return EpicVerdict(False, 0.3, "ambíguo, sem Jev", "heuristica")
    result = await decider.decide(_JEV_QUESTION, f"{title}\n{body}")
    if isinstance(result, Ok):
        d = result.value
        return EpicVerdict(d.decision, d.confidence, d.reason or motivo, "jev")
    return EpicVerdict(False, 0.3, "Jev indisponível", "heuristica")


def epic_advisory(verdict: EpicVerdict) -> str:
    """Texto de AVISO (surface-only, nunca bloqueia). Vazio se não-épico ou confiança baixa."""
    if not verdict.is_epic or verdict.confidence < _CONF_AGE:
        return ""
    return (
        f"🧩 Right-sizing ({verdict.source}): parece ÉPICO — {verdict.reason}. "
        "Considere quebrar em sub-issues (breakdown). Aviso, não bloqueia."
    )
