"""Secret-scan do diff (Trilha H): alta precisão, só linhas adicionadas, sem vazar o segredo."""

from __future__ import annotations

import pytest

from roboto.app.secret_scan import scan_diff

_GHP = "ghp_" + "a" * 36
_AKIA = "AKIA" + "A" * 16


def test_detects_github_token_in_added_line() -> None:
    diff = f'diff --git a/c.py b/c.py\n+TOKEN = "{_GHP}"\n'
    findings = scan_diff(diff)
    assert len(findings) == 1
    assert findings[0].pattern == "GitHub token"
    assert _GHP not in findings[0].redacted  # NUNCA expõe o segredo inteiro


def test_detects_private_key_header() -> None:
    diff = "+-----BEGIN RSA PRIVATE KEY-----\n+MIIEx...\n"
    assert any(f.pattern == "chave privada" for f in scan_diff(diff))


def test_detects_aws_access_key() -> None:
    diff = f"+aws_key={_AKIA}\n"
    assert any(f.pattern == "AWS access key id" for f in scan_diff(diff))


def test_ignores_removed_and_context_lines() -> None:
    # segredo em linha REMOVIDA (-) ou de contexto (sem sinal) não conta — o PR não o INTRODUZ.
    diff = f'-OLD = "{_GHP}"\n TOKEN = "{_GHP}"\n'
    assert scan_diff(diff) == []


def test_ignores_diff_file_header() -> None:
    # a linha "+++ b/arquivo" começa com + mas é cabeçalho, não conteúdo.
    diff = "+++ b/config.py\n+x = 1\n"
    assert scan_diff(diff) == []


def test_clean_diff_has_no_findings() -> None:
    diff = '+def soma(a: int, b: int) -> int:\n+    return a + b\n'
    assert scan_diff(diff) == []


def test_placeholder_is_not_flagged() -> None:
    # placeholders curtos/óbvios não batem nos formatos de alta precisão (evita falso-positivo).
    diff = '+API_KEY = "changeme"\n+token = "sk-ccr-noop"\n'
    assert scan_diff(diff) == []


def test_dedups_repeated_secret() -> None:
    diff = f'+a = "{_GHP}"\n+b = "{_GHP}"\n'
    assert len(scan_diff(diff)) == 1


@pytest.mark.parametrize(
    "secret,expected",
    [
        ("sk-" + "a" * 24, "OpenAI/Anthropic key"),
        ("xoxb-" + "1" * 12, "Slack token"),
        ("sk_live_" + "a" * 24, "Stripe secret key"),
        ("AIza" + "a" * 35, "Google API key"),
    ],
)
def test_detects_each_provider_format(secret: str, expected: str) -> None:
    findings = scan_diff(f'+k = "{secret}"\n')
    assert any(f.pattern == expected for f in findings)


# --- heurística KEYED + entropia (formatos desconhecidos) ---

def test_entropy_flags_secret_named_key_with_random_value() -> None:
    diff = '+DB_PASSWORD = "xQ7v2Lp9Rz4Wk1Nf8Ht3Bc6"\n'  # chave secreta + valor de alta entropia
    findings = scan_diff(diff)
    assert any("heurística" in f.pattern for f in findings)


def test_entropy_ignores_low_entropy_placeholder() -> None:
    # placeholder repetitivo (baixa entropia) NÃO bloqueia — evita falso-positivo
    assert scan_diff('+password = "changeme-changeme"\n') == []


def test_entropy_ignores_short_value() -> None:
    assert scan_diff('+token = "abc123"\n') == []  # < 16 chars


def test_entropy_ignores_non_secret_key() -> None:
    # chave sem cara de segredo, mesmo com valor aleatório → não flaga (precisa dos DOIS sinais)
    assert scan_diff('+commit_sha = "xQ7v2Lp9Rz4Wk1Nf8Ht3Bc6"\n') == []
