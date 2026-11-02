"""Risk-tiering determinístico (Trilha H — jev-guard)."""

from __future__ import annotations

from roboto.app.jev_guard import assess, files_from_diff


def test_sensitive_path_is_high_risk() -> None:
    r = assess(["src/db/migrations/0003_add.sql"])
    assert r.level == "alto" and r.escalate is True
    assert any("migrations" in m for m in r.reasons)


def test_ci_and_infra_are_high() -> None:
    assert assess([".github/workflows/ci.yml"]).level == "alto"
    assert assess(["infra/main.tf"]).level == "alto"
    assert assess(["Dockerfile"]).level == "alto"
    assert assess(["src/auth/login.py"]).level == "alto"


def test_wide_change_is_medium() -> None:
    files = [f"src/mod/f{i}.py" for i in range(9)]  # > limiar, nenhum sensível
    r = assess(files)
    assert r.level == "medio" and r.escalate is False
    assert "9 arquivos" in r.reasons[0]


def test_small_normal_change_is_low() -> None:
    r = assess(["src/util/strings.py", "tests/test_strings.py"])
    assert r.level == "baixo" and r.reasons == [] and r.escalate is False


def test_reasons_are_deduped() -> None:
    r = assess(["a/migrations/1.sql", "b/migrations/2.sql"])
    assert r.level == "alto"
    assert sum("migrations" in m for m in r.reasons) == 1  # motivo único


def test_files_from_diff_extracts_b_side() -> None:
    diff = (
        "diff --git a/src/x.py b/src/x.py\n+novo\n"
        "diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml\n+ci\n"
    )
    files = files_from_diff(diff)
    assert files == ["src/x.py", ".github/workflows/ci.yml"]
    assert assess(files).level == "alto"  # pega o workflow via diff


def test_empty_diff_is_low() -> None:
    assert assess(files_from_diff("")).level == "baixo"
