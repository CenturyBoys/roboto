"""Assist determinístico de i18n (#247): parseia a chave EXATA do check:i18n e stuba nos locales."""

from __future__ import annotations

import json
from pathlib import Path

from roboto.app.i18n_assist import apply_i18n_stubs, parse_missing_i18n

_HOOK = (
    "✖ i18n — 2 erro(s) (bloqueia):\n"
    '  [key] t("version-checker.client-version-deprecated") em x.ts — ausente em: en, es, pt\n'
    '  [key] t("version-checker.breaking-changes") em y.ts — ausente em: en, es, pt\n'
)


def test_parse_missing_i18n_pega_chaves_exatas() -> None:
    keys = parse_missing_i18n(_HOOK)
    assert keys == [
        "version-checker.client-version-deprecated",
        "version-checker.breaking-changes",
    ]


def test_parse_vazio_sem_chaves() -> None:
    assert parse_missing_i18n("prettier --check ok, nada de i18n") == []


def _locale_dir(tmp_path: Path) -> Path:
    d = tmp_path / "apps" / "web" / "src" / "i18n" / "messages"
    d.mkdir(parents=True)
    for loc in ("en", "es", "pt"):
        (d / f"{loc}.json").write_text(json.dumps({"existing": {"k": "v"}}), encoding="utf-8")
    return d


def test_apply_stubs_adiciona_chave_aninhada_em_todos_locales(tmp_path: Path) -> None:
    d = _locale_dir(tmp_path)
    added = apply_i18n_stubs(str(tmp_path), _HOOK)
    assert set(added) == {
        "version-checker.client-version-deprecated",
        "version-checker.breaking-changes",
    }
    for loc in ("en", "es", "pt"):  # parity: em TODOS os locales, ANINHADO pelos pontos
        tree = json.loads((d / f"{loc}.json").read_text(encoding="utf-8"))
        vc = tree["version-checker"]
        assert "client-version-deprecated" in vc and "breaking-changes" in vc
        assert tree["existing"]["k"] == "v"  # não mexe no que já existe


def test_apply_stubs_noop_sem_locales(tmp_path: Path) -> None:
    assert apply_i18n_stubs(str(tmp_path), _HOOK) == []  # sem arquivos de locale → []


def test_apply_stubs_noop_sem_chaves(tmp_path: Path) -> None:
    _locale_dir(tmp_path)
    assert apply_i18n_stubs(str(tmp_path), "sem i18n aqui") == []
