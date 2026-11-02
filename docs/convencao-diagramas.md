# Convenção de diagramas (Mermaid)

Diagrama bom = **legível em 3 segundos**. O Mermaid faz auto-layout: se a gente sobrecarrega, ele
**empilha as labels umas sobre as outras** (foi o que aconteceu com a máquina de estados). As regras
abaixo evitam isso por construção.

## As regras

1. **Label de aresta ≤ 2–3 palavras.** O detalhe vai numa **legenda em prosa** logo abaixo do
   diagrama, não dentro dele. (ex.: `retry` no diagrama; "retry = backoff exponencial" na legenda.)
2. **Sem nó-hub.** Evite muitas arestas convergindo num único nó (o `running` virou um nó com 5
   arestas → labels colidiram). Se precisar, **quebre em dois diagramas** ou agrupe com `subgraph`.
3. **≤ ~8 nós** por diagrama. Passou disso, separe por fase/assunto.
4. **Direção certa:** `flowchart LR` para **pipelines/loop** (esquerda→direita); `stateDiagram-v2`
   (TB) para **máquinas de estado**; `sequenceDiagram` para **interação no tempo**.
5. **Aspas em labels com caractere especial.** Parênteses, `/`, `:` quebram o parser fora de aspas →
   use `["texto (com parêntese)"]` ou simplifique o texto.
6. **Uma legenda curta** (`*Legenda:* termo = explicação · ...`) imediatamente após o diagrama.
7. **Teste olhando:** `mkdocs serve` → se duas labels encostam, **encurte** (não aumente o diagrama).

## Exemplo — antes × depois

```text
❌  running --> waiting: precisa aprovacao / tool-result
✅  running --> waiting: aprovação      (+ legenda: "aprovação = precisa de humano / tool-result")
```

## Por que não só mexer no espaçamento?

Dá pra forçar `nodeSpacing`/`rankSpacing` no Mermaid, mas é frágil e trata o sintoma. **Labels curtas
+ menos arestas por nó** resolvem na raiz e valem em qualquer tema/tela. Espaçamento é último recurso.

!!! tip "Ao criar/alterar um diagrama"
    Siga estas regras; se um diagrama existente estiver ilegível (labels coladas), **encurte as labels
    e mova o detalhe pra legenda** — é a correção padrão.
