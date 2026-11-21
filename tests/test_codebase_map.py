"""Mapa determinístico do repo (Ponytail): git ls-files + símbolos top-level, reuse-first."""

from __future__ import annotations

from pathlib import Path

from roboto.app.codebase_map import build_codebase_map


def _seed(tmp_path: Path) -> None:
    (tmp_path / "lib").mkdir()
    (tmp_path / "app").mkdir()
    (tmp_path / "lib" / "util.py").write_text("def helper():\n    pass\nclass Thing:\n    pass\n")
    (tmp_path / "app" / "main.ts").write_text("export function run() {}\nexport const X = 1\n")
    (tmp_path / "README.md").write_text("# doc\n")  # sem linguagem → ignorado


def _lister(files: list[str]):  # type: ignore[no-untyped-def]
    return lambda _wd: files


def test_mapa_agrupa_por_dir_e_extrai_simbolos(tmp_path: Path) -> None:
    _seed(tmp_path)
    m = build_codebase_map(
        str(tmp_path), lister=_lister(["lib/util.py", "app/main.ts", "README.md"])
    )
    assert "lib: Thing, helper" in m  # ordenado (ASCII: maiúsculas antes)
    assert "app: X, run" in m
    assert "README" not in m  # não-código ignorado
    assert m.startswith("REPO MAP")


def test_pastas_compartilhadas_vem_primeiro(tmp_path: Path) -> None:
    _seed(tmp_path)
    m = build_codebase_map(str(tmp_path), lister=_lister(["app/main.ts", "lib/util.py"]))
    # `lib` (compartilhada) aparece antes de `app` mesmo vindo depois na listagem
    assert m.index("lib:") < m.index("app:")


def test_budget_corta_e_sinaliza(tmp_path: Path) -> None:
    for i in range(10):
        (tmp_path / f"d{i}").mkdir()
        (tmp_path / f"d{i}" / "m.py").write_text(f"def f{i}_aaaaaaaaaaaaaaaaaaaa():\n    pass\n")
    files = [f"d{i}/m.py" for i in range(10)]
    m = build_codebase_map(str(tmp_path), budget=120, lister=_lister(files))
    assert "omitidos pelo budget" in m


def test_sem_codigo_ou_erro_vazio(tmp_path: Path) -> None:
    assert build_codebase_map(str(tmp_path), lister=_lister(["README.md"])) == ""

    def _boom(_wd: str) -> list[str]:
        raise RuntimeError("sem git")

    assert build_codebase_map(str(tmp_path), lister=_boom) == ""  # fail-open
