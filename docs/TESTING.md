# Testes

## Visao geral

- Estrutura baseada em `unittest` (Python stdlib).
- Alguns testes sao scripts executaveis (nao usam discovery).
- A pasta `tests/ia_extracao_regras` contem suites unitarias, integracao e e2e.

## Como rodar

### Rodar suite completa (unittest discovery)

```bash
python -m unittest
```

### Rodar arquivo especifico

```bash
python -m unittest tests.test_prompt_groups
python -m unittest tests.ia_extracao_regras.backend.unit.test_extraction_deterministic
```

### Teste de agrupamento logico (script)

```bash
python tests/test_deterministic_grouping.py
```

### E2E pedido de calculo (script)

```bash
python sistemas/pedido_calculo/test_e2e.py <caminho_xml>
```

## Estrutura das suites

- `tests/test_prompt_groups.py`
  - Valida grupos/subgrupos e filtros no gerador de pecas.

- `tests/test_deterministic_grouping.py`
  - Script de validacao de regras deterministicas (AND/OR/NOT).

- `tests/ia_extracao_regras/`
  - `backend/unit/` (validacao de regras, schema, dependencias)
  - `backend/integration/` (endpoints e migrations)
  - `backend/runtime/` (avaliacao deterministica em runtime)
  - `frontend/` (API de variaveis)
  - `e2e/` (fluxo completo)
  - `mocks/` (Gemini mockado)

Resultados detalhados: `tests/ia_extracao_regras/TEST_RESULTS.md`.

## Como criar novos testes

1) Preferir `unittest.TestCase` na pasta `tests/`.
2) Reutilizar fixtures em `tests/ia_extracao_regras/fixtures` quando aplicavel.
3) Evitar testes que dependem de rede (use mocks em `tests/ia_extracao_regras/mocks`).
4) Se for integracao, isolar DB em memoria (`sqlite:///:memory:`).

## Lacunas conhecidas

- Nao ha suite formal para `assistencia_judiciaria` e `matriculas_confrontantes`.
- Testes de UI nao estao presentes.
