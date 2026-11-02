"""Secret-scan do diff antes de abrir/atualizar o PR (Trilha H — segurança).

Gate determinístico (o output do motor é PROPOSTA): antes de **empurrar** um PR, varremos as linhas
ADICIONADAS do diff atrás de credenciais. Achou → bloqueia o push (o segredo nem sai da máquina) e
surfa pro humano. É o mesmo fio de A/D: política determinística antes de uma ação de alto impacto.

ALTA PRECISÃO de propósito: só **formatos conhecidos** de credencial (chave privada, tokens de
provedores). Bloquear tem custo (trava PR legítimo), então evitamos heurística de entropia aqui —
fica como follow-up. Varre só linhas `+` (o que o PR INTRODUZ), nunca contexto nem remoções.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (nome legível, regex). Formatos canônicos com baixíssimo falso-positivo.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("chave privada", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "GitHub token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    ),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Stripe secret key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{24,}\b")),
    ("OpenAI/Anthropic key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
)


@dataclass(frozen=True)
class SecretFinding:
    """Uma credencial encontrada no diff. `redacted` nunca expõe o segredo inteiro."""

    pattern: str
    redacted: str


class SecretLeakError(Exception):
    """Levantada quando o diff contém segredo — aborta o push (o ciclo marca FAILED e avisa)."""


def _redact(match: str) -> str:
    # mostra só um prefixo curto pra dar pista sem vazar o segredo no log/feed.
    head = match[:4]
    return f"{head}…*** ({len(match)} chars)"


def scan_diff(diff: str) -> list[SecretFinding]:
    """Varre as linhas ADICIONADAS de um diff unificado e devolve as credenciais encontradas."""
    findings: list[SecretFinding] = []
    seen: set[tuple[str, str]] = set()
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue  # só o que o PR INTRODUZ; ignora contexto, remoções e cabeçalho de arquivo
        added = line[1:]
        for name, rx in _PATTERNS:
            m = rx.search(added)
            if not m:
                continue
            redacted = _redact(m.group(0))
            key = (name, redacted)
            if key not in seen:
                seen.add(key)
                findings.append(SecretFinding(pattern=name, redacted=redacted))
    return findings
