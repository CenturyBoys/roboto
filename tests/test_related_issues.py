"""Injeção harness-driven do contexto de issues relacionadas: refs #N, leitura, bloco markdown."""

from __future__ import annotations

from roboto.app.related_issues import extract_issue_refs, related_issues_block
from roboto.orchestrator.model import Error
from roboto.result import Err, Ok, Result

_BODY = """## Pontos a cobrir
- Estabelecer prazo mínimo para notificar depreciação

Depende de #244

> Esqueleto do breakdown.

Parte do épico #67.
"""


class _StubGithub:
    """get_issue de teste: devolve (título, corpo) por número, ou Err p/ inacessível."""

    def __init__(self, issues: dict[int, tuple[str, str]]) -> None:
        self._issues = issues

    async def get_issue(self, repo: str, number: int) -> Result[tuple[str, str], Error]:
        if number not in self._issues:
            return Err(Error(kind="not_found", message=f"#{number}"))
        return Ok(self._issues[number])


def test_extract_refs_ordem_sem_repetir_sem_a_propria() -> None:
    assert extract_issue_refs(_BODY, self_id=245) == [244, 67]
    assert extract_issue_refs("vê #10, #10, #10") == [10]
    assert extract_issue_refs("#5 e #5", self_id=5) == []


def test_extract_refs_vazio_quando_nao_ha() -> None:
    assert extract_issue_refs("corpo sem referências") == []


async def test_block_injeta_corpo_das_relacionadas() -> None:
    github = _StubGithub(
        {244: ("Base versioning", "decidimos semver"), 67: ("Épico", "guarda-chuva")}
    )
    block = await related_issues_block("org/repo", _BODY, github.get_issue, self_id=245)
    assert "## Issues relacionadas" in block
    assert "NÃO edite estas issues" in block
    assert "#244 · Base versioning" in block
    assert "decidimos semver" in block
    assert "#67 · Épico" in block


async def test_block_vazio_sem_refs() -> None:
    github = _StubGithub({})
    assert await related_issues_block("org/repo", "sem refs", github.get_issue) == ""


async def test_block_degrada_pulando_issue_inacessivel() -> None:
    github = _StubGithub({244: ("Base", "ok")})  # #67 não existe → pulada
    block = await related_issues_block("org/repo", _BODY, github.get_issue, self_id=245)
    assert "#244 · Base" in block
    assert "#67" not in block


async def test_block_respeita_max_issues() -> None:
    corpo = " ".join(f"#{n}" for n in range(100, 110))
    github = _StubGithub({n: (f"T{n}", f"corpo {n}") for n in range(100, 110)})
    block = await related_issues_block("org/repo", corpo, github.get_issue, max_issues=3)
    assert block.count("###") == 3
