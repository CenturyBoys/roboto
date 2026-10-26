"""Perfil do repo-alvo (trilhas G/H): o que o motor precisa p/ OPERAR o repo como um dev faria —
gerenciador, se é monorepo, scripts (test/lint/build), que as deps JÁ estão instaladas (bootstrap).

DETERMINÍSTICO (sem LLM, pilar do projeto): lê `package.json`/workspace + o `/tmp/env-status` do
bootstrap. Vira um bloco de texto que (a) o daemon grava no **second brain** (`remember`) e (b) os
prompts de refino/implementação injetam — pro motor NÃO começar cru nem flailar em "como rodar o
teste" (era o que fazia ele inventar scripts `.cjs` e reinstalar deps à toa).
"""

from __future__ import annotations

import json
from pathlib import Path

_ENV_STATUS = Path("/tmp/env-status")  # gravado pelo bootstrap: "✅ PRONTO ..." / "❌ FALHOU ..."
_SCRIPT_KEYS = ("test", "lint", "typecheck", "build", "dev")


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
