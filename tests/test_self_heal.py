"""Self-heal de dependência faltante (fatia 2 do épico #322)."""

from __future__ import annotations

from roboto.app.deps import blocked_by
from roboto.app.self_heal import (
    NamedDep,
    already_tracked,
    heal_missing_deps,
    named_deps,
    wire_deps,
)

# corpo real da #286 (arenavalendo): deps nomeadas T1/T2 + a #281 (que é #N).
_286 = (
    "> **Depende de:** #281 (documentação de produto), **T1** (`bracket.ts` puro em "
    "`packages/core`) e **T2** (migration additive `drawSeed`/`seedA`). **Bloqueia:** T4 (lock).\n"
)


def test_parseia_deps_nomeadas_nao_N() -> None:
    deps = named_deps(_286)
    labels = [d.label for d in deps]
    assert labels == ["T1", "T2"]  # #281 (que é #N) NÃO entra; T1/T2 sim
    assert "bracket.ts" in deps[0].desc


def test_sem_deps_nomeadas_quando_so_N() -> None:
    assert named_deps("Depende de #281, #282. Resto do corpo.") == []
    assert named_deps("sem clausula de dependencia") == []


def test_already_tracked_dedup() -> None:
    dep = NamedDep("T1", "bracket.ts puro em packages/core")
    assert already_tracked(dep, ["feat(core): bracket.ts puro em packages/core (sorteio)"])
    assert not already_tracked(dep, ["outra issue qualquer", "migration de banco"])


def test_wire_deps_grava_aresta_legivel_pelo_parser() -> None:
    # a linha gravada tem que ser LIDA de volta pelo gate (deps.py:blocked_by) — ida-e-volta.
    novo = wire_deps("## Contexto\ncorpo sem deps", [397, 398])
    assert blocked_by(novo) == [397, 398]
    # no corpo real da #286 (que já expõe #281), acrescenta #397/#398 sem perder o #281
    sobre_286 = wire_deps(_286, [397, 398])
    assert set(blocked_by(sobre_286)) == {281, 397, 398}
    # idempotente: se o corpo já tem a aresta #N, não adiciona de novo
    assert wire_deps(novo, [397, 398]) == novo
    ja = "corpo\n\nDepende de #397, #398"
    assert wire_deps(ja, [397, 398]) == ja


async def test_heal_cria_esqueleto_comenta_wire_e_rebloqueia() -> None:
    criadas: list[tuple[str, str]] = []
    labels: list[tuple[int, str]] = []
    comentarios: list[tuple[int, str]] = []
    corpos: list[tuple[int, str]] = []
    seq = iter([501, 502])

    async def create_issue(repo: str, title: str, body: str) -> int | None:
        criadas.append((title, body))
        return next(seq)

    async def comment(repo: str, parent: int, text: str) -> None:
        comentarios.append((parent, text))

    async def add_label(repo: str, number: int, label: str) -> None:
        labels.append((number, label))

    async def update_body(repo: str, number: int, new_body: str) -> None:
        corpos.append((number, new_body))

    criados = await heal_missing_deps(
        repo="acme/app", parent=286, body=_286, existing_titles=[],
        create_issue=create_issue, comment=comment, add_label=add_label, update_body=update_body,
    )
    assert criados == [501, 502]  # T1, T2
    assert len(criadas) == 2 and "bracket.ts" in criadas[0][0]
    assert (501, "status:to-do") in labels and (501, "auto") in labels
    assert comentarios and "#501, #502" in comentarios[0][1]  # pai comentado com os links
    # WIRE: corpo do pai reescrito com aresta legível pelo gate
    assert corpos and corpos[0][0] == 286 and {501, 502} <= set(blocked_by(corpos[0][1]))
    # RE-BLOQUEIO: pai marcado status:blocked (depende de esqueletos sem DoR)
    assert (286, "status:blocked") in labels


async def test_heal_nao_cria_se_fundacao_ja_mergeada() -> None:
    # CHECA-ANTES-DE-CRIAR: T1 (bracket.ts) já está num PR mergeado → NÃO abre esqueleto (teria
    # evitado o #397 redundante). T2 não está satisfeita → essa sim é criada.
    criadas: list[tuple[str, str]] = []

    async def create_issue(repo: str, title: str, body: str) -> int | None:
        criadas.append((title, body))
        return 601

    async def comment(repo: str, parent: int, text: str) -> None:
        pass

    criados = await heal_missing_deps(
        repo="acme/app", parent=286, body=_286, existing_titles=[],
        create_issue=create_issue, comment=comment,
        satisfied_titles=["feat(core): bracket.ts puro em packages/core (sorteio seedado)"],
    )
    assert criados == [601]  # só a T2
    assert len(criadas) == 1 and "migration" in criadas[0][0].lower()  # T1 pulada (já feita)


async def test_heal_idempotente_nao_duplica() -> None:
    async def create_issue(repo: str, title: str, body: str) -> int | None:
        raise AssertionError("não deveria criar — já rastreada")

    async def comment(repo: str, parent: int, text: str) -> None:
        raise AssertionError("não deveria comentar")

    criados = await heal_missing_deps(
        repo="acme/app", parent=286, body=_286,
        existing_titles=[
            "T1: bracket.ts puro em packages/core",
            "T2: migration additive drawSeed seedA",
        ],
        create_issue=create_issue, comment=comment,
    )
    assert criados == []
