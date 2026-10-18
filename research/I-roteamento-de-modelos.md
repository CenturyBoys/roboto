# Trilha I — Roteamento de modelos (right-sizing)

> Status: ESQUELETO (pesquisa não iniciada)

## Pergunta

Para cada tipo de operação do fleet, qual é o **compute mais barato que resolve com qualidade
suficiente**? Não usar Opus para tudo. Como roteamos (OpenRouter?) e com que critério.

## A escada de validação (do mais barato ao mais caro)

1. **Check determinístico — sem LLM.** Se a validação pode virar script (teste unitário,
   type-checker, lint, build, validação de schema), ela *deve* virar script. Zero token,
   100% determinístico. (= ferramentificação aplicada à validação, ver Trilha F.)
2. **Decisão estruturada barata — Jev / System One (TypeSafe).** Para o que não vira código:
   "o PR cumpre o DoD?", detecção de jailbreak, scoring de qualidade, classificação.
   Saída type-safe (sem alucinação por construção) + **confiança calibrada** + ~40–200× mais
   rápido/barato (input ~$0.042/MTok, output grátis).
   Fonte: https://typesafe.ai/blog/introducing-system-one-models-and-jev
3. **Frontier tiered — Haiku → Sonnet → Opus.** Só quando há raciocínio/geração de verdade.
   Right-size por etapa (refinar issue vs. arquitetar vs. implementar vs. revisar).

## Como a confiança calibrada vira gate

O score de confiança do Jev permite um **threshold de escalonamento**: abaixo do limiar, escala
para um modelo maior ou para o humano. Isso conecta direto com os gates humanos da Trilha H.

## Perguntas a decidir / pesquisar

- [ ] **Mapa operação → modelo**: tabela de cada etapa do fleet com o tier recomendado.
- [ ] **Caminho de acesso ao Jev**: o blog NÃO confirma integração com OpenRouter — achar se é
      API direta e/ou via OpenRouter; maturidade, limites, disponibilidade.
- [ ] **Avaliar o Jev nos nossos casos reais** de validação antes de confiar (não adotar no escuro).
- [ ] **OpenRouter como substrato de roteamento**: vantagens (fallback, um só billing) vs. riscos
      (latência, vendor extra, privacidade do código).
- [ ] **Risco de superfície**: cada vendor novo (TypeSafe, OpenRouter) é dependência operacional.
- [ ] Medição: custo/latência por etapa antes/depois do right-sizing (amarra com Trilha H).

## Saída esperada

Política de roteamento de modelos (mapa operação→tier + escada de validação) que vira regra
no futuro `AGENTS.md` e critério embutido na orquestração (Trilha B).
