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
        proc = await asyncio.create_subprocess_exec(
            "pnpm", "exec", "prettier", "--write", "--ignore-unknown", *targets,
            cwd=workdir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return targets if (proc.returncode or 0) == 0 else []
    except Exception:  # noqa: BLE001 — best-effort: formatação nunca derruba o ciclo
        return []
