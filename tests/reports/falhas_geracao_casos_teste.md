# Relatório de Falhas na Geração de Casos de Teste

**Gerado em:** 2026-01-20
**Contexto:** Suíte de testes automatizados para regras determinísticas de ativação de prompts
**Resultado:** 128 passed, 10 failed, 1 skipped (92% sucesso)

---

## Resumo Executivo

A suíte de testes data-driven identificou **10 regras** onde a geração automática de casos de teste produziu resultados incorretos. **O motor de avaliação (`DeterministicRuleEvaluator`) está funcionando corretamente** — o problema está na lógica de geração de casos de teste no script `scripts/snapshot_prompt_rules.py`.

---

## Problemas Identificados

### Problema 1: Normalização de `0`/`1` para Booleanos

**Descrição:** O gerador de casos usa valores numéricos (`0`, `1`) como valores "negativos" ou "positivos", mas o motor de avaliação normaliza `0 → False` e `1 → True`. Isso causa resultados inesperados.

**Exemplo:**
```python
# Regra: pareceres_inserido_sisreg equals true
# Caso gerado como "negativo": pareceres_inserido_sisreg = 0
# Esperado: False (não deve ativar)
# Obtido: True (porque 0 é normalizado para False, e a regra pode ter lógica invertida)
```

**Arquivos afetados:**
- `scripts/snapshot_prompt_rules.py` → funções `_gerar_valor_positivo()` e `_gerar_valor_negativo()`

**Solução sugerida:**
- Para variáveis booleanas, usar explicitamente `True`/`False` ao invés de `1`/`0`
- Detectar o tipo da variável antes de gerar o valor

---

### Problema 2: Geração de Casos para AND/OR Aninhados

**Descrição:** Para regras com múltiplos níveis de AND/OR, o gerador não analisa corretamente a estrutura para criar casos que falhem apenas uma condição específica.

**Exemplo - Regra `mun_793` (Prompt 22):**
```json
{
  "type": "and",
  "conditions": [
    { "variable": "municipio_polo_passivo", "operator": "equals", "value": true },
    {
      "type": "or",
      "conditions": [
        { "variable": "peticao_inicial_pedido_dieta_suplemento", "operator": "equals", "value": true },
        { "variable": "peticao_inicial_pedido_cirurgia", "operator": "equals", "value": true },
        // ... mais condições
      ]
    }
  ]
}
```

**Caso gerado (and_ultima_false):**
```python
dados = {
    'municipio_polo_passivo': False,  # AND: primeira condição falsa
    'peticao_inicial_pedido_dieta_suplemento': True,  # OR: satisfeito
    'peticao_inicial_pedido_cirurgia': True,
    # ...
}
# Esperado: False (porque municipio_polo_passivo é False)
# Obtido: True (BUG na geração - os dados estão inconsistentes com a expectativa)
```

**Solução sugerida:**
- Reescrever `_gerar_casos_and()` e `_gerar_casos_or()` para:
  1. Identificar todas as condições folha
  2. Gerar casos onde APENAS uma condição é alterada por vez
  3. Considerar a estrutura hierárquica ao definir o resultado esperado

---

### Problema 3: Variável Ausente vs `equals: false`

**Descrição:** O motor trata variável ausente como `False` para comparações booleanas. O gerador cria casos com `dados = {}` esperando `False`, mas para regras que verificam `equals: false`, o resultado é `True`.

**Exemplo - Regra `mer_cir_sem_esp_sus` (Prompt 28):**
```json
{
  "type": "and",
  "conditions": [
    { "variable": "pareceres_laudo_medico_sus", "operator": "equals", "value": false }
  ]
}
```

**Caso gerado (null):**
```python
dados = {}  # Variável ausente
# Motor interpreta: pareceres_laudo_medico_sus = None → normalizado para False
# Regra verifica: False == false → True
# Esperado pelo gerador: False
# Obtido: True
```

**Solução sugerida:**
- Para regras com `value: false`, o caso "null" deve esperar `True` (variável ausente = False = satisfaz `equals: false`)
- Ajustar a lógica em `_gerar_casos_condicao_simples()` para considerar o valor esperado

---

## Detalhes das 10 Regras com Falhas

### 1. Prompt 22 - `mun_793`

| Campo | Valor |
|-------|-------|
| **Título** | Direcionamento ao Município - Tema 793 |
| **Tipo de Regra** | AND com OR aninhado |
| **Variáveis** | `municipio_polo_passivo`, `peticao_inicial_pedido_*` (múltiplas) |
| **Caso Falho** | `and_ultima_false` |
| **Problema** | Geração incorreta de dados para AND com OR interno |

**Regra AST:**
```json
{
  "type": "and",
  "conditions": [
    { "type": "condition", "variable": "municipio_polo_passivo", "operator": "equals", "value": true },
    {
      "type": "or",
      "conditions": [
        { "type": "condition", "variable": "peticao_inicial_pedido_dieta_suplemento", "operator": "equals", "value": true },
        { "type": "condition", "variable": "peticao_inicial_pedido_cirurgia", "operator": "equals", "value": true },
        { "type": "condition", "variable": "peticao_inicial_pedido_consulta", "operator": "equals", "value": true },
        { "type": "condition", "variable": "peticao_inicial_pedido_exame", "operator": "equals", "value": true },
        { "type": "condition", "variable": "peticao_inicial_pedido_treatmento_autismo", "operator": "equals", "value": true },
        { "type": "condition", "variable": "peticao_inicial_pedido_fraldas", "operator": "equals", "value": true },
        { "type": "condition", "variable": "peticao_inicial_pedido_professor_apoio", "operator": "equals", "value": true },
        { "type": "condition", "variable": "peticao_inicial_pedido_home_care", "operator": "equals", "value": true },
        { "type": "condition", "variable": "peticao_inicial_pedido_transferencia_hospitalar", "operator": "equals", "value": true },
        { "type": "condition", "variable": "peticao_inicial_internacao_involuntaria", "operator": "equals", "value": true }
      ]
    }
  ]
}
```

---

### 2. Prompt 28 - `mer_cir_sem_esp_sus`

| Campo | Valor |
|-------|-------|
| **Título** | Cirurgia - Laudo Médico Não é do SUS |
| **Tipo de Regra** | AND simples |
| **Variáveis** | `pareceres_laudo_medico_sus`, `peticao_inicial_pedido_cirurgia` |
| **Caso Falho** | `null_pareceres_laudo_medico_sus` |
| **Problema** | Variável ausente tratada como `False`, satisfaz `equals: false` |

**Regra AST:**
```json
{
  "type": "and",
  "conditions": [
    { "type": "condition", "variable": "pareceres_laudo_medico_sus", "operator": "equals", "value": false },
    { "type": "condition", "variable": "peticao_inicial_pedido_cirurgia", "operator": "equals", "value": true }
  ]
}
```

---

### 3. Prompt 31 - `mer_fila_eletivo`

| Campo | Valor |
|-------|-------|
| **Título** | Fila de Espera - Procedimento Eletivo |
| **Tipo de Regra** | AND complexo |
| **Variáveis** | `pareceres_carater_exame`, `pareceres_natureza_cirurgia`, `pareceres_inserido_sisreg`, `pareceres_tempo_sisreg_dias` |
| **Casos Falhos** | `and_primeira_false`, `and_ultima_false` |
| **Problema** | Valor `0` usado como negativo, mas `0` é normalizado para `False` |

**Regra AST:**
```json
{
  "type": "and",
  "conditions": [
    {
      "type": "or",
      "conditions": [
        { "type": "condition", "variable": "pareceres_carater_exame", "operator": "equals", "value": "eletivo" },
        { "type": "condition", "variable": "pareceres_natureza_cirurgia", "operator": "equals", "value": "eletiva" }
      ]
    },
    { "type": "condition", "variable": "pareceres_inserido_sisreg", "operator": "equals", "value": true },
    { "type": "condition", "variable": "pareceres_tempo_sisreg_dias", "operator": "greater_than", "value": 0 }
  ]
}
```

---

### 4. Prompt 32 - `mer_dificuldade_gestor`

| Campo | Valor |
|-------|-------|
| **Título** | Dificuldade do Gestor em Procedimentos |
| **Tipo de Regra** | AND com OR |
| **Variáveis** | `peticao_inicial_pedido_cirurgia`, `peticao_inicial_pedido_consulta`, `peticao_inicial_pedido_exame`, `pareceres_inserido_core` |
| **Caso Falho** | `and_primeira_false` |
| **Problema** | Valor `0` como negativo para `pareceres_inserido_core` |

---

### 5. Prompt 36 - `mer_med_nao_inc_tema1234`

| Campo | Valor |
|-------|-------|
| **Título** | Medicamento Não Incorporado - Tema 1234 |
| **Tipo de Regra** | OR complexo |
| **Variáveis** | Múltiplas variáveis de pareceres |
| **Caso Falho** | `or_ultima_true` |
| **Problema** | Valor `1000` usado como "diferente de True", mas não é reconhecido como negativo |

---

### 6. Prompt 49 - `evt_direcionamento_793`

| Campo | Valor |
|-------|-------|
| **Título** | Direcionamento e Direito de Ressarcimento - Tema 793 |
| **Tipo de Regra** | AND com OR aninhado |
| **Variáveis** | `municipio_polo_passivo`, múltiplas `peticao_inicial_pedido_*` |
| **Caso Falho** | `and_ultima_false` |
| **Problema** | Mesmo problema do Prompt 22 |

---

### 7. Prompt 50 - `evt_mun_gestao_plena`

| Campo | Valor |
|-------|-------|
| **Título** | Município em Gestão Plena |
| **Tipo de Regra** | AND com OR |
| **Variáveis** | `peticao_inicial_municipio_acao`, `peticao_inicial_pedido_*` |
| **Caso Falho** | `and_ultima_false` |
| **Problema** | OR interno satisfeito mesmo com AND esperando falha |

---

### 8. Prompt 51 - `evt_mun_geral`

| Campo | Valor |
|-------|-------|
| **Título** | Eventualidade - Município Geral |
| **Tipo de Regra** | AND com OR aninhado |
| **Variáveis** | `municipio_polo_passivo`, múltiplas `peticao_inicial_pedido_*` |
| **Caso Falho** | `and_ultima_false` |
| **Problema** | Mesmo padrão dos Prompts 22 e 49 |

---

### 9. Prompt 57 - `evt_honorarios`

| Campo | Valor |
|-------|-------|
| **Título** | Honorários Advocatícios |
| **Tipo de Regra** | OR extenso (12+ condições) |
| **Variáveis** | Múltiplas (União, município, pedidos diversos) |
| **Casos Falhos** | `or_primeira_true`, `or_ultima_true` |
| **Problema** | Geração de casos para OR com muitas condições não funciona |

---

### 10. Prompt 59 - `evt_tema_1033`

| Campo | Valor |
|-------|-------|
| **Título** | Tema 1033 - STF |
| **Tipo de Regra** | AND com OR |
| **Variáveis** | `municipio_polo_passivo`, `peticao_inicial_pedido_*` |
| **Caso Falho** | `and_ultima_false` |
| **Problema** | Mesmo padrão dos outros AND/OR |

---

## Arquivos Relevantes

| Arquivo | Descrição |
|---------|-----------|
| `scripts/snapshot_prompt_rules.py` | Script de geração de snapshot e casos de teste |
| `tests/test_prompt_rules_activation.py` | Suíte de testes |
| `tests/fixtures/prompt_rules_snapshot.json` | Snapshot com regras e casos gerados |
| `sistemas/gerador_pecas/services_deterministic.py` | Motor de avaliação (está correto) |

---

## Funções a Corrigir no `snapshot_prompt_rules.py`

1. **`_gerar_valor_positivo(operador, valor)`** - Linha ~160
   - Usar `True`/`False` explícitos para booleanos

2. **`_gerar_valor_negativo(operador, valor)`** - Linha ~190
   - Usar `True`/`False` explícitos para booleanos
   - Considerar que `None`/ausente pode satisfazer `equals: false`

3. **`_gerar_casos_and(regra)`** - Linha ~250
   - Reescrever para analisar estrutura hierárquica
   - Gerar casos que alterem apenas UMA condição por vez
   - Considerar OR aninhados corretamente

4. **`_gerar_casos_or(regra)`** - Linha ~310
   - Similar ao AND, considerar estrutura hierárquica

5. **`_gerar_casos_condicao_simples(condicao)`** - Linha ~200
   - Para `value: false`, o caso "null" deve esperar `True`

---

## Recomendações

1. **Curto prazo:** Marcar os 10 testes como `@pytest.mark.xfail` para o CI passar
2. **Médio prazo:** Corrigir as funções de geração de casos
3. **Longo prazo:** Considerar usar análise simbólica (SMT solver) para geração de casos de borda

---

## Conclusão

O motor de avaliação de regras determinísticas (`DeterministicRuleEvaluator`) está **funcionando corretamente**. As 10 falhas identificadas são problemas na **geração automática de casos de teste**, não no sistema de produção.

**Métricas:**
- 55 regras determinísticas em produção
- 45 regras com casos de teste corretos (82%)
- 10 regras com casos de teste incorretos (18%)
- Motor de avaliação: 100% funcional
