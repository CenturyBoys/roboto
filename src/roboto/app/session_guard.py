"""Guard de sessão (#266): não retomar uma sessão nativa sob config incompatível.

Com o switcher de modelo por etapa (trilha I) e o escalonamento (#242, correção no modelo forte), um
`resume` pode cair sob modelo/tools diferente do que criou a sessão — contexto/cache incoerente.
Guardamos um **hash da config** (modelo + tools + extra) na sessão e só retomamos quando ele bate.
Derivado do `sessionConfig`-hash do Tucano (Apache-2.0; ver `research/tucano-reuso.md`).

Puro e sem I/O: o motor/orquestrador computa o hash e decide com `may_resume`/`resumable_native_id`.
"""

from __future__ import annotations

import hashlib

from roboto.orchestrator.model import Session


def session_config_hash(*, model: str, tools: tuple[str, ...] = (), extra: str = "") -> str:
    """Hash estável da config que torna uma sessão nativa retomável. Mesma config → mesmo hash.

    `tools` entra ordenado (a ordem não muda a config); `extra` carrega qualquer dimensão adicional
    que invalide a sessão (ex.: system prompt), quando o chamador quiser considerá-la.
    """
    payload = "\n".join([model.strip(), ",".join(sorted(tools)), extra.strip()])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def may_resume(stored_hash: str | None, current_hash: str) -> bool:
    """Só retoma se a sessão foi criada sob a MESMA config. Sem hash guardado → não retoma."""
    return stored_hash is not None and stored_hash == current_hash


def resumable_native_id(sessions: list[Session], current_hash: str) -> str | None:
    """Id nativo da sessão mais recente com config compatível (maior id primeiro); senão `None`."""
    for session in sorted(sessions, key=lambda s: s.id, reverse=True):
        if session.native_session_id and may_resume(session.config_hash, current_hash):
            return session.native_session_id
    return None
