"""Validação determinística de pré-condições do runtime (Trilha K).

Antes de o daemon começar a trabalhar, checa o que faz o container **flailar** se faltar: env
obrigatório, workdir existente/gravável, disco mínimo. Determinístico (sem LLM) — falha cedo com
mensagem clara em vez de o motor descobrir no meio da task. Não-bloqueante: loga o resultado (a
config crítica já é validada em `load_config`); aqui é a camada de infra/acesso.

Puro e testável: recebe os valores já lidos (env, caminho, disco livre) e só decide — o I/O (ler
`os.environ`, `shutil.disk_usage`) fica no chamador (runtime).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class PreflightResult:
    checks: list[PreflightCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def failures(self) -> list[PreflightCheck]:
        return [c for c in self.checks if not c.ok]


def check(
    *,
    env: Mapping[str, str],
    required_keys: tuple[str, ...],
    workdir: str,
    min_disk_mb: int = 0,
    disk_free_mb: int | None = None,
) -> PreflightResult:
    """Avalia as pré-condições. `disk_free_mb=None` pula o check de disco (não medido)."""
    checks: list[PreflightCheck] = []
    for k in required_keys:
        present = bool(env.get(k))
        checks.append(PreflightCheck(f"env:{k}", present, "ok" if present else "faltando"))
    wd = Path(workdir)
    exists = wd.is_dir()
    checks.append(PreflightCheck("workdir", exists, str(wd) if exists else f"{wd} não existe"))
    if disk_free_mb is not None and min_disk_mb > 0:
        enough = disk_free_mb >= min_disk_mb
        checks.append(
            PreflightCheck("disco", enough, f"{disk_free_mb}MB livre (mín {min_disk_mb}MB)")
        )
    return PreflightResult(checks=checks)
