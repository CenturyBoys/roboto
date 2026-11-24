"""Self-heal de dependência faltante (fatia 2 do épico #322, orquestração autônoma).

Quando uma issue referencia uma dependência que NÃO existe como issue (nem `#N`, só nome/descrição —
ex.: a #286 dependia de "**T1** (`bracket.ts`…)" e "**T2** (migration…)", que estavam no doc de
breakdown mas nunca viraram issue), o harness **abre a issue da dependência** automaticamente —
esqueleto marcado `auto`+`status:to-do` (NÃO entra no coder: falha o DoR até ser refinada) e linka
de volta por COMENTÁRIO no pai (não edita o corpo — D30). Deixa o grafo confiável pro driver de
épico (fatia 3). Determinismo-primeiro: o parser e a criação são código; o refino depois é agêntico.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from roboto.app.deps import blocked_by

# a cláusula "Depende de …" até o próximo cabeçalho em negrito (**Bloqueia:**) ou fim de linha.
_DEP_CLAUSE = re.compile(
    r"depende d[ea]s?\s*:?(.+?)(?:\*\*\s*\w+\s*:|[\r\n]|$)", re.IGNORECASE | re.DOTALL,
)
# item NOMEADO: **Label** (descrição) — Label NÃO é #N (esse o gate de dependência por #N já cobre).
_NAMED = re.compile(r"\*\*\s*([A-Za-z][\w.-]*)\s*\*\*\s*\(([^)]+)\)")


@dataclass(frozen=True)
class NamedDep:
    label: str  # ex.: "T1"
    desc: str  # ex.: "bracket.ts puro em packages/core"

    @property
    def title(self) -> str:
        """Título do esqueleto: a descrição (acionável) prefixada pelo rótulo do breakdown."""
        return f"{self.label}: {self.desc}"


def named_deps(body: str) -> list[NamedDep]:
    """Dependências NOMEADAS (não-`#N`) citadas na cláusula "Depende de" (dedup por label). Vazio
    quando as deps são só `#N` (caso normal — o gate por #N resolve) ou não há cláusula."""
    m = _DEP_CLAUSE.search(body or "")
    if not m:
        return []
    seen: set[str] = set()
    out: list[NamedDep] = []
    for label, desc in _NAMED.findall(m.group(1)):
        key = label.strip().lower()
        if key not in seen:
            seen.add(key)
            out.append(NamedDep(label=label.strip(), desc=desc.strip()))
    return out


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def already_tracked(dep: NamedDep, existing_titles: list[str]) -> bool:
    """A dependência nomeada já virou issue? Match frouxo pela descrição (palavras-chave) p/ não
    duplicar quando alguém (ou um ciclo anterior) já criou o esqueleto."""
    needle = _normalize(dep.desc)
    key = needle.split()[0] if needle else ""
    return any(key and key in _normalize(t) and _overlap(needle, t) for t in existing_titles)


def _overlap(needle: str, title: str) -> bool:
    ns, ts = set(needle.split()), set(_normalize(title).split())
    if not ns:
        return False
    return len(ns & ts) / len(ns) >= 0.5  # metade das palavras-chave da desc batem no título


def skeleton_body(parent: int, dep: NamedDep) -> str:
    """Corpo do esqueleto auto-aberto. Marcado como auto + NÃO-pronto: tem que passar pelo refino
    (DoR) antes de implementar — o esqueleto por si só não é acionável (de propósito)."""
    return (
        f"> ⚙️ **Issue auto-aberta** pelo self-heal: a #{parent} depende de **{dep.label}** "
        f"(`{dep.desc}`), que não existia como issue. Criada p/ destravar a cadeia.\n\n"
        f"**Depende de:** (raiz — preencher no refino)\n"
        f"**Parte da cadeia de:** #{parent}\n\n"
        "## Contexto\n"
        f"Fatia **{dep.label}** referenciada pela #{parent}. Refinar a fundo (DoR) antes de "
        "implementar — descrição de origem: " + dep.desc + ".\n\n"
        "## Escopo\n(a definir no refino)\n\n"
        "## Critérios de aceite\n- [ ] (a definir no refino)\n\n"
        "## DoD\n- [ ] (a definir no refino)\n"
    )


def wire_deps(body: str, created: list[int]) -> str:
    """Grava no corpo do dependente uma aresta LEGÍVEL (`Depende de #N`) p/ as deps recém-criadas.

    Sem isto, a dep nasce ÓRFÃ: o self-heal cria o esqueleto mas o corpo do pai continua citando só
    a prosa ("T1/T2"), que o gate/driver não enxerga (bug do #286 → #397/#398). Idempotente: não
    repete o que o parser já vê. Linha NOVA (não mexe na prosa existente, frágil) e no formato que o
    ``app/deps.py:blocked_by`` lê (ruído de markdown curto antes do `#N`)."""
    ja = set(blocked_by(body or ""))
    faltando = [n for n in created if n not in ja]
    if not faltando:
        return body or ""
    linha = (
        "> **Depende de:** " + ", ".join(f"#{n}" for n in faltando)
        + "  _(aresta gravada pelo self-heal — dep antes era só nomeada)_"
    )
    return (body or "").rstrip() + "\n\n" + linha + "\n"


# callables injetáveis (teste passa fakes; o harness liga no github real)
CreateIssue = Callable[[str, str, str], Awaitable[int | None]]  # (repo,title,body) -> número|None
Comment = Callable[[str, int, str], Awaitable[None]]  # (repo, pai, texto)
AddLabel = Callable[[str, int, str], Awaitable[None]]  # (repo, número, label)
UpdateBody = Callable[[str, int, str], Awaitable[None]]  # (repo, número, novo_corpo)


async def heal_missing_deps(
    *, repo: str, parent: int, body: str, existing_titles: list[str],
    create_issue: CreateIssue, comment: Comment, add_label: AddLabel | None = None,
    update_body: UpdateBody | None = None, max_create: int = 6,
) -> list[int]:
    """Cria um esqueleto p/ cada dependência NOMEADA (não-`#N`) que ainda não é issue, marca
    `status:to-do`+`auto`, comenta no PAI linkando, **grava a aresta `Depende de #N` no corpo do
    pai** (``update_body``) e **re-bloqueia o pai** (``add_label`` → `status:blocked`). Devolve os
    criados ([] = nada a curar). Idempotente via `existing_titles`. Teto `max_create` contra surto.

    WIRE + RE-BLOQUEIO são o conserto do #322: antes, a dep nascia órfã (só comentário) e o pai
    seguia "pronto" aos olhos do gate/driver — rodava impl sobre fundação inexistente (run-1047)."""
    faltantes = [d for d in named_deps(body) if not already_tracked(d, existing_titles)]
    criados: list[int] = []
    for dep in faltantes[:max_create]:
        num = await create_issue(repo, dep.title, skeleton_body(parent, dep))
        if num is None:
            continue
        criados.append(num)
        if add_label is not None:
            for lab in ("status:to-do", "auto"):
                await add_label(repo, num, lab)
    if criados:
        links = ", ".join(f"#{n}" for n in criados)
        await comment(
            repo, parent,
            f"⚙️ self-heal: abri {links} para as dependências que faltavam (nomeadas, sem issue). "
            "Refino (DoR) pendente antes de implementar — destravando a cadeia.",
        )
        if update_body is not None:  # aresta legível no corpo do pai (não deixa a dep órfã)
            novo = wire_deps(body, criados)
            if novo != body:
                await update_body(repo, parent, novo)
        if add_label is not None:  # pai depende de esqueletos sem DoR → NÃO está pronto
            await add_label(repo, parent, "status:blocked")
    return criados
