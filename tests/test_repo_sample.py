"""Teste-exemplo do repo (G/#224): formatação pura + descoberta determinística com poda."""

from __future__ import annotations

from pathlib import Path

from roboto.app.repo_profile import format_test_sample, sample_test_excerpt


def test_format_test_sample_monta_bloco() -> None:
    b = format_test_sample("tests/test_x.py", "def test_ok():\n    assert 1 == 1\n")
    assert "EXEMPLO DE TESTE DO REPO (tests/test_x.py)" in b
    assert "def test_ok" in b
    assert "```" in b


def test_format_test_sample_trunca() -> None:
    b = format_test_sample("t.py", "x" * 5000, max_chars=100)
    assert "truncado" in b
    assert len(b) < 400


def test_format_test_sample_vazio() -> None:
    assert format_test_sample("t.py", "   \n  ") == ""


def test_sample_test_excerpt_acha_e_poda_node_modules(tmp_path: Path) -> None:
    # decoy em node_modules NÃO deve ser escolhido; o teste raso de tests/ sim
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "test_decoy.py").write_text("# nao use este")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_real.py").write_text("def test_real():\n    assert True\n")

    block = sample_test_excerpt(str(tmp_path))
    assert "test_real.py" in block
    assert "test_decoy" not in block
    assert "def test_real" in block


def test_sample_test_excerpt_vazio_sem_teste(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')")
    assert sample_test_excerpt(str(tmp_path)) == ""


def test_sample_test_excerpt_escolhe_por_relevancia(tmp_path: Path) -> None:
    # dois testes; o hint da issue (menciona "payments") deve puxar o de payments, não o de auth
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "test_login.py").write_text("def test_login():\n    assert True\n")
    (tmp_path / "payments").mkdir()
    (tmp_path / "payments" / "test_charge.py").write_text("def test_charge():\n    assert True\n")

    rel = sample_test_excerpt(str(tmp_path), hints="Implementar reembolso no módulo de payments")
    assert "payments/test_charge.py" in rel
    # sem hint, cai no determinístico (auth vem antes alfabeticamente)
    neutro = sample_test_excerpt(str(tmp_path))
    assert "auth/test_login.py" in neutro
