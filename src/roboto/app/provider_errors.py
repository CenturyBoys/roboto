"""Classificador de erro OPERACIONAL do provider (billing/cota/rate) → mensagem clara pro operador.

Padrão "nunca morrer opaco": 403 budget-de-workspace / 402 crédito / 429 rate do OpenRouter NÃO são
bug nem o modelo — são billing/operação. Em vez de despejar o stacktrace cru no feed, o harness
detecta e surfa a AÇÃO (suba o budget / recarregue / espere o reset). Pura/testável.
"""

from __future__ import annotations

import re


def classify_provider_error(message: str) -> str | None:
    """Mensagem de operador se for erro OPERACIONAL do provider (billing/cota/rate); senão None."""
    low = message.lower()
    # OpenRouter workspace budget (403) — extrai gasto/limite/reset do payload quando vierem.
    if ("workspace" in low and "budget" in low) or "openrouter_workspace_budget" in low:
        spend = re.search(r'spend_usd["\s:]+([0-9.]+)', message)
        limit = re.search(r'limit_usd["\s:]+([0-9.]+)', message)
        reset = re.search(r'resets_at["\s:]+"?([0-9T:\-.Z]+)', message)
        det = ""
        if spend and limit:
            det += f" (${float(spend.group(1)):.2f}/${float(limit.group(1)):.0f})"
        if reset:
            det += f", reseta {reset.group(1)}"
        return (
            f"💸 OpenRouter: budget do workspace esgotado{det} — OPERACIONAL, não é bug nem o "
            "modelo. Suba o budget do workspace (org admin) ou espere o reset, e re-dispare."
        )
    if "402" in message or "exceed your available credit" in low or "insufficient" in low:
        return (
            "💸 OpenRouter: sem crédito (402) — OPERACIONAL, não é bug. Recarregue o crédito e "
            "re-dispare."
        )
    if "429" in message or "rate limit" in low or "overloaded" in low:
        return (
            "⏳ Provider sobrecarregado/rate-limit (429) — OPERACIONAL e transitório. "
            "Re-dispare em instantes."
        )
    return None
