"""Tipagem de task (Trilha A, #158): natureza da task + tamanho, com GATE anti-codar-definição.

Distinto do `tiering` (que escolhe a FORÇA do modelo) — aqui classificamos a NATUREZA:
- `definicao` — produz spec/decisão (ADR/RFC), NÃO código. "Done" = spec. Não vai pra impl.
- `desenvolvimento` — produz código + testes. Exige critério verificável.
- `spike` — investigação/protótipo descartável (time-boxed). "Done" = achados documentados.

**Determinismo primeiro:** regras CLARAS e testáveis (keywords + estrutura). O Jev (LLM barato)
entra só como ESCALADA quando a confiança é baixa; o núcleo aqui é sem LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class TaskType(StrEnum):
    DEFINICAO = "definicao"
    DESENVOLVIMENTO = "desenvolvimento"
    SPIKE = "spike"


@dataclass(frozen=True)
class TaskClass:
    task_type: TaskType
    size: str  # XS | S | M | L | XL
    confianca: str  # alta | media | baixa
    sinais: list[str]


_SPIKE_KW = (
    "spike", "investigar", "explorar", "prova de conceito", "poc ",
    "avaliar viabilidade", "pesquisar",
)
_DEFIN_KW = (
    "decidir", "especificar", "escrever a spec", "adr", "rfc",
    "levantar requisito", "proposta de arquitetura", "desenhar a solução", "definir o contrato",
)
# caminho/arquivo citado (sinal de task de desenvolvimento concreta)
_ARQ_RE = re.compile(r"[\w./-]+\.(?:ts|tsx|js|jsx|py|sql|md|yml|yaml|json|go|rs)\b")
_SIZE_STEPS = (("XS", 1), ("S", 3), ("M", 6), ("L", 10))  # acima do último -> XL


def _size_from(score: int) -> str:
    for label, limite in _SIZE_STEPS:
        if score <= limite:
            return label
    return "XL"


def classificar_task(title: str, body: str) -> TaskClass:
    """Natureza + tamanho da task a partir do título/corpo (regras determinísticas)."""
    texto = f"{title}\n{body}".lower()
    criterios = body.count("- [ ]")  # itens verificáveis
    arquivos = len(set(_ARQ_RE.findall(body)))
    sinais: list[str] = []

    if any(k in texto for k in _SPIKE_KW):
        sinais.append("keyword de spike")
        return TaskClass(TaskType.SPIKE, _size_from(criterios + arquivos), "alta", sinais)

    defin_kw = any(k in texto for k in _DEFIN_KW)
    if criterios == 0:
        # sem critério verificável → é definição (keyword reforça a confiança)
        sinais.append("sem critério verificável ('- [ ]')")
        conf = "alta" if defin_kw else "media"
        if defin_kw:
            sinais.append("keyword de definição")
        return TaskClass(TaskType.DEFINICAO, _size_from(arquivos), conf, sinais)

    if defin_kw:
        sinais.append("keyword de definição (apesar de ter critérios)")
        return TaskClass(TaskType.DEFINICAO, _size_from(criterios + arquivos), "media", sinais)

    # tem critério verificável e sem cara de definição/spike → desenvolvimento
    sinais.append(f"{criterios} critério(s) verificável(is)")
    if arquivos:
        sinais.append(f"{arquivos} arquivo(s) citado(s)")
    conf = "alta" if arquivos else "media"
    return TaskClass(TaskType.DESENVOLVIMENTO, _size_from(criterios + arquivos), conf, sinais)
