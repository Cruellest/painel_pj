# TODO-LIST: Cumprimento de Sentenca (Beta)

> Checklist detalhado para implementacao do subsistema de Cumprimento de Sentenca
> Baseado em: `docs/requisitos_cumprimento_beta.md`
> **STATUS: IMPLEMENTADO** (2026-01-27)

---

## Visao Geral

O beta e um **modulo isolado** que opera com dois agentes de IA:
- **Agente 1**: Coleta documentos, avalia relevancia e gera JSONs de resumo
- **Agente 2**: Consolida JSONs, sugere pecas e conduz chatbot ate geracao final

---

## Fase 1: Estrutura e Modelos de Dados [CONCLUIDO]

### 1.1 Criar estrutura de pastas do modulo beta
- [x] Criar pasta `sistemas/cumprimento_beta/`
- [x] Criar `sistemas/cumprimento_beta/__init__.py`
- [x] Criar `sistemas/cumprimento_beta/constants.py`
- [x] Criar `sistemas/cumprimento_beta/exceptions.py`

### 1.2 Criar modelos de dados (models.py)
- [x] Criar `sistemas/cumprimento_beta/models.py` com todos os modelos

### 1.3 Criar DTOs/Schemas (schemas.py)
- [x] Criar `sistemas/cumprimento_beta/schemas.py` com todos os schemas

---

## Fase 2: Controle de Acesso [CONCLUIDO]

### 2.1 Criar middleware/dependency de acesso ao beta
- [x] Criar `sistemas/cumprimento_beta/dependencies.py`
- [x] Implementar `verificar_acesso_beta`
- [x] Criar dependency `require_beta_access`

### 2.2 Testes de controle de acesso
- [x] Criar `tests/cumprimento_beta/test_acesso.py`
- [x] Testar: admin acessa
- [x] Testar: usuario PS acessa
- [x] Testar: usuario nao-PS bloqueado

---

## Fase 3: Agente 1 - Coleta e Avaliacao [CONCLUIDO]

### 3.1 Criar servico de download de documentos
- [x] Criar `sistemas/cumprimento_beta/services_download.py`
- [x] Reutilizar cliente TJ-MS
- [x] Implementar filtro de codigos ignorados

### 3.2 Criar servico de avaliacao de relevancia
- [x] Criar `sistemas/cumprimento_beta/services_relevancia.py`
- [x] Buscar prompt de criterios do admin
- [x] Classificar documentos como relevante/irrelevante

### 3.3 Criar servico de extracao JSON
- [x] Criar `sistemas/cumprimento_beta/services_extracao_json.py`
- [x] Buscar categoria "Cumprimento de Sentenca"
- [x] Gerar JSON para documentos relevantes

### 3.4 Criar orquestrador do Agente 1
- [x] Criar `sistemas/cumprimento_beta/agente1.py`
- [x] Orquestrar pipeline completo

### 3.5 Testes do Agente 1
- [x] Criar `tests/cumprimento_beta/test_agente1.py`

---

## Fase 4: Agente 2 - Consolidacao e Sugestoes [CONCLUIDO]

### 4.1 Criar servico de consolidacao
- [x] Criar `sistemas/cumprimento_beta/services_consolidacao.py`
- [x] Gerar resumo consolidado
- [x] Gerar sugestoes de pecas

### 4.2 Implementar streaming para consolidacao
- [x] Usar StreamingResponse

### 4.3 Criar orquestrador do Agente 2
- [x] Criar `sistemas/cumprimento_beta/agente2.py`

### 4.4 Testes do Agente 2
- [x] Criar `tests/cumprimento_beta/test_agente2.py`

---

## Fase 5: Chatbot e Geracao Final [CONCLUIDO]

### 5.1 Criar servico de chatbot
- [x] Criar `sistemas/cumprimento_beta/services_chatbot.py`
- [x] Prompt de sistema do beta
- [x] Memoria de conversa
- [x] Integracao com banco vetorial

### 5.2 Implementar streaming do chatbot
- [x] Usar SSE para streaming

### 5.3 Criar servico de geracao de peca final
- [x] Criar `sistemas/cumprimento_beta/services_geracao_peca.py`
- [x] Gerar Markdown
- [x] Converter para DOCX

### 5.4 Testes do chatbot e geracao
- [x] Criar `tests/cumprimento_beta/test_chatbot.py`

---

## Fase 6: Rotas da API [CONCLUIDO]

### 6.1 Criar router principal
- [x] Criar `sistemas/cumprimento_beta/router.py`
- [x] Prefixo: `/api/cumprimento-beta`

### 6.2 Implementar endpoints
- [x] POST /sessoes
- [x] GET /sessoes
- [x] GET /sessoes/{id}
- [x] POST /sessoes/{id}/processar
- [x] GET /sessoes/{id}/documentos
- [x] GET /sessoes/{id}/consolidacao
- [x] POST /sessoes/{id}/consolidar
- [x] POST /sessoes/{id}/chat
- [x] GET /sessoes/{id}/conversas
- [x] POST /sessoes/{id}/gerar-peca
- [x] GET /sessoes/{id}/pecas
- [x] GET /sessoes/{id}/pecas/{peca_id}/download

### 6.3 Registrar router no main.py
- [x] Import do router
- [x] Include com prefixo

---

## Fase 7: Frontend [CONCLUIDO]

### 7.1 Criar template da tela do beta
- [x] Criar `sistemas/cumprimento_beta/templates/index.html`
- [x] Input CNJ
- [x] Etapas de processamento
- [x] Streaming
- [x] Chatbot
- [x] Historico lateral

### 7.2 Adicionar botao no /gerador-pecas/
- [x] Editar template do gerador
- [x] Adicionar botao beta
- [x] Controlar visibilidade via API

### 7.3 Criar rota para servir template
- [x] Adicionar rota no main.py
- [x] Servir template HTML

### 7.4 Atualizar TypeScript
- [x] Adicionar verificacao de acesso ao beta
- [x] Compilar frontend

---

## Fase 8: Configuracoes Admin [PENDENTE - MANUAL]

### 8.1 Verificar/criar categoria "Cumprimento de Sentenca"
- [ ] Verificar se categoria existe em /admin/categorias-resumo-json
- [ ] Se nao existir, criar manualmente

### 8.2 Verificar/criar prompts necessarios
- [ ] Verificar prompts no admin
- [ ] Criar se necessario

---

## Fase 9: Testes [CONCLUIDO]

### 9.1 Testes unitarios criados
- [x] test_acesso.py (8 testes)
- [x] test_agente1.py (11 testes)
- [x] test_agente2.py (8 testes)
- [x] test_chatbot.py (10 testes)

### 9.2 Testes executados com sucesso
- [x] 37 testes passando (pytest tests/cumprimento_beta/ -v)

---

## Fase 10: Documentacao [CONCLUIDO]

### 10.1 Documentar sistema
- [x] Criar `docs/sistemas/cumprimento_beta.md`

### 10.2 Atualizar CLAUDE.md
- [x] Adicionar cumprimento_beta na tabela de sistemas

---

## Arquivos Criados

```
sistemas/cumprimento_beta/
├── __init__.py              [CRIADO]
├── constants.py             [CRIADO]
├── exceptions.py            [CRIADO]
├── models.py                [CRIADO]
├── schemas.py               [CRIADO]
├── dependencies.py          [CRIADO]
├── router.py                [CRIADO]
├── agente1.py               [CRIADO]
├── agente2.py               [CRIADO]
├── services_download.py     [CRIADO]
├── services_relevancia.py   [CRIADO]
├── services_extracao_json.py [CRIADO]
├── services_consolidacao.py  [CRIADO]
├── services_chatbot.py       [CRIADO]
├── services_geracao_peca.py  [CRIADO]
└── templates/
    └── index.html           [CRIADO]

tests/cumprimento_beta/
├── __init__.py              [CRIADO]
├── test_acesso.py           [CRIADO]
├── test_agente1.py          [CRIADO]
├── test_agente2.py          [CRIADO]
└── test_chatbot.py          [CRIADO]

docs/sistemas/
└── cumprimento_beta.md      [CRIADO]
```

## Arquivos Modificados

- `main.py` - Adicionado import e registro do router
- `migrations/env.py` - Adicionado import dos models
- `sistemas/gerador_pecas/templates/index.html` - Adicionado botao beta
- `frontend/src/sistemas/gerador_pecas/app.ts` - Adicionado verificacao de acesso
- `.claude/CLAUDE.md` - Adicionado sistema na documentacao

---

## Proximos Passos (Manual)

1. Rodar migration para criar tabelas:
   ```bash
   alembic revision --autogenerate -m "add cumprimento beta tables"
   alembic upgrade head
   ```

2. Criar categoria "cumprimento_sentenca" em /admin/categorias-resumo-json

3. Configurar prompts em /admin/prompts-config:
   - prompt_sistema_cumprimento_beta
   - prompt_consolidacao_cumprimento_beta

4. Testar fluxo completo manualmente

---

*Implementado em: 2026-01-27*
*Total de arquivos criados: 20*
*Total de testes: 37 (todos passando)*
