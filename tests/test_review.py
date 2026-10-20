"""Gate de prontidão da issue (DoR) — check_issue_readiness (determinístico)."""

from __future__ import annotations

from roboto.agents.refiner import IssueDraft
from roboto.agents.review import check_issue_readiness

_READY_BODY = (
    "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n- [ ] faz z\n"
    "## DoD\n- [ ] testes + CI\n## Fora de escopo\nnada"
)


def test_complete_issue_is_ready() -> None:
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body=_READY_BODY))
    assert verdict.ready is True
    assert verdict.missing == []


def test_missing_sections_listed() -> None:
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body="## Contexto\nsó isso"))
    assert verdict.ready is False
    assert any("Escopo" in m for m in verdict.missing)
    assert any("Critérios de aceite" in m for m in verdict.missing)
    assert any("DoD" in m for m in verdict.missing)


def test_no_acceptance_checkbox_is_not_ready() -> None:
    # tem as seções mas nenhum item "- [ ]"
    body = "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\nfaz z\n## DoD\ntestes"
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body=body))
    assert verdict.ready is False
    assert any("- [ ]" in m for m in verdict.missing)


def test_empty_title_is_not_ready() -> None:
    verdict = check_issue_readiness(IssueDraft(title="  ", body=_READY_BODY))
    assert verdict.ready is False
    assert "título" in verdict.missing
