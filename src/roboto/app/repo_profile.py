"""Perfil do repo-alvo (trilhas G/H): o que o motor precisa p/ OPERAR o repo como um dev faria —
gerenciador, se é monorepo, scripts (test/lint/build), que as deps JÁ estão instaladas (bootstrap).

DETERMINÍSTICO (sem LLM, pilar do projeto): lê `package.json`/workspace + o `/tmp/env-status` do
bootstrap. Vira um bloco de texto que (a) o daemon grava no **second brain** (`remember`) e (b) os
prompts de refino/implementação injetam — pro motor NÃO começar cru nem flailar em "como rodar o
teste" (era o que fazia ele inventar scripts `.cjs` e reinstalar deps à toa).
"""

from __future__ import annotations

import json
import os
import re
from fnmatch import fnmatch
from pathlib import Path

_ENV_STATUS = Path("/tmp/env-status")  # gravado pelo bootstrap: "✅ PRONTO ..." / "❌ FALHOU ..."
_SCRIPT_KEYS = ("test", "lint", "typecheck", "build", "dev")

# AGENTS.md é o padrão de fato (E); CLAUDE.md costuma só apontar pra ele — por isso a ordem.
_CONVENTION_FILES = ("AGENTS.md", "CLAUDE.md")
# teto de token (F): o AGENTS.md do repo-alvo entra no prompt de impl; o alvo não é nosso, então
# capamos pra não estourar o orçamento. ~6k chars ≈ 1.5k tokens.
_CONVENTIONS_MAX_CHARS = 6000


def read_agents_conventions(workdir: str, *, max_chars: int = _CONVENTIONS_MAX_CHARS) -> str:
    """Lê o AGENTS.md (ou CLAUDE.md) do repo-alvo e devolve um bloco pronto pra injetar no prompt.

    DETERMINÍSTICO (E, determinismo primeiro): o harness injeta as convenções do repo-alvo em vez de
    mandar o motor "ler o AGENTS.md você mesmo" — que gasta token (F) e pode ser ignorado. Capado a
    `max_chars` (orçamento de token); se truncar, aponta pro arquivo completo. Vazio se não existir.
    """
    root = Path(workdir)
    for name in _CONVENTION_FILES:
        path = root / name
        try:
            content = path.read_text(errors="replace").strip()
        except OSError:
            continue
        if not content:
            continue
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars].rstrip()
        header = f"CONVENÇÕES DO REPO-ALVO ({name} — siga à risca):"
        footer = (
            f"\n[… truncado em {max_chars} de {len(path.read_text(errors='replace'))} chars — "
            f"o {name} completo está no cwd]"
            if truncated
            else ""
        )
        return f"{header}\n{content}{footer}"
    return ""


def build_repo_profile(workdir: str, *, env_status_path: Path = _ENV_STATUS) -> str:
    """Bloco de texto com como operar o repo. Vazio se não for projeto JS (nada a dizer)."""
    root = Path(workdir)
    pkg = root / "package.json"
    if not pkg.exists():
        return ""
    try:
        data = json.loads(pkg.read_text(errors="replace"))
    except (OSError, ValueError):
        return ""

    pm_full = str(data.get("packageManager", "")).strip()
    pm = pm_full.split("@")[0] or "npm"
    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
    is_mono = (root / "pnpm-workspace.yaml").exists() or "workspaces" in data
    has_agents = (root / "AGENTS.md").exists()
    env_status = ""
    try:
        env_status = env_status_path.read_text(errors="replace").strip()
    except OSError:
        pass

    lines = ["PERFIL DO REPO (determinístico — ambiente já preparado pelo bootstrap):"]
    lines.append(f"- Gerenciador: {pm_full or pm}" + (" | MONOREPO" if is_mono else ""))
    if "PRONTO" in env_status:
        lines.append("- Deps JÁ INSTALADAS pelo bootstrap — NÃO rode install de novo.")
    elif env_status:
        lines.append(f"- Ambiente: {env_status}")
    key = {k: scripts[k] for k in _SCRIPT_KEYS if isinstance(scripts, dict) and k in scripts}
    if key:
        lines.append("- Scripts (raiz): " + ", ".join(f"{k}=`{v}`" for k, v in key.items()))
    if is_mono:
        lines.append(
            f"- Em monorepo, rode por pacote: `{pm} --filter <pacote> <script>` ou recursivo "
            f"`{pm} -r <script>`."
        )
    lines.append(
        f"- Rode lint/testes PELO {pm} (como um dev na máquina). NUNCA crie scripts de teste "
        "avulsos (.cjs/.js) nem reinstale deps — use o que o repo já define."
    )
    if has_agents:
        lines.append("- Leia o AGENTS.md para as convenções do repo.")
    return "\n".join(lines)


# --- teste-exemplo (G): o motor NÃO redescobre "como os testes são feitos" — o harness mostra -----

_TEST_GLOBS = (
    "test_*.py", "*_test.py", "*.test.ts", "*.spec.ts", "*.test.tsx",
    "*.test.js", "*.spec.js", "*.test.jsx",
)
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "dist", "build", ".venv", "venv", "__pycache__",
    "vendor", ".next", "coverage", ".turbo",
})
_TEST_SAMPLE_MAX = 1200


def format_test_sample(rel_path: str, content: str, *, max_chars: int = _TEST_SAMPLE_MAX) -> str:
    """Bloco do teste-exemplo (PURA, testável). Vazio se não há conteúdo."""
    excerpt = content.strip()
    if not excerpt:
        return ""
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip() + "\n… (truncado)"
    return (
        f"EXEMPLO DE TESTE DO REPO ({rel_path}) — SIGA ESTE PADRÃO (framework, estrutura, nomes, "
        f"mocking); NÃO reinvente nem crie runner avulso:\n```\n{excerpt}\n```"
    )


def _test_files(root: Path, *, max_dirs: int = 3000, cap: int = 300) -> list[Path]:
    """Lista testes (bounded): poda dirs pesados/ocultos; cap de dirs e de arquivos."""
    out: list[Path] = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        seen += 1
        if seen > max_dirs or len(out) >= cap:
            break
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
        for fn in sorted(filenames):
            if any(fnmatch(fn, g) for g in _TEST_GLOBS):
                out.append(Path(dirpath) / fn)
    return out


def _tokens(text: str) -> set[str]:
    """Tokens de ≥3 chars (minúsculos) — casa termos da issue com partes do path do teste."""
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) >= 3}


def _pick_test_file(files: list[Path], root: Path, hints: str) -> Path | None:
    """Escolhe por RELEVÂNCIA: sobreposição de tokens do path do teste com os termos da issue.
    Empate / sem hints → determinístico (mais raso, depois alfabético) = o 1º estável de antes."""
    if not files:
        return None
    hint_tokens = _tokens(hints)

    def key(p: Path) -> tuple[int, int, str]:
        rel = str(p.relative_to(root))
        score = len(_tokens(rel) & hint_tokens) if hint_tokens else 0
        return (-score, len(p.parts), rel)  # relevância desc → raso → alfabético

    return sorted(files, key=key)[0]


def sample_test_excerpt(workdir: str, *, hints: str = "", max_chars: int = _TEST_SAMPLE_MAX) -> str:
    """Acha 1 teste-exemplo e devolve o bloco pro prompt. Com `hints` (texto da issue), prefere o
    teste mais RELEVANTE (path casa com os termos da issue); sem hints, o mais raso/alfabético.
    Best-effort ("" se não há teste)."""
    root = Path(workdir)
    chosen = _pick_test_file(_test_files(root), root, hints)
    if chosen is None:
        return ""
    try:
        content = chosen.read_text(errors="replace")
        rel = str(chosen.relative_to(root))
    except (OSError, ValueError):
        return ""
    return format_test_sample(rel, content, max_chars=max_chars)
