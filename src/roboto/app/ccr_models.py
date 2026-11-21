"""Lê os ids de modelo que o claude-code-router (ccr) sabe rotear — p/ o harness NÃO entregar ao
motor um id que o ccr responde ``unrecognized_model`` (o run morre em ~3s, sem sessão nativa e sem
motivo gravado; ver run #1039: o tier forte apontava p/ ``qwen3.8-27b``, ausente do ccr).

Determinismo-primeiro: validamos o modelo ANTES de rodar e caímos no base conhecido, em vez de
contar com o acerto da config. ``registered_models`` é **fail-open**: se não der p/ ler o ccr.config
(caminho diferente, arquivo ausente), devolve set vazio → o chamador NÃO bloqueia (não inventa
falha onde não sabe). Formato dos ids = ``provider,model`` (sintaxe de override que o ccr respeita).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _config_path() -> Path:
    """Caminho do ccr.config.json em uso. Env ``CCR_CONFIG`` > o do runtime
    (``~/.claude-code-router/config.json``, gerado pelo entrypoint) > o fonte do repo."""
    env = os.environ.get("CCR_CONFIG")
    if env:
        return Path(env)
    home = Path(os.path.expanduser("~/.claude-code-router/config.json"))
    if home.exists():
        return home
    return Path("/opt/roboto/poc/ccr.config.json")


def registered_models(path: str | os.PathLike[str] | None = None) -> set[str]:
    """Set de ids que o ccr roteia (``Providers[].models``), no formato ``provider,model`` e também
    sem o prefixo. Vazio se não der p/ ler — nesse caso o chamador deve FAZER FAIL-OPEN (usar o
    modelo como veio), pra não bloquear por desconhecer a config."""
    p = Path(path) if path else _config_path()
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return set()
    out: set[str] = set()
    providers = data.get("Providers") or data.get("providers") or []
    for prov in providers:
        name = prov.get("name", "")
        for m in prov.get("models", []):
            out.add(f"{name},{m}")
            out.add(m)  # tolera id citado sem o prefixo de provider
    return out


def pin_or_fallback(
    model: str, *, registered: set[str], fallback: str = "",
) -> tuple[str, str | None]:
    """Resolve o id a entregar ao motor. Usa ``model`` como está quando: é vazio (= default do
    ccr), o ccr não pôde ser lido (``registered`` vazio → fail-open), ou o id está registrado.
    Senão cai no ``fallback`` e devolve o MOTIVO (p/ logar/gravar no feed, não só "failed")."""
    if not model or not registered or model in registered:
        return model, None
    reason = (
        f"modelo forte '{model}' não está registrado no ccr (responderia unrecognized_model) — "
        f"caio no base '{fallback or '(default do ccr)'}' p/ o run não morrer sem motivo."
    )
    return fallback, reason
