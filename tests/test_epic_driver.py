"""Driver de épico (fatia 3 do épico #322)."""

from __future__ import annotations

from roboto.app.epic_driver import (
    EpicChild,
    drive_epic,
    plan_epic,
    ready_issues,
)


def _issue(n: int, body: str, labels: list[str] | None = None) -> tuple:
    return (n, f"issue {n}", body, labels or [], "open")


def test_ready_issues_respeita_dep_e_label() -> None:
    children = [
        EpicChild(10, deps=[], blocked=False),  # pronta (sem dep, sem label)
        EpicChild(11, deps=[10], blocked=False),  # #10 ainda aberta → espera
        EpicChild(12, deps=[], blocked=True),  # status:blocked → espera
    ]
    assert ready_issues(children, open_numbers={10, 11, 12}) == [10]
    # fechou a #10: ela sai das FILHAS abertas E das open_numbers → a #11 destrava
    children2 = [EpicChild(11, deps=[10], blocked=False), EpicChild(12, deps=[], blocked=True)]
    assert ready_issues(children2, open_numbers={11, 12}) == [11]


def test_plan_epic_acha_filhas_e_separa() -> None:
    opens = [
        _issue(10, "Parte do épico #7.\n\nFatia raiz."),  # filha pronta
        _issue(11, "Parte do épico #7.\n\nDepende de #10."),  # filha esperando a #10
        _issue(12, "Parte do épico #7.", ["status:blocked"]),  # filha bloqueada
        _issue(99, "issue solta, não é do épico"),  # não é filha
    ]
    plan = plan_epic(7, opens)
    assert plan.total == 3  # 3 filhas
    assert plan.ready == [10]
    assert set(plan.waiting) == {11, 12}


async def test_drive_epic_despacha_so_as_prontas() -> None:
    opens = [
        _issue(10, "Parte do épico #7."),
        _issue(11, "Parte do épico #7.\n\nDepende de #10."),
    ]
    disparados: list[int] = []

    async def list_full(repo: str) -> list:
        return opens

    async def is_active(n: int) -> bool:
        return False

    async def dispatch(n: int) -> bool:
        disparados.append(n)
        return True

    res = await drive_epic(
        repo="acme/app", epic=7, list_full=list_full, is_active=is_active, dispatch=dispatch,
    )
    assert res.dispatched == [10]  # só a pronta; a #11 espera a #10 fechar
    assert disparados == [10]


async def test_drive_epic_nao_duplica_run_ativo() -> None:
    opens = [_issue(10, "Parte do épico #7.")]

    async def list_full(repo: str) -> list:
        return opens

    async def is_active(n: int) -> bool:
        return True  # já tem impl rodando

    async def dispatch(n: int) -> bool:
        raise AssertionError("não deveria despachar — já ativo")

    res = await drive_epic(
        repo="acme/app", epic=7, list_full=list_full, is_active=is_active, dispatch=dispatch,
    )
    assert res.dispatched == []
    assert res.plan.ready == [10]  # estava pronta, mas já rodando → não redispara
