"""Secret-scan do diff antes de abrir/atualizar o PR (Trilha H — segurança).

Gate determinístico (o output do motor é PROPOSTA): antes de **empurrar** um PR, varremos as linhas
ADICIONADAS do diff atrás de credenciais. Achou → bloqueia o push (o segredo nem sai da máquina) e
surfa pro humano. É o mesmo fio de A/D: política determinística antes de uma ação de alto impacto.

ALTA PRECISÃO de propósito: só **formatos conhecidos** de credencial (chave privada, tokens de
provedores). Bloquear tem custo (trava PR legítimo), então evitamos heurística de entropia aqui —
fica como follow-up. Varre só linhas `+` (o que o PR INTRODUZ), nunca contexto nem remoções.
"""

from __future__ import annotations

import math
import re
from collections import Counter
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

# heurística KEYED (menos falso-positivo que entropia pura): um identificador com CARA de segredo
# atribuído a um literal de string. Combinado com alta entropia do valor, é sinal forte.
_ASSIGN = re.compile(
    r"""(?ix)
    # palavra-chave com cara de segredo (pode estar dentro de um identificador, ex.: DB_PASSWORD)
    (?:pass(?:word|wd)?|secret|token|api[_-]?key|access[_-]?key
       |private[_-]?key|client[_-]?secret|auth[_-]?token)
    \w*            # resto do identificador
    \s*[:=]\s*
    ['"]([^'"]{16,})['"]
    """
)
# entropia (bits/char) acima da qual o valor "parece aleatório" (segredo), não palavra/placeholder.
_ENTROPY_MIN = 3.5

# arquivos de teste/fixture: o segredo é FAKE por design (ex.: token:"nod…" num route.test.ts).
# A heurística KEYED+entropia (propensa a falso-positivo) NÃO roda aqui; os formatos canônicos
# (_PATTERNS, ~0 FP) seguem valendo em TODO lugar — um ghp_/AKIA real num teste ainda vaza.
_TEST_PATH = re.compile(
    r"""(?ix)
    (?:^|/)(?:tests?|__tests__|__mocks__|fixtures?|e2e)(?:/|$)  # dir: tests/ spec/ fixtures/
    | \.(?:test|spec|e2e)\.[a-z0-9]+$                           # foo.test.ts x.int.test.ts
    | (?:^|/)test_[^/]*\.py$ | _test\.py$                       # pytest: test_x.py | x_test.py
    """
)


def _is_test_path(path: str) -> bool:
    """O arquivo do diff é de teste/fixture? (segredo fake por design — pula a heurística)."""
    return bool(_TEST_PATH.search(path))


def _shannon_bits_per_char(s: str) -> float:
    if not s:
        return 0.0
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


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
    in_test = False  # contexto de arquivo: a heurística de entropia não roda em arquivo de teste
    for line in diff.splitlines():
        if line.startswith("+++"):
            # cabeçalho de arquivo (+++ b/path | +++ /dev/null): só atualiza o contexto.
            path = line[4:].strip()
            path = path[2:] if path.startswith(("a/", "b/")) else path
            in_test = _is_test_path(path)
            continue
        if not line.startswith("+"):
            continue  # só o que o PR INTRODUZ; ignora contexto e remoções
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
        # camada KEYED + entropia: chave com cara de segredo atribuída a valor de alta entropia.
        # Pula em arquivo de teste/fixture (valor fake por design) — evita o FP que matou o run #56.
        if in_test:
            continue
        am = _ASSIGN.search(added)
        if am and _shannon_bits_per_char(am.group(1)) >= _ENTROPY_MIN:
            redacted = _redact(am.group(1))
            key = ("segredo atribuído (heurística)", redacted)
            if key not in seen:
                seen.add(key)
                findings.append(SecretFinding(pattern=key[0], redacted=redacted))
    return findings
