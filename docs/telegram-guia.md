# Guia — conversando com o Potter pelo Telegram ⚡

Referência rápida de **comandos** e **conversas**. Princípio geral:
**Telegram = a conversa · a issue do GitHub = o registro.** O Potter **nunca cria, edita ou
mergeia nada sem o seu `ok`** (D30).

> Dentro do próprio Telegram, mande **`ajuda`** a qualquer momento pra receber a versão curta disto.

---

## As 4 intenções que ele entende

Ele decide o que você quer de forma **determinística** (sem gastar LLM nisso):

| Você manda… | Intenção | O que acontece |
|---|---|---|
| `quero um placar de vitórias por jogador` | **ideia nova** | entrevista → propõe a issue → cria com seu `ok` |
| `sobre a #180` · `a #180 precisa cobrir X` | **issue existente** | busca a #180 → conversa sobre ela → edita com seu `ok` |
| `issues` · `qual issue dá pra fazer` | **pergunta** | lista as issues abertas |
| `pega #180` | **trabalhar** | checa o DoR; se completo, implementa; se falta, te pergunta |
| `ajuda` · `oi` · `/start` | **ajuda** | manda este guia (curto) |

---

## 1. Ideia nova → issue (conversa de refino)

```
você:   queria um placar de vitórias por jogador
Potter: PERGUNTA: deve persistir no banco? quais critérios de aceite?
você:   (reply) sim, no banco; critério: mostra W/L por jogador
Potter: 📋 Proponho criar esta issue: <título + corpo>. Responde ok que eu crio.
você:   (reply) ok
Potter: ✅ Issue criada: <título>
```

- Ele faz **uma pergunta por vez** até ter o DoR (Contexto, Escopo, Critérios, DoD).
- **Responda em _reply_** à pergunta dele (é o que mantém a conversa no trilho).
- Só cria a issue depois do seu **`ok`**. Qualquer outra resposta → descarta.

## 2. Issue que já existe → discutir e editar

```
você:   sobre a #180, acho que falta o DoD
Potter: (busca a #180) PERGUNTA: o DoD deve incluir teste de carga?
você:   (reply) sim, e cobrir rate limit por IP
Potter: 📋 Proponho atualizar a #180: <novo corpo>. Responde ok que eu edito.
você:   (reply) ok
Potter: ✅ Issue #180 atualizada.  (+ comentário de trilha na issue)
```

- Ele **busca o corpo atual** da issue — não precisa mandar link.
- Edição entra **no corpo** da issue + deixa **1 comentário de trilha** (o que mudou).

## 3. Listar / escolher

```
você:   qual issue dá pra fazer que não tá bloqueada
Potter: Issues abertas:
        #180 feat: rate limit distribuído
        #112 feat: targeting por parceiro
        ...
```

## 4. Trabalhar (implementar) — `pega #N`

```
você:   pega #180
Potter: Ok, peguei a #180 — vou checar o DoR e, se completa, trabalhar.
        (se faltar DoR) ⚡ #180: falta 'DoD'. Complete e eu sigo.
        (quando implementa) ✅ #180: implementei, review aprovou (PR #X). Falta o merge humano.
```

- `pega #180` de novo em algo parado = **retoma** o trabalho.
- O **merge final é humano** — o Potter abre o PR e revisa, mas não mergeia.

---

## Regras de ouro

- **Responda em _reply_** às perguntas/propostas dele (roteia a resposta certa).
- **Nada acontece sem o seu `ok`**: criar issue, editar issue, abrir/mergear PR.
- Ele só age em issues/PRs **marcados pra ele** (label `roboto` ou atribuídos) — não mexe no
  trabalho de outras pessoas.
- O que ele gasta de tokens aparece no **console** (`/costs`).
