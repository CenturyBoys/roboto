"""Orçamento do fleet (Trilha L): gasto do mês vs teto, com alerta.

Base de orçamento decidida (D6): **teto mensal-alvo em US$/token** (≈ 1 assinatura Max, ~R$550/mês)
+ **alerta em 80%**, barato-primeiro. O custo real por chamada já é medido em `llm_call` (trilha F);
aqui só agregamos o gasto do mês e comparamos com o teto — surfado no cockpit, **não bloqueante**
(degradar/pausar ao estourar fica como follow-up, pra não cortar trabalho sem régua calibrada).

Puro e sem I/O: o endpoint passa `spent` (do store) e `cap` (da config).
"""

from __future__ import annotations

from dataclasses import dataclass

_ALERT_AT = 0.8  # alerta em 80% do teto (D6)


@dataclass(frozen=True)
class BudgetStatus:
    """Gasto do mês vs teto. `pct` em [0,1+]; `alert` ≥80%; `over` ≥100%."""

    spent_usd: float
    cap_usd: float
    pct: float
    alert: bool
    over: bool


def assess(spent_usd: float, cap_usd: float, *, alert_at: float = _ALERT_AT) -> BudgetStatus:
    """Avalia o gasto do mês contra o teto. `cap_usd<=0` = sem teto (pct 0, nunca alerta)."""
    if cap_usd <= 0:
        return BudgetStatus(spent_usd=spent_usd, cap_usd=0.0, pct=0.0, alert=False, over=False)
    pct = spent_usd / cap_usd
    return BudgetStatus(
        spent_usd=spent_usd,
        cap_usd=cap_usd,
        pct=round(pct, 4),
        alert=pct >= alert_at,
        over=pct >= 1.0,
    )
