---
name: review-pr
description: Revisa um PR (reviewer ≠ autor) focando em lógica/design, com findings estruturados e evidência. Dispare ao revisar um PR, ou quando pedirem "revisa o PR #N".
version: 1
---

# review-pr — review estruturado (reviewer ≠ autor)

**Reviewer ≠ autor** (quem gera não valida). Foque em **LÓGICA e DESIGN**.

## O que NÃO flagar (determinismo primeiro)
Não re-flague **lint / type / test / build / secret-scan** — o **CI já pega**. É desperdício de token
e ruído. Se o verify determinístico (code-intel/tsgo) apontou algo, avalie contra o diff: se real,
vire finding; se falso positivo, ignore.

## Saída — um bloco por problema REAL
```
FINDING
severidade: bloqueador|menor
arquivo: <path ou ->
linha: <n ou 0>
confianca: alta|media|baixa
titulo: <frase curta>
evidencia: <1-2 linhas; só o trecho MÍNIMO, nunca cole o arquivo>
recomendacao: <objetivo>
END
```
Sem problema real → **não emita bloco nenhum**.

## Veredito e contexto
- Qualquer **BLOQUEADOR** não-tratado **reprova** o PR. Na dúvida, reprove.
- **Re-review:** se já há reviews anteriores no PR, **não repita** o que foi apontado — foque no que mudou.
- Exija **evidência** em cada finding. Os comentários vão **inline**, enxutos (evidência colapsada).
