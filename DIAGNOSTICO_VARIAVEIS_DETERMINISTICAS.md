# DIAGNÓSTICO: Fluxo de Variáveis e Regras Determinísticas

## Data: 2026-01-19

---

## RESUMO EXECUTIVO

### Causa Raiz Identificada (MÚLTIPLAS)

1. **PROBLEMA PRINCIPAL: Modo de ativação inconsistente**
   - Prompts com `regra_deterministica` definida mas `modo_ativacao='llm'`
   - O código ignora silenciosamente a regra quando o modo é LLM

2. **PROBLEMA SECUNDÁRIO: Variáveis sem categoria**
   - Variáveis `pareceres_*` adicionadas sem `categoria_id`
   - Isso não impede a extração, mas dificulta o rastreamento

3. **PROBLEMA TERCIÁRIO: Falta de observabilidade**
   - Sem trace de decisão para entender por que prompts não foram ativados
   - Erros silenciosos em prompts determinísticos sem regra

---

## MAPEAMENTO DO FLUXO (Passo 1)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. DEFINIÇÃO (BD)                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ extraction_variables:      Variáveis disponíveis para extração          │
│ categorias_resumo_json:    Formato JSON por tipo de documento           │
│ prompt_modulos:            Prompts com regra_deterministica             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. EXTRAÇÃO (Agente 1)                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ agente_tjms.py:            Baixa documentos do TJ-MS                    │
│ extrator_resumo_json.py:   Aplica formato JSON por categoria            │
│ Resultado:                 doc.resumo = JSON com variáveis extraídas    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. CONSOLIDAÇÃO (orquestrador_agentes.py)                               │
├─────────────────────────────────────────────────────────────────────────┤
│ consolidar_dados_extracao():                                            │
│   - Parseia doc.resumo de cada documento                                │
│   - Consolida variáveis (OR para booleanos, merge para listas)          │
│   - Retorna: Dict[slug, valor]                                          │
│                                                                         │
│ ProcessVariableResolver.resolver_todas():                               │
│   - Calcula variáveis do XML (valor_causa_superior_210sm, etc)          │
│   - Retorna: Dict[slug, valor]                                          │
│                                                                         │
│ Merge: variaveis = dados_extracao + variaveis_processo                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. AVALIAÇÃO (detector_modulos.py + services_deterministic.py)          │
├─────────────────────────────────────────────────────────────────────────┤
│ DetectorModulosIA.detectar_modulos_relevantes():                        │
│   - Separa módulos: determinísticos vs LLM                              │
│   - Para cada módulo determinístico:                                    │
│       └─ avaliar_ativacao_prompt(regra, variaveis)                      │
│           └─ DeterministicRuleEvaluator.avaliar(AST, dados)             │
│                                                                         │
│ Resultado: ativar = True | False | None (indeterminado)                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. ATIVAÇÃO                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│ Se ativar=True:  Módulo é incluído na peça                              │
│ Se ativar=False: Módulo é ignorado                                      │
│ Se ativar=None:  FAST PATH ignora, MISTO envia para LLM                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## INVENTÁRIO DO BD (Passo 2)

### Variáveis de Extração
- **Total:** 45 variáveis cadastradas
- **Ativas:** 43 variáveis
- **Sem categoria:** 8 variáveis (todas `pareceres_*` recém-adicionadas)

### Variáveis de Sistema (calculadas)
- `processo_ajuizado_apos_2024_09_19`
- `valor_causa_numerico`
- `valor_causa_inferior_60sm`
- `valor_causa_superior_210sm`
- `estado_polo_passivo`
- `municipio_polo_passivo`
- `uniao_polo_passivo`
- `autor_com_assistencia_judiciaria`
- `autor_com_defensoria`

### Prompts Determinísticos
| ID | Nome | Modo | Regra | Status |
|----|------|------|-------|--------|
| 8 | prel_jef_estadual | deterministic | **NULL** | ⚠️ INCONSISTENTE |
| 24 | mer_sem_urgencia | deterministic | `pareceres_natureza_cirurgia = 'eletiva'` | ✅ OK |
| 43 | evt_direcionamento_793 | deterministic | **NULL** | ⚠️ INCONSISTENTE |

### Mapeamento de Categorias
| ID | Nome | Códigos TJ-MS | Status |
|----|------|---------------|--------|
| 1 | residual | [] | ATIVO (fallback) |
| 2 | peticoes | [510, 9500, 8320, 8326] | ATIVO |
| 3 | decisoes | [8506, 517, 137, ...] | ATIVO |
| 5 | **pareceres** | [207, 8451, 9636, 59, 8490] | **INATIVO** |
| 7 | parecer_nat | [8451, 9636, 59, 8490] | ATIVO |

---

## HIPÓTESES VALIDADAS (Passo 3)

### ✅ H1: Desalinhamento de slugs
**Status:** NÃO CONFIRMADO

A regra usa `pareceres_natureza_cirurgia` e o formato JSON do `parecer_nat` define exatamente esse slug. Não há problema de nomenclatura.

### ⚠️ H2: Fonte errada de variáveis
**Status:** PARCIALMENTE CONFIRMADO

O problema estava no **modo de ativação**:
- O prompt `mer_sem_urgencia` tinha `modo_ativacao='llm'`
- Isso fazia a regra ser ignorada (código: `if modo_ativacao == "deterministic" AND regra_deterministica`)
- A variável chegava ao motor, mas a regra não era avaliada

**Evidência (services_deterministic.py:1193):**
```python
if modo_ativacao == "deterministic" and regra_deterministica:
    # Avalia regra
else:
    # Retorna None (vai para LLM)
```

### ✅ H3: Tipos inconsistentes
**Status:** NÃO CONFIRMADO

O avaliador já tem normalização de tipos:
- Booleanos: suporta `true/false`, `"true"/"false"`, `1/0`
- Strings: comparação case-insensitive

### ✅ H4: Cache desatualizado
**Status:** NÃO CONFIRMADO

O cache tem TTL de 60 minutos e inclui tipo_peca na chave.

### ⚠️ H5: Avaliação interrompida
**Status:** CONFIRMADO

Prompts com `modo_ativacao='deterministic'` mas `regra_deterministica=NULL` são **silenciosamente** tratados como LLM. Não há log de erro.

---

## CORREÇÕES IMPLEMENTADAS (Passo 4)

### 4.1 Correção de dados no BD

```sql
-- Corrigir prompts com modo determinístico mas sem regra válida
UPDATE prompt_modulos
SET modo_ativacao = 'llm'
WHERE modo_ativacao = 'deterministic'
  AND (regra_deterministica IS NULL OR regra_deterministica = 'null');

-- OU criar regra para os que devem ser determinísticos
UPDATE prompt_modulos
SET modo_ativacao = 'deterministic',
    regra_deterministica = '{"type":"condition","variable":"pareceres_natureza_cirurgia","operator":"equals","value":"eletiva"}'
WHERE id = 24;
```

### 4.2 Auto-correção no código

Adicionado em `admin/router_prompts.py`:
- Quando `regra_deterministica` é definida, `modo_ativacao` é automaticamente setado para `'deterministic'`
- Isso previne inconsistências futuras

### 4.3 Logs de debug melhorados

Adicionado em `detector_modulos.py`:
- Log de todas as variáveis `pareceres_*` disponíveis
- Log da regra sendo avaliada (variável, valor esperado, valor atual)
- Log do resultado detalhado de cada avaliação

---

## OBSERVABILIDADE (Passo 4.2)

### Trace de Decisão Proposto

Para cada execução, salvar:

```json
{
  "timestamp": "2026-01-19T10:30:00Z",
  "processo": "0001234-56.2026.8.12.0001",
  "modulos_avaliados": [
    {
      "id": 24,
      "nome": "mer_sem_urgencia",
      "modo": "deterministic",
      "regra": {"variable": "pareceres_natureza_cirurgia", "operator": "equals", "value": "eletiva"},
      "variaveis_usadas": ["pareceres_natureza_cirurgia"],
      "valores_encontrados": {"pareceres_natureza_cirurgia": "eletiva"},
      "resultado": true,
      "detalhes": "Regra primária avaliada com sucesso"
    }
  ],
  "resultado_final": {
    "modo_ativacao": "fast_path",
    "modulos_det": 3,
    "modulos_llm": 0,
    "ids_ativados": [8, 24, 43]
  }
}
```

---

## AÇÕES PENDENTES

1. ✅ **FEITO:** Corrigir `modo_ativacao` dos prompts 8, 24, 43
2. ✅ **FEITO:** Adicionar auto-correção no código de salvar prompts
3. ✅ **FEITO:** Melhorar logs de debug no detector
4. ⬜ **PENDENTE:** Implementar trace de decisão persistido
5. ⬜ **PENDENTE:** Criar testes automatizados (Passo 5)
6. ⬜ **PENDENTE:** Criar regras determinísticas para prompts 8 e 43

---

## CONCLUSÃO

O problema principal era uma **inconsistência silenciosa** entre `modo_ativacao` e `regra_deterministica`. O sistema não alertava quando um prompt estava configurado como determinístico mas sem regra definida.

As correções implementadas:
1. Corrigem os dados existentes no BD
2. Previnem novas inconsistências via auto-correção
3. Melhoram a observabilidade para debug futuro
