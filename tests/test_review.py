"""Gate de prontidão da issue (DoR) — check_issue_readiness (determinístico)."""

from __future__ import annotations

from roboto.agents.refiner import IssueDraft
from roboto.agents.review import (
    Finding,
    IssueReadiness,
    PullRequest,
    _parse_findings,
    aprovado_por_findings,
    check_issue_readiness,
    check_issue_size,
    formatar_finding,
    montar_review,
    resumo_review,
    review_issue_semantics,
    review_pr,
    review_pr_findings,
    validar_issue_semantica,
)
from roboto.llm.port import ChatMessage, Completion, Tier
from roboto.llm.stub import StubModelGateway
from roboto.orchestrator.model import Error
from roboto.result import Ok, Result

_READY_BODY = (
    "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n- [ ] faz z\n"
    "## DoD\n- [ ] testes + CI\n## Fora de escopo\nnada"
)


def test_complete_issue_is_ready() -> None:
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body=_READY_BODY))
    assert verdict.ready is True
    assert verdict.missing == []


def test_issue_size_ok_quando_focada() -> None:
    # issue focada (poucos critérios) NÃO é oversized
    s = check_issue_size(IssueDraft(title="feat: x", body=_READY_BODY))
    assert s.oversized is False and s.criterios == 1


def test_issue_size_oversized_quando_epico() -> None:
    # muitos critérios de aceite = parece épico → quebrar em sub-issues (#239)
    criterios = "\n".join(f"- [ ] entregável {i}" for i in range(9))
    body = f"## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n{criterios}\n## DoD\n- [ ] ci"
    s = check_issue_size(IssueDraft(title="feat: rotas versionadas", body=body))
    assert s.oversized is True and s.criterios == 9 and "épico" in s.reason


def test_issue_size_so_conta_criterios_de_aceite_nao_dod() -> None:
    # os '- [ ]' do DoD não contam — só os de Critérios de aceite
    dod = "\n".join(f"- [ ] dod {i}" for i in range(20))
    body = f"## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n- [ ] um\n## DoD\n{dod}"
    s = check_issue_size(IssueDraft(title="feat: x", body=body))
    assert s.oversized is False and s.criterios == 1


def test_checkbox_under_subsection_is_ready() -> None:
    # '- [ ]' sob um subtítulo '### Teste 1' DENTRO de 'Critérios de aceite' conta (a seção vai
    # até o próximo heading de nível igual/superior, não quebra no primeiro '###').
    body = (
        "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\n"
        "### Teste 1 — brute force\n- [ ] bloqueia após N tentativas\n"
        "## DoD\n- [ ] ci"
    )
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body=body))
    assert verdict.ready is True
    assert verdict.missing == []


def test_checkbox_only_in_dod_is_not_ready() -> None:
    # '- [ ]' só no DoD, nenhum sob 'Critérios de aceite' -> não testável -> not ready (#160)
    body = "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\nfaz z\n## DoD\n- [ ] ci"
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body=body))
    assert verdict.ready is False
    assert any("Critérios de aceite" in m for m in verdict.missing)


def test_missing_sections_listed() -> None:
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body="## Contexto\nsó isso"))
    assert verdict.ready is False
    assert any("Escopo" in m for m in verdict.missing)
    assert any("Critérios de aceite" in m for m in verdict.missing)
    assert any("DoD" in m for m in verdict.missing)


def test_no_acceptance_checkbox_is_not_ready() -> None:
    # tem as seções mas nenhum item "- [ ]"
    body = "## Contexto\nx\n## Escopo\ny\n## Critérios de aceite\nfaz z\n## DoD\ntestes"
    verdict = check_issue_readiness(IssueDraft(title="feat: x", body=body))
    assert verdict.ready is False
    assert any("- [ ]" in m for m in verdict.missing)


def test_empty_title_is_not_ready() -> None:
    verdict = check_issue_readiness(IssueDraft(title="  ", body=_READY_BODY))
    assert verdict.ready is False
    assert "título" in verdict.missing


# --- camada semântica da issue (juiz) ---
async def test_issue_semantics_approved() -> None:
    gw = StubModelGateway(reply="VEREDITO: aprovado\nPROBLEMAS:")
    result = await review_issue_semantics(IssueDraft(title="feat: x", body=_READY_BODY), gw)
    assert isinstance(result, Ok)
    assert result.value.approved is True


async def test_issue_semantics_rejected_lists_problems() -> None:
    gw = StubModelGateway(reply="VEREDITO: reprovado\nPROBLEMAS:\n- critério vago\n- escopo amplo")
    result = await review_issue_semantics(IssueDraft(title="feat: x", body=_READY_BODY), gw)
    assert isinstance(result, Ok)
    assert result.value.approved is False
    assert "critério vago" in result.value.issues


# --- review de PR (reviewer != autor) ---
def _pr(author: str = "impl") -> PullRequest:
    return PullRequest(number=7, author=author, title="feat: x", diff="+ código")


async def test_pr_review_blocks_self_review() -> None:
    gw = StubModelGateway(reply="VEREDITO: aprovado")  # não deve nem ser usado
    result = await review_pr(_pr(author="alice"), gw, reviewer="alice")
    assert isinstance(result, Ok)
    assert result.value.approved is False
    assert any("autor" in i for i in result.value.issues)


async def test_pr_review_approves_when_reviewer_differs() -> None:
    gw = StubModelGateway(reply="VEREDITO: aprovado\nPROBLEMAS:")
    result = await review_pr(_pr(author="alice"), gw, reviewer="bob")
    assert isinstance(result, Ok)
    assert result.value.approved is True


async def test_pr_review_requests_changes() -> None:
    gw = StubModelGateway(reply="VEREDITO: reprovado\nPROBLEMAS:\n- sem teste")
    result = await review_pr(_pr(author="alice"), gw, reviewer="bob")
    assert isinstance(result, Ok)
    assert result.value.approved is False
    assert "sem teste" in result.value.issues


class _CapturingGateway:
    """Gateway que guarda as mensagens recebidas, p/ inspecionar o prompt do review (ideia 1)."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.seen: list[ChatMessage] = []

    async def complete(
        self, messages: list[ChatMessage], tier: Tier
    ) -> Result[Completion, Error]:
        self.seen = messages
        return Ok(Completion(text=self._reply, model="cap", tokens_in=0, tokens_out=0))


async def test_re_review_mantem_bloqueador_nao_resolvido_no_prompt() -> None:
    # bug pego no ponta-a-ponta: findings anteriores NÃO podem virar "ignore"; o prompt manda
    # VERIFICAR contra o diff atual e MANTER se não resolvido (não aprovar só por já ter sido dito).
    gw = _CapturingGateway("")
    prev = ["🛑 [BLOQUEADOR] Falta teste de integração (x.ts:10)"]
    result = await review_pr_findings(
        _pr(author="alice"), gw, reviewer="bob", contexto_previo=prev
    )
    assert isinstance(result, Ok)
    user = "\n".join(m.content for m in gw.seen if m.role == "user")
    assert "Falta teste de integração" in user  # o parecer anterior entrou no prompt
    assert "MANTENHA" in user and "não resolvido" in user.lower()  # framing correto
    assert "NÃO repita o que já foi apontado" not in user  # framing antigo (bugado) removido


async def test_pr_review_injeta_achados_do_verify_no_prompt() -> None:
    gw = _CapturingGateway("VEREDITO: reprovado\nPROBLEMAS:\n- erro de tipo não tratado")
    achados = ["env.ts:226 Cannot find name 'process'."]
    result = await review_pr(_pr(author="alice"), gw, reviewer="bob", verify_findings=achados)
    assert isinstance(result, Ok)
    prompt_user = "\n".join(m.content for m in gw.seen if m.role == "user")
    assert "env.ts:226" in prompt_user  # o achado determinístico entrou no prompt
    assert "POSSÍVEIS" in prompt_user  # como possível (avaliar), não fato absoluto


class _SeqGateway:
    """Devolve respostas em sequência (1 por chamada) — p/ testar a ESCALADA (#160)."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    async def complete(
        self, messages: list[ChatMessage], tier: Tier
    ) -> Result[Completion, Error]:
        self.calls += 1
        return Ok(Completion(text=self._replies.pop(0), model="seq", tokens_in=0, tokens_out=0))


async def test_validar_issue_estruturado_alta() -> None:
    gw = StubModelGateway(reply="BEM_DEFINIDA: sim\nCONFIANCA: alta\nLACUNAS:")
    r = await validar_issue_semantica(IssueDraft(title="x", body="y"), gw)
    assert isinstance(r, Ok)
    assert r.value == IssueReadiness(bem_definida=True, confianca="alta", lacunas=[])


async def test_validar_issue_lacunas() -> None:
    gw = StubModelGateway(
        reply="BEM_DEFINIDA: nao\nCONFIANCA: media\nLACUNAS:\n- critério vago\n- sem escopo"
    )
    r = await validar_issue_semantica(IssueDraft(title="x", body="y"), gw)
    assert isinstance(r, Ok)
    assert r.value.bem_definida is False
    assert r.value.confianca == "media"
    assert r.value.lacunas == ["critério vago", "sem escopo"]


async def test_validar_issue_escala_em_baixa() -> None:
    # 1ª (JUDGE) confiança baixa -> escala p/ FRONTIER, que decide alta (usa o veredito forte)
    gw = _SeqGateway(
        ["BEM_DEFINIDA: nao\nCONFIANCA: baixa\nLACUNAS:\n- ambíguo",
         "BEM_DEFINIDA: sim\nCONFIANCA: alta\nLACUNAS:"]
    )
    r = await validar_issue_semantica(IssueDraft(title="x", body="y"), gw)  # type: ignore[arg-type]
    assert isinstance(r, Ok)
    assert gw.calls == 2  # escalou
    assert r.value.bem_definida is True and r.value.confianca == "alta"


# ---- review estruturado por finding (Trilha D) ----
_FIND_TXT = (
    "FINDING\nseveridade: bloqueador\narquivo: src/a.py\nlinha: 42\nconfianca: alta\n"
    "titulo: race na escrita\nevidencia: write sem lock\nrecomendacao: usar lock\nEND\n"
    "FINDING\nseveridade: menor\narquivo: -\nlinha: 0\nconfianca: media\n"
    "titulo: nome ruim\nevidencia: x\nrecomendacao: renomear\nEND"
)


async def test_review_pr_findings_parseia() -> None:
    gw = StubModelGateway(reply=_FIND_TXT)
    r = await review_pr_findings(_pr(author="alice"), gw, reviewer="bob")
    assert isinstance(r, Ok)
    fs = r.value
    assert len(fs) == 2
    assert fs[0].severidade == "bloqueador" and fs[0].arquivo == "src/a.py" and fs[0].linha == 42
    assert fs[1].severidade == "menor" and fs[1].linha == 0


def test_parse_findings_preenche_recomendacao_vazia() -> None:
    # #2: reviewer deixou `recomendacao` vazia → o parser garante um "como" acionável (nunca em
    # branco). Fallback: evidência concreta > derivar do título.
    texto = (
        "FINDING\nseveridade: bloqueador\narquivo: a.ts\nlinha: 10\nconfianca: alta\n"
        "titulo: Teste duplicado\nevidencia: it('x') repete (L20 e L40)\nrecomendacao:\nEND\n"
        "FINDING\nseveridade: menor\narquivo: b.ts\nlinha: 0\nconfianca: media\n"
        "titulo: Nome ruim\nevidencia:\nrecomendacao:\nEND"
    )
    fs = _parse_findings(texto)
    assert len(fs) == 2
    assert fs[0].recomendacao == "it('x') repete (L20 e L40)"  # cai na evidência
    assert fs[1].recomendacao == "Corrigir: Nome ruim"  # sem evidência → deriva do título
    assert all(f.recomendacao.strip() for f in fs)  # nunca vazio


def test_veredito_por_findings() -> None:
    blk = Finding("x", "bloqueador", "-", 0, "alta")
    menor = Finding("y", "menor", "-", 0, "media")
    assert aprovado_por_findings([menor]) is True
    assert aprovado_por_findings([menor, blk]) is False
    assert aprovado_por_findings([]) is True


async def test_review_findings_bloqueia_self_review() -> None:
    gw = StubModelGateway(reply="irrelevante")
    r = await review_pr_findings(_pr(author="alice"), gw, reviewer="alice")
    assert isinstance(r, Ok)
    assert len(r.value) == 1 and r.value[0].severidade == "bloqueador"
    assert aprovado_por_findings(r.value) is False


def test_formatar_finding_enxuto_com_details() -> None:
    f = Finding(
        "race", "bloqueador", "a.py", 10, "alta", evidencia="write sem lock", recomendacao="lock"
    )
    md = formatar_finding(f)
    assert "race" in md and "lock" in md
    assert "<details>" in md and "write sem lock" in md  # evidência COLAPSADA, não à vista


def test_resumo_review() -> None:
    assert "sem apontamentos" in resumo_review([])
    blk = Finding("bug", "bloqueador", "a.py", 3, "alta")
    s = resumo_review([blk])
    assert s.startswith("🔁") and "bug" in s and "a.py" in s


def test_montar_review_separa_inline_e_resumo() -> None:
    com_loc = Finding("bug", "bloqueador", "a.py", 5, "alta", evidencia="x", recomendacao="y")
    sem_loc = Finding("design ruim", "menor", "-", 0, "media")
    inline, body, aprovado = montar_review([com_loc, sem_loc])
    assert inline == [("a.py", 5, formatar_finding(com_loc))]  # com localização -> inline
    assert "design ruim" in body  # sem localização -> entra no resumo (não some)
    assert aprovado is False  # há bloqueador


async def test_review_findings_usa_contexto_previo() -> None:
    # #151: reviews anteriores entram no prompt pra o juiz NÃO repetir o apontamento.
    gw = _CapturingGateway(_FIND_TXT)
    await review_pr_findings(
        _pr(author="alice"), gw, reviewer="bob",
        contexto_previo=["🔁 já apontei: falta teste no login"],
    )
    prompt = "\n".join(m.content for m in gw.seen if m.role == "user")
    assert "falta teste no login" in prompt
    assert "NÃO repita" in prompt
