"""Guard do modelo forte vs. ccr: valida ANTES de rodar p/ não morrer com unrecognized_model."""

from __future__ import annotations

import json
from pathlib import Path

from roboto.app.ccr_models import pin_or_fallback, registered_models

_CFG = {
    "Providers": [
        {
            "name": "openrouter",
            "models": ["qwen/qwen3-coder-next", "qwen/qwen3.8-27b"],
        }
    ],
}


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "ccr.config.json"
    p.write_text(json.dumps(_CFG))
    return p


def test_registered_models_tem_prefixo_e_sem(tmp_path: Path) -> None:
    reg = registered_models(_write(tmp_path))
    assert "openrouter,qwen/qwen3.8-27b" in reg
    assert "qwen/qwen3.8-27b" in reg  # tolera citação sem provider


def test_registered_models_fail_open_arquivo_ausente(tmp_path: Path) -> None:
    # arquivo inexistente / ilegível → set vazio (o chamador faz fail-open, não bloqueia)
    assert registered_models(tmp_path / "nao-existe.json") == set()


def test_pin_mantem_modelo_registrado(tmp_path: Path) -> None:
    reg = registered_models(_write(tmp_path))
    model, reason = pin_or_fallback("openrouter,qwen/qwen3.8-27b", registered=reg)
    assert model == "openrouter,qwen/qwen3.8-27b"
    assert reason is None


def test_pin_cai_no_fallback_quando_desconhecido(tmp_path: Path) -> None:
    reg = registered_models(_write(tmp_path))
    model, reason = pin_or_fallback("openrouter,qwen/inexistente", registered=reg)
    assert model == ""  # base/default do ccr
    assert reason is not None and "unrecognized_model" in reason


def test_pin_fail_open_quando_ccr_nao_lido() -> None:
    # registered vazio = não conseguimos ler o ccr → usa o modelo como veio (não inventa falha)
    model, reason = pin_or_fallback("openrouter,qwen/qualquer", registered=set())
    assert model == "openrouter,qwen/qualquer"
    assert reason is None


def test_pin_modelo_vazio_e_noop() -> None:
    # "" = default do ccr; nunca vira fallback nem motivo
    model, reason = pin_or_fallback("", registered={"openrouter,x"})
    assert model == ""
    assert reason is None
