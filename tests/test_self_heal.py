"""Self-heal de dependência faltante (fatia 2 do épico #322)."""

from __future__ import annotations

from roboto.app.self_heal import (
    NamedDep,
    already_tracked,
    heal_missing_deps,
    named_deps,
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


async def test_heal_cria_esqueleto_e_comenta() -> None:
    criadas: list[tuple[str, str]] = []
    labels: list[tuple[int, str]] = []
    comentarios: list[tuple[int, str]] = []
    seq = iter([501, 502])

    async def create_issue(repo: str, title: str, body: str) -> int | None:
        criadas.append((title, body))
        return next(seq)

    async def comment(repo: str, parent: int, text: str) -> None:
        comentarios.append((parent, text))

    async def add_label(repo: str, number: int, label: str) -> None:
        labels.append((number, label))

    criados = await heal_missing_deps(
        repo="acme/app", parent=286, body=_286, existing_titles=[],
        create_issue=create_issue, comment=comment, add_label=add_label,
    )
    assert criados == [501, 502]  # T1, T2
    assert len(criadas) == 2 and "bracket.ts" in criadas[0][0]
    assert (501, "status:to-do") in labels and (501, "auto") in labels
    assert comentarios and "#501, #502" in comentarios[0][1]  # pai comentado com os links


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
