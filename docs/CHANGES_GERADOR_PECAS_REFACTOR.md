# CHANGES: Refactoring do Gerador de Pecas

> Documentacao das alteracoes realizadas no refactoring do sistema de geracao de pecas juridicas.
> Data: 2026-01-24

## Resumo Executivo

Este refactoring focou em:
1. **Centralizacao de constantes** - Criacao de `constants.py` para eliminar magic numbers/strings
2. **Padronizacao de erros** - Criacao de `exceptions.py` com excecoes de dominio
3. **Correcao de testes quebrados** - Varios testes estavam falhando por mudancas de API
4. **Documentacao de onboarding** - Guia para novos desenvolvedores
5. **Atualizacao de documentacao tecnica** - Refletir nova estrutura

## Alteracoes por Modulo

### 1. sistemas/gerador_pecas/constants.py (NOVO)

**Objetivo**: Centralizar todas as constantes usadas pelo sistema.

**Conteudo**:
- Timeouts (AG2_DETECCAO, TJMS, GEMINI, DOCX)
- Modelos de IA padrao
- Codigos de documento TJ-MS
- Limites de processamento
- Salarios minimos e limites financeiros
- Categorias de prompts e modos de ativacao
- Mensagens de erro padronizadas

**Beneficios**:
- Elimina magic numbers espalhados pelo codigo
- Facilita ajuste de configuracoes
- Melhora legibilidade

### 2. sistemas/gerador_pecas/exceptions.py (NOVO)

**Objetivo**: Excecoes customizadas do dominio.

**Hierarquia**:
```
GeradorPecasError (base)
├── TJMSError
│   ├── TJMSTimeoutError
│   └── TJMSProcessoNaoEncontradoError
├── GeminiError
│   ├── GeminiTimeoutError
│   └── GeminiRateLimitError
├── ValidationError
│   ├── TipoPecaInvalidoError
│   ├── GrupoNaoPermitidoError
│   └── CNJInvalidoError
├── ProcessamentoError
│   ├── Agente1Error
│   ├── Agente2Error
│   ├── Agente3Error
│   ├── DocumentoError
│   ├── ExtracaoError
│   └── DocxConversionError
└── RegraError
    ├── RegraInvalidaError
    └── VariavelNaoEncontradaError
```

**Beneficios**:
- Tratamento de erro mais preciso
- Mensagens padronizadas
- Facilita debug e logging

### 3. sistemas/bert_training/models.py (CORRECAO)

**Problema**: Indice `ix_bert_logs_timestamp` estava duplicado.
- Coluna `timestamp` tinha `index=True`
- `__table_args__` tambem definia o indice explicito

**Correcao**: Removido `index=True` da coluna, mantendo apenas a definicao em `__table_args__`.

### 4. tests/ (CORRECOES)

#### test_detector_with_process_vars.py
- **Problema**: `import asyncio` estava no final do arquivo, apos seu uso
- **Correcao**: Movido para o topo do arquivo

#### test_process_variables.py
- **Problema**: Importava funcao inexistente `_resolver_ajuizado_apos_tema_106`
- **Correcao**: Atualizado para `_resolver_ajuizado_apos_2024_09_19`

#### test_bert_training.py
- **Problema**: Usava `_can_import_torch()` que nao existia
- **Correcao**: Adicionada a funcao helper

#### test_prompt_groups.py
- **Problema**: Teste esperava comportamento antigo de filtragem de subcategorias
- **Correcao**: Atualizado para refletir comportamento atual (modulos sem subcategoria sao "universais")

#### test_services_tjms.py (REESCRITO)
- **Problema**: Usava API antiga (`_get_downloader`) que nao existe mais
- **Correcao**: Reescrito para usar nova API do TJMSClient unificado (`_get_client`)

### 5. docs/onboarding_gerador_pecas.md (NOVO)

Guia pratico para desenvolvedores iniciando no sistema, contendo:
- Visao geral rapida
- Arquitetura em 3 agentes
- Estrutura de arquivos
- Como rodar localmente
- Fluxo principal (processar-stream)
- Sistema de prompts modulares
- Debugando selecao deterministica
- Testando geracao DOCX
- Armadilhas comuns
- Checklist de PR

### 6. docs/sistemas/gerador_pecas.md (ATUALIZADO)

Adicionado:
- Referencias aos novos arquivos (constants.py, exceptions.py)
- Link para documentacao de onboarding

## Estrutura Antes/Depois

### Antes
```
sistemas/gerador_pecas/
├── router.py
├── services.py
├── orquestrador_agentes.py
├── agente_tjms.py
├── ... (outros arquivos)
└── models.py
```

### Depois
```
sistemas/gerador_pecas/
├── router.py
├── services.py
├── orquestrador_agentes.py
├── agente_tjms.py
├── constants.py          # NOVO - constantes centralizadas
├── exceptions.py         # NOVO - excecoes de dominio
├── ... (outros arquivos)
└── models.py
```

## Como Validar

```bash
# 1. Rodar testes core
pytest tests/test_deterministic_rules.py tests/test_docx_list_numbering.py -v

# 2. Verificar imports dos novos modulos
python -c "from sistemas.gerador_pecas.constants import *; from sistemas.gerador_pecas.exceptions import *; print('OK')"

# 3. Rodar testes completos
python run_tests.py tests/ --ignore=tests/load --ignore=tests/e2e -q
```

## Riscos e Pontos de Atencao

1. **constants.py ainda nao esta sendo usado**
   - Os novos arquivos foram criados mas o codigo existente ainda usa valores hardcoded
   - Proxima iteracao: substituir gradualmente os valores hardcoded por referencias a constants.py

2. **exceptions.py ainda nao esta sendo usado**
   - As excecoes foram definidas mas o codigo existente ainda usa Exception generica
   - Proxima iteracao: substituir raises por excecoes especificas

3. **Testes de integracao**
   - Alguns testes de integracao foram corrigidos, mas a suite completa pode ter outros problemas
   - Recomendado: rodar suite completa em ambiente isolado

## Metricas

| Metrica | Antes | Depois |
|---------|-------|--------|
| Testes core passando | N/A (erros) | 67 |
| Erros de coleta | 3 | 0 |
| Arquivos novos | 0 | 3 |
| Documentacao | Incompleta | Atualizada |

## Fase 2: Migracao para Constantes (Em Andamento)

### orquestrador_agentes.py
- **Antes**: Constantes locais `MODELO_AGENTE1_PADRAO`, `TIMEOUT_AG2_DETECCAO`, `TIMEOUT_AG2_FAST_PATH`
- **Depois**: Importadas de `constants.py`

### detector_modulos.py
- **Antes**: Strings hardcoded para modos de ativacao
- **Depois**: Importa `MODO_ATIVACAO_*` de `constants.py`

## Proximos Passos Recomendados

1. ~~Migrar codigo para usar `constants.py` gradualmente~~ (parcialmente feito)
2. Substituir `Exception` por excecoes especificas de `exceptions.py`
3. Adicionar mais testes de integracao
4. Refatorar arquivos grandes (router.py, services_deterministic.py)
5. Implementar circuit breaker para chamadas externas
