# Sistema de Extração e Regras Determinísticas

Este documento descreve o sistema de extração de dados e regras determinísticas implementado no Portal PGE-MS.

## Visão Geral

O sistema implementa três modos de operação:

1. **Modo Legado (Manual)**: Schema JSON definido manualmente
2. **Modo IA (AI Generated)**: Schema gerado por IA a partir de perguntas em linguagem natural
3. **Modo Determinístico**: Regras de ativação de prompts avaliadas sem LLM

## Arquitetura

### Modelos de Dados

```
sistemas/gerador_pecas/models_extraction.py
```

- **ExtractionQuestion**: Perguntas de extração em linguagem natural
- **ExtractionModel**: Modelo de extração (manual ou gerado por IA)
- **ExtractionVariable**: Variáveis normalizadas do sistema
- **PromptVariableUsage**: Rastreamento de uso de variáveis em prompts
- **PromptActivationLog**: Log de ativação de prompts para auditoria

### Serviços

```
sistemas/gerador_pecas/services_extraction.py
```
- **ExtractionSchemaGenerator**: Converte perguntas em linguagem natural para schema JSON
- **ExtractionSchemaValidator**: Valida schemas de extração

```
sistemas/gerador_pecas/services_deterministic.py
```
- **DeterministicRuleGenerator**: Converte condições em linguagem natural para AST JSON
- **DeterministicRuleEvaluator**: Avalia regras no runtime sem LLM
- **PromptVariableUsageSync**: Sincroniza uso de variáveis quando regras são modificadas

## Modo Legado (Manual)

No modo legado, o administrador define manualmente o schema JSON de extração:

```json
{
  "nome_autor": {"type": "text", "description": "Nome do autor"},
  "valor_causa": {"type": "currency", "description": "Valor da causa"},
  "tipo_acao": {
    "type": "choice",
    "description": "Tipo da ação",
    "options": ["Medicamentos", "Cirurgia", "Outros"]
  }
}
```

### Tipos de Dados Suportados

| Tipo | Descrição |
|------|-----------|
| `text` | Texto livre |
| `number` | Valor numérico |
| `date` | Data (formato YYYY-MM-DD) |
| `boolean` | Sim/Não |
| `choice` | Escolha única entre opções |
| `list` | Lista de valores |
| `currency` | Valor monetário |

## Modo IA (AI Generated)

### Fluxo de Trabalho

1. **Criar Perguntas**: O usuário escreve perguntas em linguagem natural
   ```
   "Qual é o nome completo do autor da ação?"
   "O medicamento solicitado está na lista RENAME?"
   "Qual é o valor total da causa?"
   ```

2. **Sugestões Opcionais**: O usuário pode sugerir:
   - Nome da variável (ex: `nome_autor`)
   - Tipo de dado (ex: `text`, `boolean`)
   - Opções para múltipla escolha

3. **Geração Automática**: A IA (Gemini 3 Flash Preview) converte as perguntas em:
   - Schema JSON estruturado
   - Variáveis normalizadas
   - Mapeamento pergunta → variável

### Exemplo de Uso

```python
# Endpoint: POST /admin/api/extraction/schemas/gerar
{
  "categoria_id": 1,
  "categoria_nome": "Medicamentos",
  "perguntas": [
    {
      "pergunta": "Qual é o nome do medicamento solicitado?",
      "nome_variavel_sugerido": "nome_medicamento",
      "tipo_sugerido": "text"
    },
    {
      "pergunta": "O medicamento está na lista RENAME?",
      "tipo_sugerido": "boolean"
    }
  ]
}
```

## Modo Determinístico

### Regras AST JSON

As regras determinísticas são representadas como AST (Abstract Syntax Tree) JSON:

#### Condição Simples
```json
{
  "type": "condition",
  "variable": "valor_causa",
  "operator": "greater_than",
  "value": 100000
}
```

#### Operadores Lógicos

**AND** - Todas as condições devem ser verdadeiras:
```json
{
  "type": "and",
  "conditions": [
    {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": true},
    {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 50000}
  ]
}
```

**OR** - Pelo menos uma condição deve ser verdadeira:
```json
{
  "type": "or",
  "conditions": [
    {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": true},
    {"type": "condition", "variable": "autor_crianca", "operator": "equals", "value": true}
  ]
}
```

**NOT** - Negação:
```json
{
  "type": "not",
  "conditions": [
    {"type": "condition", "variable": "status", "operator": "equals", "value": "arquivado"}
  ]
}
```

### Operadores de Comparação

| Operador | Descrição | Exemplo |
|----------|-----------|---------|
| `equals` | Igualdade (case insensitive para strings) | `"valor": "medicamentos"` |
| `not_equals` | Diferente de | `"valor": "arquivado"` |
| `contains` | Contém texto | `"valor": "insulina"` |
| `not_contains` | Não contém texto | `"valor": "urgente"` |
| `starts_with` | Começa com | `"valor": "0001234"` |
| `ends_with` | Termina com | `"valor": "0001"` |
| `greater_than` | Maior que | `"valor": 100000` |
| `less_than` | Menor que | `"valor": 18` |
| `greater_or_equal` | Maior ou igual | `"valor": 60` |
| `less_or_equal` | Menor ou igual | `"valor": 1000` |
| `is_empty` | Está vazio/nulo | `"value": true` |
| `is_not_empty` | Não está vazio | `"value": true` |
| `in_list` | Está na lista | `"value": ["MS", "MT", "GO"]` |
| `not_in_list` | Não está na lista | `"value": ["SP", "RJ"]` |
| `matches_regex` | Corresponde ao regex | `"value": "^\\d{3}\\.\\d{3}"` |

### Geração de Regras por IA

O usuário pode escrever condições em linguagem natural:

```
"O valor da causa é maior que 100000 e o autor é idoso"
"O medicamento é de alto custo ou não está na lista RENAME"
"O processo não está arquivado"
```

A IA converte automaticamente para AST JSON usando o endpoint:
```
POST /admin/api/extraction/regras-deterministicas/gerar
```

### Avaliação no Runtime

As regras determinísticas são avaliadas sem chamar LLM:

```python
from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator

evaluator = DeterministicRuleEvaluator()

regra = {
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": True},
        {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 50000}
    ]
}

dados = {"autor_idoso": True, "valor_causa": 100000}

resultado = evaluator.avaliar(regra, dados)  # True
```

## Painel de Variáveis

O painel administrativo de variáveis está disponível em:
```
/admin/variaveis
```

### Funcionalidades

1. **Resumo**: Cards com estatísticas (total, em uso, não utilizadas, por tipo)
2. **Listagem**: Tabela com busca, filtros por tipo e categoria
3. **CRUD**: Criar, editar e excluir variáveis
4. **Detalhes**: Ver quais prompts usam cada variável

## Endpoints da API

### Extração

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/admin/api/extraction/categorias` | Lista categorias |
| GET | `/admin/api/extraction/categorias/{id}` | Detalhes de categoria |
| GET | `/admin/api/extraction/perguntas/{categoria_id}` | Perguntas de uma categoria |
| POST | `/admin/api/extraction/perguntas` | Criar pergunta |
| PUT | `/admin/api/extraction/perguntas/{id}` | Atualizar pergunta |
| DELETE | `/admin/api/extraction/perguntas/{id}` | Excluir pergunta |
| POST | `/admin/api/extraction/schemas/gerar` | Gerar schema por IA |
| POST | `/admin/api/extraction/schemas/validar` | Validar schema |

### Regras Determinísticas

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| POST | `/admin/api/extraction/regras-deterministicas/gerar` | Gerar regra por IA |
| POST | `/admin/api/extraction/regras-deterministicas/validar` | Validar regra |
| POST | `/admin/api/extraction/regras-deterministicas/avaliar` | Avaliar regra com dados |

### Variáveis

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/admin/api/extraction/variaveis` | Listar variáveis |
| GET | `/admin/api/extraction/variaveis/{id}` | Detalhes de variável |
| POST | `/admin/api/extraction/variaveis` | Criar variável |
| PUT | `/admin/api/extraction/variaveis/{id}` | Atualizar variável |
| DELETE | `/admin/api/extraction/variaveis/{id}` | Excluir variável |
| GET | `/admin/api/extraction/variaveis/resumo` | Resumo estatístico |

## Migração de Dados

As migrações são executadas automaticamente pelo `database/init_db.py`:

```python
# Tabelas criadas:
# - extraction_questions
# - extraction_models
# - extraction_variables
# - prompt_variable_usage
# - prompt_activation_logs

# Colunas adicionadas em prompt_modulos:
# - modo_ativacao (llm | deterministic)
# - regra_deterministica (JSON)
# - regra_texto_original (TEXT)
```

## Testes

Os testes automatizados estão em:
```
tests/test_extraction_deterministic.py
```

Para executar:
```bash
python -m unittest tests.test_extraction_deterministic -v
```

### Cobertura dos Testes

- Validação de schemas (tipos, opções, padrões)
- Avaliação de todos os operadores de comparação
- Operadores lógicos (AND, OR, NOT)
- Condições aninhadas
- Sincronização de uso de variáveis
- Compatibilidade com modo legado
- Normalização de slugs
- Conversão de números (formato brasileiro)

## Modelo de IA

O sistema usa obrigatoriamente o modelo `gemini-3-flash-preview` para:
- Geração de schemas de extração
- Geração de regras determinísticas

A temperatura é configurada como `0.1` para maximizar consistência e determinismo nas respostas.
