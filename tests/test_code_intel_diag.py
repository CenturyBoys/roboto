"""Diagnostics harness-driven (#226): formatação só injeta quando há sinal de erro (conservador)."""

from __future__ import annotations

from roboto.app.code_intel_diag import format_diagnostics


def test_formata_quando_ha_erro() -> None:
    raw = "src/app/api/version/route.ts(12,7): error TS2307: Cannot find module './schema'."
    out = format_diagnostics(raw)
    assert out.startswith("DIAGNÓSTICOS DO BUILD")
    assert "TS2307" in out
    assert "route.ts" in out


def test_vazio_quando_build_ok() -> None:
    # sem sinal de erro → não injeta (não trata "build ok" como diagnóstico)
    assert format_diagnostics("Build succeeded. 0 errors.") == ""
    assert format_diagnostics("") == ""
    assert format_diagnostics("   \n  ") == ""


def test_trunca_diag_longo() -> None:
    raw = "error: " + "x" * 5000
    out = format_diagnostics(raw, max_chars=200)
    assert "truncado" in out
    assert len(out) < 500
