"""Provisionamento efêmero dos serviços do alvo (B): sobe por-run, derruba no fim, sweep órfãos."""

from __future__ import annotations

from roboto.app.service_provision import provision, sweep_orphans, teardown
from roboto.app.target_env import CiService, parse_ci_services

_CI = """
jobs:
  verify:
    services:
      postgres:
        image: postgres:18
        env:
          POSTGRES_USER: jokenpo
          POSTGRES_DB: jokenpo_test
          TOKEN: ${{ secrets.X }}
      redis:
        image: redis:8
      sem_imagem:
        env: {A: b}
"""


class _Docker:
    """docker fake: grava os comandos e devolve saídas roteadas."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.ps_output = ""

    def __call__(self, args: list[str]) -> tuple[int, str]:
        self.calls.append(args)
        if args[:1] == ["ps"]:
            return 0, self.ps_output
        return 0, "cid\n"


def test_parse_ci_services() -> None:
    svcs = parse_ci_services(_CI)
    by = {s.name: s for s in svcs}
    assert by["postgres"].image == "postgres:18"
    assert by["postgres"].env == {"POSTGRES_USER": "jokenpo", "POSTGRES_DB": "jokenpo_test"}
    assert by["redis"].image == "redis:8"
    assert "sem_imagem" not in by  # serviço sem image é ignorado


def test_provision_sobe_na_rede_do_fleet_com_label() -> None:
    d = _Docker()
    svcs = [CiService("postgres", "postgres:18", {"POSTGRES_USER": "jk"})]
    subidos = provision(svcs, run_id=42, self_container="poc", docker=d)
    assert subidos == ["roboto-run42-postgres"]
    runcmd = next(c for c in d.calls if c[:1] == ["run"])
    assert "--network" in runcmd and "container:poc" in runcmd  # localhost compartilhado
    assert "roboto.run=42" in " ".join(runcmd)  # labelado por-run
    assert "POSTGRES_USER=jk" in runcmd  # env passada


def test_teardown_remove_por_label() -> None:
    d = _Docker()
    d.ps_output = "c1\nc2\n"
    n = teardown(42, docker=d)
    assert n == 2
    rm = next(c for c in d.calls if c[:2] == ["rm", "-f"])
    assert rm == ["rm", "-f", "c1", "c2"]


def test_teardown_sem_container_nao_remove() -> None:
    d = _Docker()
    d.ps_output = ""
    assert teardown(99, docker=d) == 0
    assert not any(c[:2] == ["rm", "-f"] for c in d.calls)


def test_sweep_remove_so_orfaos() -> None:
    d = _Docker()
    d.ps_output = "idA 10\nidB 42\nidC 7\n"  # runs 10, 42, 7
    n = sweep_orphans({42}, docker=d)  # só o 42 está ativo → 10 e 7 são órfãos
    assert n == 2
    rm = next(c for c in d.calls if c[:2] == ["rm", "-f"])
    assert set(rm[2:]) == {"idA", "idC"}  # removeu os órfãos, não o ativo (idB)


def test_wait_ready_espera_porta_abrir() -> None:
    from roboto.app.service_provision import wait_ready

    pg = CiService("postgres", "postgres:18", {})
    estados = iter([False, False, True])  # abre na 3ª checagem
    assert wait_ready([pg], timeout=5, check=lambda _p: next(estados, True)) is True


def test_wait_ready_sem_porta_conhecida_e_true() -> None:
    from roboto.app.service_provision import wait_ready

    exotico = CiService("meu-servico", "foo/bar:1", {})
    assert wait_ready([exotico], check=lambda _p: False) is True  # nada a esperar


def test_wait_ready_timeout_porta_fechada() -> None:
    from roboto.app.service_provision import wait_ready

    pg = CiService("postgres", "postgres:18", {})
    assert wait_ready([pg], timeout=0.1, check=lambda _p: False) is False
