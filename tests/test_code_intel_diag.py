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


def test_descarta_erro_de_uso_da_tool() -> None:
    # #226 bug: validate_build sem file/lang devolve "faltou 'lang' ou 'file'" — NÃO é diagnóstico
    assert format_diagnostics("faltou 'lang' ou 'file' para inferir a linguagem") == ""
    assert format_diagnostics("Error: missing 'file' attribute") == ""


def test_descarta_erro_de_config_do_code_intel() -> None:
    # #245 runaway: validate_build sem o typecheck configurado devolve erro de CONFIG — é o
    # code-intel pedindo setup ao operador, NÃO erro no código. Não pode ir pro modelo "corrigir".
    assert format_diagnostics("error: sem comando de build p/ 'typescript' (defina "
                              "TYPESCRIPT_CHECK_CMD)") == ""
    assert format_diagnostics("error: language 'python' not configured — run doctor --fix") == ""
    assert format_diagnostics("erro: workspace não configurado; defina PY_CHECK_CMD") == ""


def test_config_err_nao_mata_erro_real_de_ts() -> None:
    # guard: um erro REAL de TS não pode ser confundido com config (o filtro é específico)
    out = format_diagnostics("route.ts(3,1): error TS2345: Argument not assignable.")
    assert out.startswith("DIAGNÓSTICOS DO BUILD") and "TS2345" in out


def test_diagnostics_sem_file_nem_lang_nao_chama_tool() -> None:
    # guard: sem dica de linguagem, não chama validate_build (evita o erro de uso) → ""
    from roboto.app.code_intel_diag import code_intel_diagnostics

    assert code_intel_diagnostics("/tmp/qualquer", "") == ""
