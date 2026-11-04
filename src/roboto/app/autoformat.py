"""Auto-format antes do commit (determinismo primeiro, F/B).

O motor costuma ESQUECER de formatar, e o pre-commit hook do repo (ex.: `prettier --check`) barra o
commit — foi o que travou o #232 em várias tentativas, mesmo com o aprendizado injetando o motivo.
Em vez de depender do modelo lembrar, o harness roda o formatador nos arquivos ALTERADOS antes de
commitar. Best-effort: repo sem prettier / comando ausente → no-op (nunca levanta, nunca derruba o
ciclo). A pura `prettier_targets` é testável; o IO é tolerante.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

# extensões que o prettier formata (p/ não chamar o prettier em binário/imagem/etc.)
_PRETTIER_EXT = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".md", ".mdx",
    ".css", ".scss", ".less", ".html", ".vue", ".yml", ".yaml",
}
_PRETTIER_CFG = (
    ".prettierrc", ".prettierrc.json", ".prettierrc.js", ".prettierrc.cjs",
    ".prettierrc.yaml", ".prettierrc.yml", "prettier.config.js", "prettier.config.cjs",
)


def uses_prettier(workdir: str) -> bool:
    """O repo usa prettier? (arquivo de config OU dependência/script no package.json)."""
    root = Path(workdir)
    if any((root / f).exists() for f in _PRETTIER_CFG):
        return True
    pkg = root / "package.json"
    if not pkg.exists():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    deps = {**data.get("devDependencies", {}), **data.get("dependencies", {})}
    if "prettier" in deps:
        return True
    return "prettier" in json.dumps(data.get("scripts", {}))


def prettier_targets(changed: list[str]) -> list[str]:
    """Filtra os arquivos alterados para os que o prettier formata (dedup, ordem estável)."""
    out: list[str] = []
    for f in changed:
        if Path(f).suffix.lower() in _PRETTIER_EXT and f not in out:
            out.append(f)
    return out


def _nearest_workspace(workdir: str, file: str) -> str:
    """Workspace do arquivo = dir ancestral mais próximo com `package.json` (relativo ao workdir).
    '' = raiz. No monorepo é onde vive o prettier/config que o hook usa. Pura (só checa arquivo)."""
    root = Path(workdir)
    d = (root / file).parent
    while True:
        if (d / "package.json").exists():
            rel = os.path.relpath(d, root)
            return "" if rel == "." else rel
        if d.resolve() == root.resolve() or root.resolve() not in d.resolve().parents:
            return ""
        d = d.parent


def prettier_groups(workdir: str, targets: list[str]) -> dict[str, list[str]]:
    """Agrupa os alvos pelo WORKSPACE (monorepo #228): roda o prettier de cada workspace, com os
    paths relativos a ele — senão o prettier da raiz não casa com a config do workspace e o hook
    `--check` barra o commit. Chave '' = raiz. Pura."""
    groups: dict[str, list[str]] = {}
    for f in targets:
        ws = _nearest_workspace(workdir, f)
        rel = os.path.relpath(f, ws) if ws else f
        groups.setdefault(ws, []).append(rel)
    return groups


async def _changed_files(workdir: str) -> list[str]:
    proc = await asyncio.create_subprocess_exec(
        "git", "status", "--porcelain", cwd=workdir,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    files: list[str] = []
    for ln in out.decode(errors="replace").splitlines():
        p = ln[3:].strip()  # "XY path"
        if "->" in p:  # rename: "antigo -> novo"
            p = p.split("->")[-1].strip()
        if p:
            files.append(p.strip('"'))
    return files


async def autoformat(workdir: str) -> list[str]:
    """Formata (prettier --write) os arquivos alterados do repo. Devolve os que mandou formatar.
    Best-effort: repo sem prettier / sem alvos / comando falho → ``[]`` (nunca levanta)."""
    if not uses_prettier(workdir):
        return []
    try:
        targets = prettier_targets(await _changed_files(workdir))
        if not targets:
            return []
        # monorepo (#228): roda o prettier POR workspace, no cwd dele — resolve o binário + a config
        # locais (a mesma do pre-commit `--check`). Da raiz não casava → o hook barrava o commit.
        done: list[str] = []
        for ws, files in prettier_groups(workdir, targets).items():
            cwd = str(Path(workdir) / ws) if ws else workdir
            proc = await asyncio.create_subprocess_exec(
                "pnpm", "exec", "prettier", "--write", "--ignore-unknown", *files,
                cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if (proc.returncode or 0) == 0:
                done.extend(f if not ws else f"{ws}/{f}" for f in files)
        return done
    except Exception:  # noqa: BLE001 — best-effort: formatação nunca derruba o ciclo
        return []
