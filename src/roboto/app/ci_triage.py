"""Triagem de falha de CI/CD — o AGENTE faz o levantamento, a POLÍTICA decide (determinismo 1º).

Pedido do dono: nem toda CI vermelha é erro NOSSO. Pode ser vuln de dependência PRÉ-EXISTENTE
(`pnpm audit`), erro de CONFIGURAÇÃO de pipeline (secret/runner/env), ou infra/flaky. Forçar o PR
atual a "consertar" isso é errado (flaila, muda fora de escopo, escala à toa). Precisamos ser
RESILIENTES: deixar o agente LER a falha + o diff e classificar a PROCEDÊNCIA; aí a política de rota
decide — corrige no PR (se é nosso), abre issue dedicada (se é dep/config alheia) ou escala
pro humano (infra/flaky ou baixa confiança). O modelo PROPÕE o veredito; o código DECIDE a ação.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from roboto.llm.port import ChatMessage, ModelGateway, Tier

# `+++ b/<path>` do diff unificado = arquivo tocado pelo PR (ignora /dev/null de arquivo removido).
_DIFF_FILE = re.compile(r"^\+\+\+ b/(.+)$", re.M)


def changed_files_from_diff(diff: str) -> list[str]:
    """Arquivos que o PR mudou, extraídos do diff unificado (p/ o agente aferir procedência)."""
    return [m for m in _DIFF_FILE.findall(diff) if m != "/dev/null"]

# categorias de procedência (o agente escolhe uma). Constantes p/ evitar typo no roteamento.
CAT_NOSSO = "nosso_codigo"  # a MUDANÇA do PR quebrou (lint/tipo/teste em arquivo que ele mexeu)
CAT_SEGURANCA = "dependencia_seguranca"  # vuln/CVE/GHSA em dependência que o PR não tocou
CAT_CONFIG = "config_pipeline"  # workflow/secret/runner/env mal configurado (não é código)
CAT_INFRA = "infra_flaky"  # timeout/conexão recusada/flaky — ambiente, não a mudança

# ações possíveis (o que a política decide a partir do veredito).
ACAO_CORRIGIR = "corrigir"  # é nosso → realimenta o motor no próprio PR (comportamento atual)
ACAO_ABRIR_ISSUE = "abrir_issue"  # não é nosso → abre task dedicada (deduplicada) + não trava o PR
ACAO_ESCALAR = "escalar"  # infra/flaky ou baixa confiança → surfa pro humano (não chuta)

CI_TRIAGE_SYSTEM = (
    "Você é um TRIADOR de falhas de CI/CD. Recebe o RESUMO dos checks que FALHARAM num PR, a lista "
    "de ARQUIVOS que o PR mudou e um trecho do diff. Decida a PROCEDÊNCIA da falha — se foi a "
    "MUDANÇA deste PR que quebrou, ou se é algo PRÉ-EXISTENTE/alheio. NÃO conserte nada; só "
    "CLASSIFIQUE. Responda EXATAMENTE neste formato (uma chave por linha, sem markdown):\n"
    "CATEGORIA: nosso_codigo | dependencia_seguranca | config_pipeline | infra_flaky\n"
    "NOSSO: sim | nao   (a falha foi CAUSADA pelo diff deste PR?)\n"
    "CONFIANCA: alta | media | baixa\n"
    "TITULO: <título curto e específico p/ abrir uma issue, caso não seja nosso>\n"
    "RESUMO: <1-3 linhas ACIONÁVEIS: o quê, onde, como resolver (ex.: bump pacote X p/ >=Y)>\n"
    "DEDUP: <chave estável p/ não duplicar: o GHSA/CVE, ou o pacote, ou nome-do-check+erro>\n"
    "Regras: `pnpm audit`/CVE/GHSA numa dependência que o PR NÃO tocou = dependencia_seguranca, "
    "NOSSO=nao. Erro de workflow/secret/runner/env/permission = config_pipeline, NOSSO=nao. "
    "Timeout/ECONNREFUSED/flaky = infra_flaky. Lint/tipo/teste em arquivo que o PR MUDOU = "
    "nosso_codigo, NOSSO=sim."
)


@dataclass(frozen=True)
class CiTriage:
    categoria: str  # CAT_* — procedência da falha
    nosso: bool  # a falha foi causada pelo diff deste PR?
    confianca: str  # alta | media | baixa
    titulo: str  # título p/ a issue (se não for nosso)
    resumo: str  # acionável (corpo da issue / feedback)
    dedup: str  # chave estável p/ dedup da issue


def _parse_triage(text: str) -> CiTriage:
    """Parser tolerante do formato `CHAVE: valor` (uma por linha). Faltou chave → default seguro."""
    campos: dict[str, str] = {}
    for linha in text.splitlines():
        if ":" in linha:
            chave, _, valor = linha.partition(":")
            k = chave.strip().lower()
            if k in ("categoria", "nosso", "confianca", "titulo", "resumo", "dedup"):
                campos[k] = valor.strip()
    categoria = campos.get("categoria", "").lower()
    if categoria not in (CAT_NOSSO, CAT_SEGURANCA, CAT_CONFIG, CAT_INFRA):
        categoria = CAT_INFRA  # desconhecido → trata como ambiente (não força correção cega)
    nosso = campos.get("nosso", "").lower().startswith("s") or categoria == CAT_NOSSO
    conf = campos.get("confianca", "media").lower()
    if conf not in ("alta", "media", "baixa"):
        conf = "media"
    return CiTriage(
        categoria=categoria,
        nosso=nosso,
        confianca=conf,
        titulo=campos.get("titulo", "").strip(),
        resumo=campos.get("resumo", "").strip(),
        dedup=campos.get("dedup", "").strip(),
    )


def acao_ci(t: CiTriage) -> str:
    """POLÍTICA pura: do veredito do agente → a ação. Conservador: baixa confiança NÃO conserta
    cego nem abre issue à toa (escala); infra/flaky escala; só nosso vai pra correção no PR."""
    if t.confianca == "baixa":
        return ACAO_ESCALAR
    if t.categoria == CAT_NOSSO or t.nosso:
        return ACAO_CORRIGIR
    if t.categoria in (CAT_SEGURANCA, CAT_CONFIG):
        return ACAO_ABRIR_ISSUE
    return ACAO_ESCALAR  # infra_flaky (ou qualquer resto) → humano decide (retry/ignorar)


async def triar_ci(
    ci_log: str,
    changed_files: list[str],
    diff: str,
    gateway: ModelGateway,
    *,
    tier: Tier = Tier.JUDGE,
    max_diff: int = 4000,
) -> CiTriage:
    """O AGENTE lê a falha de CI + o diff do PR e classifica a procedência. Falha do gateway →
    default conservador (infra_flaky, baixa confiança → a política escala, não chuta correção)."""
    arquivos = "\n".join(f"- {f}" for f in changed_files[:50]) or "(nenhum arquivo listado)"
    user = (
        f"CHECKS QUE FALHARAM:\n{ci_log.strip()}\n\n"
        f"ARQUIVOS MUDADOS PELO PR:\n{arquivos}\n\n"
        f"DIFF (trecho):\n{diff[:max_diff]}"
    )
    messages = [
        ChatMessage(role="system", content=CI_TRIAGE_SYSTEM),
        ChatMessage(role="user", content=user),
    ]
    result = await gateway.complete(messages, tier)
    from roboto.result import Ok

    if isinstance(result, Ok):
        return _parse_triage(result.value.text)
    return CiTriage(CAT_INFRA, False, "baixa", "", "triagem indisponível", "")


def ci_issue_body(t: CiTriage, repo: str, pr_number: int) -> str:
    """Corpo da issue de CI (procedência + acionável + rastro do PR onde o vermelho apareceu)."""
    return (
        f"## Falha de CI não causada por um PR específico ({t.categoria})\n\n"
        f"{t.resumo or '(sem resumo)'}\n\n"
        f"- **Procedência:** não introduzida pelo diff do PR (triagem do agente, "
        f"confiança {t.confianca}).\n"
        f"- **Visto em:** {repo}#{pr_number} (o vermelho é pré-existente/alheio a esse PR).\n"
        f"- **Dedup:** `{t.dedup}`\n\n"
        "> Issue aberta automaticamente pela triagem de CI — corrigir em PR dedicado, não no PR "
        "que apenas esbarrou no vermelho."
    )
