"""Auto-format antes do commit (F/B): detecção de prettier + filtro de alvos."""

from __future__ import annotations

import json
from pathlib import Path

from roboto.app.autoformat import autoformat, prettier_targets, uses_prettier


def test_prettier_targets_filtra_por_extensao() -> None:
    alterados = [
        "scripts/check-logs.mjs", "src/a.ts", "README.md", "logo.png",
        "Makefile", "styles.css", "data.bin",
    ]
    alvos = prettier_targets(alterados)
    assert alvos == ["scripts/check-logs.mjs", "src/a.ts", "README.md", "styles.css"]


def test_prettier_targets_dedup() -> None:
    assert prettier_targets(["a.ts", "a.ts", "b.js"]) == ["a.ts", "b.js"]


def test_uses_prettier_por_devdependency(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"devDependencies": {"prettier": "^3.0.0"}}), encoding="utf-8"
    )
    assert uses_prettier(str(tmp_path)) is True


def test_uses_prettier_por_config(tmp_path: Path) -> None:
    (tmp_path / ".prettierrc").write_text("{}", encoding="utf-8")
    assert uses_prettier(str(tmp_path)) is True


def test_uses_prettier_false_sem_sinais(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
    assert uses_prettier(str(tmp_path)) is False
    assert uses_prettier(str(tmp_path / "nao-existe")) is False


async def test_autoformat_noop_sem_prettier(tmp_path: Path) -> None:
    # repo sem prettier → não tenta formatar, devolve [] (best-effort, não levanta)
    (tmp_path / "package.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
    assert await autoformat(str(tmp_path)) == []


def test_prettier_groups_monorepo(tmp_path: Path) -> None:
    # #228: arquivo em apps/web/ agrupa no workspace (path relativo a ele); raiz fica em ''
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "apps" / "web").mkdir(parents=True)
    (tmp_path / "apps" / "web" / "package.json").write_text("{}")
    from roboto.app.autoformat import prettier_groups

    g = prettier_groups(str(tmp_path), ["apps/web/src/x.ts", "scripts/root.ts"])
    assert g["apps/web"] == ["src/x.ts"]  # workspace: path relativo ao workspace
    assert g[""] == ["scripts/root.ts"]  # raiz (nenhum package.json mais próximo que a raiz)
