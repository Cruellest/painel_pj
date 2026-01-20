# Testes de Regras Determinísticas de Ativação

Este diretório contém a suíte de testes automatizados para validar as regras determinísticas de ativação dos prompts modulares.

## Arquitetura

```
tests/
├── fixtures/
│   └── prompt_rules_snapshot.json    # Snapshot das regras (gerado)
├── reports/
│   └── prompt_rules_coverage.md      # Relatório de cobertura (gerado)
├── test_prompt_rules_activation.py   # Suíte de testes data-driven
└── README_REGRAS_DETERMINISTICAS.md  # Este arquivo

scripts/
└── snapshot_prompt_rules.py          # Script de extração de regras
```

## Fluxo de Trabalho

### 1. Gerar Snapshot das Regras (Produção)

Execute o script de snapshot para extrair as regras do banco de produção:

```bash
python scripts/snapshot_prompt_rules.py
```

**Saídas:**
- `tests/fixtures/prompt_rules_snapshot.json` - Snapshot das regras
- `tests/reports/prompt_rules_coverage.md` - Relatório de cobertura

**Requisitos:**
- `DATABASE_URL` configurada no `.env`

### 2. Executar Testes

Os testes usam o snapshot local e NÃO dependem do banco de produção:

```bash
# Todos os testes
pytest tests/test_prompt_rules_activation.py -v

# Apenas testes de regras específicas
pytest tests/test_prompt_rules_activation.py -v -k "test_regra_"

# Apenas testes de cobertura
pytest tests/test_prompt_rules_activation.py -v -k "TestCobertura"

# Com output resumido
pytest tests/test_prompt_rules_activation.py -v --tb=short
```

### 3. Verificar Cobertura

O relatório de cobertura é gerado automaticamente pelo script de snapshot:

```bash
cat tests/reports/prompt_rules_coverage.md
```

## Estrutura do Snapshot

```json
{
  "timestamp": "2024-01-15T10:30:00",
  "versao_snapshot": "1.0",
  "regras": [
    {
      "prompt_id": 22,
      "prompt_nome": "contestacao_medicamentos_nat",
      "regra_primaria": { "type": "and", "conditions": [...] },
      "variaveis_primaria": ["pareceres_medicamento_nao_incorporado_sus", "valor_causa_superior_210sm"],
      "casos_teste_primaria": [
        { "nome": "and_todas_true", "dados": {...}, "esperado": true },
        { "nome": "and_primeira_false", "dados": {...}, "esperado": false }
      ]
    }
  ],
  "variaveis": [...],
  "estatisticas": {
    "total_prompts_deterministicos": 5,
    "total_casos_teste_gerados": 45
  }
}
```

## Tipos de Testes

### Testes Unitários do Avaliador
- Operadores de comparação (`equals`, `greater_than`, `contains`, etc.)
- Operadores lógicos (`and`, `or`, `not`)
- Normalização de valores (booleanos, moeda brasileira)
- Variáveis ausentes/nulas

### Testes Data-Driven (Gerados do Snapshot)
Para cada regra no snapshot:
- **Caso positivo**: dados que DEVEM ativar a regra
- **Caso negativo**: dados que NÃO DEVEM ativar a regra
- **Casos de borda**: valores limítrofes para operadores numéricos

### Testes de Cobertura
- Todas as regras têm caso positivo
- Todas as regras têm caso negativo
- Cobertura mínima de 100%

### Testes de Performance
- Avaliação < 10ms por regra
- Resultados determinísticos

## Critérios de Aceite

1. **100% de cobertura**: Todas as regras têm pelo menos 1 caso positivo e 1 negativo
2. **Determinístico**: Testes rodam sem acesso ao banco de produção
3. **Rastreabilidade**: Cada falha indica claramente:
   - Qual regra falhou
   - Qual prompt está associado
   - Quais dados causaram a falha
   - Qual era o resultado esperado vs obtido

## Manutenção

### Quando atualizar o snapshot:
- Após criar/modificar regras determinísticas
- Após adicionar novas variáveis
- Semanalmente (recomendado)

### Quando os testes falham:
1. Verifique se a regra foi alterada intencionalmente
2. Se sim, regenere o snapshot: `python scripts/snapshot_prompt_rules.py`
3. Se não, investigue o bug no motor de avaliação

## Integração com CI/CD

Adicione ao pipeline:

```yaml
- name: Gerar snapshot de regras
  run: python scripts/snapshot_prompt_rules.py
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}

- name: Executar testes de regras
  run: pytest tests/test_prompt_rules_activation.py -v --tb=short
```

## Limitações Conhecidas

1. **Variáveis externas**: Variáveis calculadas em runtime (ex: do XML do processo) são testadas com valores mock
2. **Integrações**: Regras que dependem de serviços externos são testadas com mocks
3. **Snapshot defasado**: Se o snapshot estiver desatualizado, testes podem passar mesmo com bugs
