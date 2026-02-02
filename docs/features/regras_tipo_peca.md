# Sistema de Regras Determinísticas por Tipo de Peça

## Visão Geral

Este documento descreve a evolução arquitetural do sistema de **PROMPTS MODULARES DE CONTEÚDO** para suportar regras determinísticas específicas por tipo de peça jurídica.

## Conceitos

### Regras Globais
Regras que se aplicam a **TODOS** os tipos de peça, independentemente do tipo selecionado ou detectado pela IA.

**Exemplo:** "Se valor da causa > 210 salários mínimos, ativar módulo de argumentação especial"

### Regras Específicas por Tipo de Peça
Regras que só se aplicam quando o tipo de peça corresponde ao configurado.

**Exemplo:** "Se autor possui Defensoria Pública E tipo de peça = Contestação, ativar módulo de gratuidade"

### Tipos de Peça Suportados
- `contestacao` - Contestação
- `recurso_apelacao` - Apelação
- `recurso_especial` - Recurso Especial
- `recurso_extraordinario` - Recurso Extraordinário
- `contrarrazoes_apelacao` - Contrarrazões de Apelação
- (outros conforme configuração do sistema)

## Modelo de Dados

### Tabela `regra_deterministica_tipo_peca`

```sql
CREATE TABLE regra_deterministica_tipo_peca (
    id INTEGER PRIMARY KEY,
    modulo_id INTEGER NOT NULL REFERENCES prompt_modulos(id) ON DELETE CASCADE,
    tipo_peca VARCHAR(50) NOT NULL,
    regra_deterministica JSON NOT NULL,      -- AST da regra
    regra_texto_original TEXT,               -- Descrição em linguagem natural
    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    criado_por INTEGER REFERENCES users(id),
    atualizado_por INTEGER REFERENCES users(id),
    UNIQUE(modulo_id, tipo_peca)             -- Uma regra por tipo de peça por módulo
);
```

### Relacionamentos
- `modulo_id` → `prompt_modulos.id` (N:1)
- Constraint UNIQUE garante no máximo uma regra por tipo de peça por módulo

## Lógica de Avaliação

### Ordem de Avaliação
1. Avalia regra **GLOBAL** (do `PromptModulo.regra_deterministica`)
2. Se `tipo_peca` fornecido, avalia regra **ESPECÍFICA** (de `RegraDeterministicaTipoPeca`)

### Lógica OR
```
ATIVAÇÃO = regra_global == TRUE OU regra_especifica == TRUE
```

- Se regra GLOBAL retorna `True` → módulo ativado (não avalia específica)
- Se regra GLOBAL retorna `False` ou `None` → avalia regra específica
- Se regra ESPECÍFICA retorna `True` → módulo ativado
- Se AMBAS retornam `False` → módulo não ativado
- Se não há regras configuradas → resultado indeterminado (`None`)

### Compatibilidade com "IA Decide"
Quando o usuário seleciona "Detectar automaticamente (IA decide)":

1. O sistema detecta o tipo de peça via IA
2. O tipo detectado (`tipo_peca_final`) é usado para:
   - Filtrar módulos aplicáveis ao tipo
   - Avaliar regras ESPECÍFICAS do tipo detectado
   - Avaliar regras GLOBAIS normalmente

## API Endpoints

### Listar Regras por Tipo de Peça
```
GET /admin/prompt-modulos/{modulo_id}/regras-tipo-peca
```

**Resposta:**
```json
[
    {
        "id": 1,
        "modulo_id": 123,
        "tipo_peca": "contestacao",
        "regra_deterministica": {"type": "condition", ...},
        "regra_texto_original": "Se autor possui Defensoria...",
        "ativo": true,
        "criado_em": "2025-01-20T10:00:00"
    }
]
```

### Criar Regra por Tipo de Peça
```
POST /admin/prompt-modulos/{modulo_id}/regras-tipo-peca
```

**Body:**
```json
{
    "tipo_peca": "contestacao",
    "regra_deterministica": {
        "type": "condition",
        "variable": "autor_com_defensoria",
        "operator": "equals",
        "value": true
    },
    "regra_texto_original": "Se autor possui Defensoria Pública",
    "ativo": true
}
```

### Atualizar Regra
```
PUT /admin/prompt-modulos/regras-tipo-peca/{regra_id}
```

### Excluir Regra
```
DELETE /admin/prompt-modulos/regras-tipo-peca/{regra_id}
```

### Ativar/Desativar Regra
```
PATCH /admin/prompt-modulos/regras-tipo-peca/{regra_id}/toggle
```

## Uso no Frontend

### Localização
A interface de regras por tipo de peça está em `/admin/prompts-modulos`, no modal de edição de cada módulo.

### Seção "Regras por Tipo de Peça"
Exibida abaixo da regra global (REGRA DETERMINÍSTICA), contém:
- Lista de regras existentes com status (ativo/inativo)
- Botão "Adicionar Regra por Tipo"
- Opções de editar/excluir por regra

### Modal de Criação/Edição
- Campo: Tipo de Peça (select com tipos disponíveis)
- Campo: Regra em formato de texto natural
- Botão: Converter para JSON (usando serviço de conversão)

## Formato AST de Regras

### Condição Simples
```json
{
    "type": "condition",
    "variable": "valor_causa_superior_210sm",
    "operator": "equals",
    "value": true
}
```

### Operador AND
```json
{
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "var1", "operator": "equals", "value": true},
        {"type": "condition", "variable": "var2", "operator": "equals", "value": false}
    ]
}
```

### Operador OR
```json
{
    "type": "or",
    "conditions": [
        {"type": "condition", "variable": "var1", "operator": "equals", "value": true},
        {"type": "condition", "variable": "var2", "operator": "equals", "value": true}
    ]
}
```

### Operadores Suportados
- `equals` - Igualdade
- `not_equals` - Diferença
- `contains` - Contém (para strings/listas)
- `not_contains` - Não contém
- `greater_than` - Maior que
- `less_than` - Menor que
- `in` - Está na lista
- `not_in` - Não está na lista

## Migração de Dados

### Regras Existentes
Todas as regras determinísticas existentes são consideradas **GLOBAIS** e continuam funcionando normalmente.

### Nova Tabela
A migração cria automaticamente a tabela `regra_deterministica_tipo_peca` na primeira execução do sistema.

## Testes

### Suíte de Testes
Arquivo: `tests/test_regras_tipo_peca.py`

### Cenários Cobertos
1. **Regras Globais Sozinhas**
   - Ativação quando satisfeita
   - Não ativação quando não satisfeita
   - Comportamento com variáveis ausentes

2. **Regras Específicas Sozinhas**
   - Ativação quando tipo corresponde
   - Não ativação quando tipo é diferente
   - Regras inativas não são avaliadas

3. **Combinação Global + Específica**
   - Global TRUE, Específica FALSE → Ativa
   - Global FALSE, Específica TRUE → Ativa
   - Ambas FALSE → Não ativa
   - Ambas TRUE → Ativa pela global (primeira)

4. **Modo "IA Decide"**
   - Detecção de contestação aplica regras de contestação
   - Detecção de apelação aplica regras de apelação
   - Regras globais sempre avaliadas

5. **Fallback**
   - Tipo nulo usa apenas global
   - Tipo inexistente não quebra

6. **Retrocompatibilidade**
   - Comportamento sem tipo preservado
   - Seleção manual funciona igual detecção

### Executar Testes
```bash
cd portal-pge
python -m pytest tests/test_regras_tipo_peca.py -v
```

## Arquivos Principais

| Arquivo | Descrição |
|---------|-----------|
| `admin/models_prompts.py` | Modelo ORM `RegraDeterministicaTipoPeca` |
| `database/init_db.py` | Migração de banco de dados |
| `sistemas/gerador_pecas/services_deterministic.py` | Lógica de avaliação |
| `sistemas/gerador_pecas/detector_modulos.py` | Integração com detector |
| `admin/router_prompts.py` | Endpoints da API |
| `frontend/templates/admin_prompts_modulos.html` | Interface de usuário |
| `tests/test_regras_tipo_peca.py` | Testes automatizados |

## Histórico de Versões

| Data | Versão | Descrição |
|------|--------|-----------|
| 2025-01-20 | 1.0 | Implementação inicial do sistema de regras por tipo de peça |
