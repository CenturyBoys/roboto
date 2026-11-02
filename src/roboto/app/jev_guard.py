"""Risk-tiering determinístico (Trilha H — jev-guard).

O output do motor é PROPOSTA; antes do gate humano (merge), o fleet **classifica o risco** da
mudança pelos ARQUIVOS que ela toca — determinístico, sem LLM. O nível é **surfado** (badge no
cockpit + seção no PR) pra o humano saber onde olhar com mais cuidado. Conservador: **não bloqueia**
o fluxo normal; só chama atenção. Escalada automática (alto → espera OK) fica como toggle follow-up.

`alto` = toca caminho sensível (migrations, CI/CD, infra, deploy, auth/segurança, deps). `medio` =
mudança ampla (muitos arquivos). `baixo` = o resto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# (regex no path, motivo legível). Caminhos cuja mudança tem impacto alto/irreversível na prática.
_SENSITIVE: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(^|/)migrations?/"), "mexe em migrations (schema do banco)"),
    (re.compile(r"(^|/)\.github/workflows/"), "mexe em CI/CD (workflows)"),
    (re.compile(r"(^|/)(Dockerfile|docker-compose)", re.I), "mexe em build/runtime (Docker)"),
    (re.compile(r"\.tf$|(^|/)terraform/"), "mexe em infraestrutura (IaC)"),
    (re.compile(r"(^|/)(deploy|k8s|helm|charts)/", re.I), "mexe em deploy"),
    (re.compile(r"auth|security|secret|credential|senha|password|login", re.I),
     "toca autenticação/segurança"),
    (re.compile(r"(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|Cargo\.lock)$"),
     "mexe em dependências (lockfile)"),
)
# acima disto, uma mudança é "ampla" mesmo sem caminho sensível → risco médio.
_WIDE_FILE_COUNT = 8


@dataclass(frozen=True)
class RiskAssessment:
    """Nível de risco + motivos (pra surfar no PR/cockpit). `escalate` = candidato a gate humano."""

    level: str  # "baixo" | "medio" | "alto"
    reasons: list[str] = field(default_factory=list)

    @property
    def escalate(self) -> bool:
        return self.level == "alto"


def files_from_diff(diff: str) -> list[str]:
    """Extrai os paths tocados de um diff unificado (linhas `diff --git a/x b/x`)."""
    files: list[str] = []
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            # 'diff --git a/path b/path' → pega o lado b/
            parts = line.split(" b/", 1)
            if len(parts) == 2 and parts[1] not in files:
                files.append(parts[1])
    return files


def assess(files: list[str]) -> RiskAssessment:
    """Classifica o risco da mudança pelos arquivos tocados (determinístico)."""
    reasons: list[str] = []
    for path in files:
        for rx, motivo in _SENSITIVE:
            if rx.search(path) and motivo not in reasons:
                reasons.append(motivo)
    if reasons:
        return RiskAssessment(level="alto", reasons=reasons)
    if len(files) > _WIDE_FILE_COUNT:
        return RiskAssessment(level="medio", reasons=[f"mudança ampla ({len(files)} arquivos)"])
    return RiskAssessment(level="baixo", reasons=[])
