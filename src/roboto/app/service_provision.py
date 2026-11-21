"""Provisiona os serviços do CI do alvo (postgres/redis…) EFÊMEROS por-run e os DERRUBA no fim.

Pedido do dono: subir recurso só quando a task precisa (roda teste), e **derrubar no final**
(nada de container pendurado). Determinismo-primeiro: o HARNESS sobe (lendo o `services:` do CI via
`target_env.parse_ci_services`), não o modelo. Cada container leva o label `roboto.run=<id>` →
teardown por label + sweep de órfãos (runs mortos). Compartilham a REDE do container do fleet
(`--network container:<self>`) p/ o `localhost:5432/6379` do ci.yml do alvo funcionar DE DENTRO.

Dados EFÊMEROS por default (sobe limpo, migra, roda, derruba) — reprodutível e isolado, igual ao CI
do GitHub. Persistência seria opt-in por performance (não implementada; não é o padrão).

Tudo via um `docker` INJETÁVEL (`(args)->(rc,out)`) → testável sem docker real.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

from roboto.app.target_env import CiService

Docker = Callable[[list[str]], tuple[int, str]]
_LABEL = "roboto.run"


def _docker(args: list[str]) -> tuple[int, str]:
    p = subprocess.run(  # noqa: S603,S607 — args fixos do harness, não input do modelo
        ["docker", *args], capture_output=True, text=True, timeout=120,
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _cname(run_id: int, svc: str) -> str:
    return f"roboto-run{run_id}-{svc}"


def provision(
    services: list[CiService], *, run_id: int, self_container: str, docker: Docker | None = None,
) -> list[str]:
    """Sobe cada serviço com `docker run -d`, na REDE do fleet (localhost compartilhado) e labelado
    por-run. Idempotente (remove um homônimo antes). Devolve os nomes que subiram."""
    run = docker or _docker
    subidos: list[str] = []
    for s in services:
        name = _cname(run_id, s.name)
        run(["rm", "-f", name])  # idempotente: mata um resíduo de tentativa anterior
        cmd = [
            "run", "-d", "--name", name, "--label", f"{_LABEL}={run_id}",
            "--network", f"container:{self_container}",
        ]
        for k, v in s.env.items():
            cmd += ["-e", f"{k}={v}"]
        cmd.append(s.image)
        rc, _ = run(cmd)
        if rc == 0:
            subidos.append(name)
    return subidos


# porta padrão por serviço (p/ esperar ficar pronto) — a porta só abre quando o serviço aceita
# conexão (ex.: postgres só binda 5432 depois de inicializar o DB). Cobre os comuns.
_DEFAULT_PORTS = {
    "postgres": 5432, "postgis": 5432, "mysql": 3306, "mariadb": 3306, "redis": 6379,
    "valkey": 6379, "mongo": 27017, "mongodb": 27017, "rabbitmq": 5672, "elasticsearch": 9200,
}

# checker de porta injetável (p/ teste): (port) -> aberta?
PortCheck = Callable[[int], bool]


def _port_open(port: int) -> bool:
    import socket

    s = socket.socket()
    s.settimeout(1.0)
    try:
        s.connect(("localhost", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _port_for(svc: CiService) -> int | None:
    hay = f"{svc.name} {svc.image}".lower()
    return next((p for k, p in _DEFAULT_PORTS.items() if k in hay), None)


def wait_ready(
    services: list[CiService], *, timeout: float = 30.0, check: PortCheck | None = None,
) -> bool:
    """Espera as portas dos serviços ACEITAREM conexão (a porta só abre quando o serviço subiu de
    verdade — melhor que um `sleep` fixo). True se todas abriram dentro do timeout; True também se
    nenhum serviço tem porta conhecida (nada a esperar)."""
    import time

    chk = check or _port_open
    ports = [p for s in services if (p := _port_for(s)) is not None]
    if not ports:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(chk(p) for p in ports):
            return True
        time.sleep(0.5)
    return all(chk(p) for p in ports)


def teardown(run_id: int, *, docker: Docker | None = None) -> int:
    """Derruba TODO container do run (por label). Devolve quantos removeu. Sempre no `finally`."""
    run = docker or _docker
    rc, out = run(["ps", "-aq", "--filter", f"label={_LABEL}={run_id}"])
    ids = [i for i in out.split() if i]
    if ids:
        run(["rm", "-f", *ids])
    return len(ids)


def sweep_orphans(active_run_ids: set[int], *, docker: Docker | None = None) -> int:
    """Remove containers labelados cujo run NÃO está ativo (órfãos de run morto/recreate). Boot."""
    run = docker or _docker
    fmt = "{{.ID}} {{.Label \"" + _LABEL + "\"}}"
    rc, out = run(["ps", "-a", "--filter", f"label={_LABEL}", "--format", fmt])
    orfaos: list[str] = []
    for linha in out.splitlines():
        partes = linha.split()
        if len(partes) >= 2 and partes[1].isdigit() and int(partes[1]) not in active_run_ids:
            orfaos.append(partes[0])
    if orfaos:
        run(["rm", "-f", *orfaos])
    return len(orfaos)
