"""Tipagem de task (#158): classificador determinístico (natureza + tamanho)."""

from __future__ import annotations

from roboto.app.task_class import TaskType, classificar_task

_DEV = "## Critérios de aceite\n- [ ] faz X em `apps/web/foo.ts`\n- [ ] testa Y"


def test_desenvolvimento_com_criterio_e_arquivo() -> None:
    c = classificar_task("feat: implementar X", _DEV)
    assert c.task_type is TaskType.DESENVOLVIMENTO
    assert c.confianca == "alta"


def test_definicao_por_keyword_sem_criterio() -> None:
    c = classificar_task("Decidir arquitetura (ADR)", "Precisamos decidir o ADR.")
    assert c.task_type is TaskType.DEFINICAO
    assert c.confianca == "alta"  # keyword -> confiante -> o gate bloqueia


def test_esqueleto_sem_keyword_e_ambiguo() -> None:
    c = classificar_task("feat: algo", "só um esqueleto, sem nada")
    assert c.task_type is TaskType.DEFINICAO
    assert c.confianca == "media"  # ambíguo (dev incompleto?) -> NÃO bloqueia (gate exige alta)


def test_spike_por_keyword() -> None:
    c = classificar_task("Investigar viabilidade de X", "Spike pra explorar.")
    assert c.task_type is TaskType.SPIKE


def test_size_escala_com_mais_itens() -> None:
    big = "## Critérios\n" + "\n".join(f"- [ ] item {i} em `a{i}.ts`" for i in range(12))
    c = classificar_task("feat: grande", big)
    assert c.task_type is TaskType.DESENVOLVIMENTO
    assert c.size in ("L", "XL")
