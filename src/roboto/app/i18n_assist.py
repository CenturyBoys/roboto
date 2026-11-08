"""Assist DETERMINÍSTICO de i18n pré-commit (determinismo primeiro, B/#247).

O motor escreve `t("ns.key")` no código mas NÃO adiciona a chave nos locales — pior, inventa um
nome DIFERENTE (drift kebab↔camel) → o `check:i18n` barra o commit pra sempre, mesmo no modelo
forte (medido na exec #80/#81). A chave faltando NÃO é adivinhação: o hook a ENTREGA. Então o
harness parseia a chave EXATA e a stuba nos locales — imune ao drift do modelo (igual ao autoformat
do prettier). Merge é gate humano → o humano revisa/traduz os stubs.

Repo-shaped mas discovery genérico: acha os JSON de locale (stems de 2 letras tipo en/es/pt num
mesmo dir), seta a chave ANINHADA pelos pontos, e adiciona a TODOS os locales (parity). Best-effort:
sem locales / parse falho → no-op (nunca derruba o ciclo).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# linha do check:i18n: `[key] t("ns.key") em arquivo — ausente em: en, es, pt`
_KEY_RE = re.compile(r'\[key\]\s*t\(\s*["\']([^"\']+)["\']\s*\)')
_LOCALE_STEM = re.compile(r"^[a-z]{2}([-_][A-Za-z]{2})?$")  # en, pt, es, pt-BR...


def parse_missing_i18n(hook_output: str) -> list[str]:
    """Chaves `t("...")` que o check:i18n apontou como faltando (únicas, ordem estável). Pura."""
    out: list[str] = []
    for m in _KEY_RE.finditer(hook_output):
        k = m.group(1).strip()
        if k and k not in out:
            out.append(k)
    return out


def _humanize(dotted_key: str) -> str:
    """Valor-stub legível a partir da folha da chave (ex.: 'client-version-x' → 'Client version x').
    Não é tradução — é placeholder p/ o humano revisar no PR (merge é gate humano)."""
    leaf = dotted_key.split(".")[-1]
    words = re.split(r"[-_]", leaf)
    phrase = " ".join(w for w in words if w).strip()
    return phrase[:1].upper() + phrase[1:] if phrase else dotted_key


def _set_nested(tree: dict[str, object], dotted_key: str, value: str) -> bool:
    """Seta a chave ANINHADA (pontos → objetos) se ainda não existe. True se adicionou."""
    parts = dotted_key.split(".")
    cur = tree
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    if parts[-1] in cur:
        return False
    cur[parts[-1]] = value
    return True


def _find_locale_files(workdir: str) -> list[Path]:
    """JSON de locale: stems de 2 letras (en/es/pt...) que são dict, agrupados pelo dir com MAIS
    deles (o diretório de mensagens do repo). Ignora node_modules."""
    groups: dict[Path, list[Path]] = {}
    for p in Path(workdir).rglob("*.json"):
        if "node_modules" in p.parts:
            continue
        if not _LOCALE_STEM.match(p.stem):
            continue
        try:
            if isinstance(json.loads(p.read_text(encoding="utf-8")), dict):
                groups.setdefault(p.parent, []).append(p)
        except (ValueError, OSError):
            continue
    if not groups:
        return []
    best = max(groups, key=lambda d: len(groups[d]))
    return sorted(groups[best])


def apply_i18n_stubs(workdir: str, hook_output: str) -> list[str]:
    """Stuba as chaves faltando em TODOS os locales (parity). Devolve as chaves adicionadas.
    Best-effort: sem chave/locale ou erro → []. Determinístico — usa a chave EXATA do hook."""
    keys = parse_missing_i18n(hook_output)
    if not keys:
        return []
    locale_files = _find_locale_files(workdir)
    if not locale_files:
        return []
    added: set[str] = set()
    for lf in locale_files:
        try:
            tree = json.loads(lf.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        changed = False
        for key in keys:
            if _set_nested(tree, key, _humanize(key)):
                added.add(key)
                changed = True
        if changed:
            try:
                lf.write_text(
                    json.dumps(tree, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            except OSError:
                continue
    return sorted(added)
