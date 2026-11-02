"""Classificação de erro TRANSITÓRIO de provedor (Trilha B/H — recuperação).

Um erro de provedor que é **temporário** (sem crédito no momento, rate-limit, instabilidade 5xx,
modelo sobrecarregado) NÃO deve virar FAILED terminal — o run deve **re-enfileirar com backoff** e o
daemon **retoma sozinho** quando a condição passa (ex.: o humano recarrega o crédito). Erro
permanente (bug, git, PR) segue terminal. Determinístico: casa marcadores na mensagem do erro.
"""

from __future__ import annotations

# marcadores (minúsculos) de falha TEMPORÁRIA de provedor — vale re-tentar com backoff.
_TRANSIENT = (
    "402",  # OpenRouter: "would exceed your available credit" (reserva por request / saldo)
    "exceed your available credit",
    "insufficient",
    "429",  # rate limit
    "rate limit",
    "rate-limit",
    "overloaded",
    "capacity",
    "timeout",
    "timed out",
    "temporarily",
    "503",
    "502",
    "500",
    "upstream",
)


def is_transient(message: str) -> bool:
    """`True` se a mensagem de erro parece transitória (vale re-enfileirar com backoff)."""
    low = message.lower()
    return any(m in low for m in _TRANSIENT)
