# Documentacao do Portal PGE-MS

> Indice central da documentacao tecnica do Portal PGE-MS.

## Inicio Rapido

1. **Novo no projeto?** Comece pelo [CLAUDE.md](../.claude/CLAUDE.md) (regras operacionais)
2. **Entender a arquitetura?** Leia [arquitetura/ARQUITETURA_GERAL.md](arquitetura/ARQUITETURA_GERAL.md)
3. **Trabalhar em um sistema?** Acesse [sistemas/](sistemas/)
4. **Fazer deploy?** Siga o [operacoes/CHECKLIST_RELEASE_EQUIPE.md](operacoes/CHECKLIST_RELEASE_EQUIPE.md)

---

## Estrutura da Documentacao

```
docs/
├── README.md                 # Este arquivo (indice central)
├── arquitetura/              # Arquitetura e decisoes tecnicas
├── sistemas/                 # Documentacao por sistema
├── integracoes/              # Integracoes externas (TJ-MS, etc)
├── api/                      # Documentacao de API REST
├── operacoes/                # Deploy, testes, ambiente local
├── seguranca/                # Documentacao de seguranca
├── features/                 # Features especificas
├── dominio/                  # Glossario e conceitos juridicos
├── planejamento/             # Roadmaps e planos de melhoria
├── _archive/                 # Documentos arquivados
└── _outros/                  # Documentos sem classificacao
```

---

## Arquitetura (`arquitetura/`)

Visao macro do sistema, decisoes tecnicas e estrutura de modulos.

| Documento | Descricao |
|-----------|-----------|
| [ARQUITETURA_GERAL.md](arquitetura/ARQUITETURA_GERAL.md) | **Comece aqui** - Visao macro, fluxos, onboarding |
| [ARCHITECTURE.md](arquitetura/ARCHITECTURE.md) | Detalhes tecnicos de arquitetura |
| [MODULES.md](arquitetura/MODULES.md) | Estrutura de modulos Python |
| [decisions/](arquitetura/decisions/) | ADRs (Architecture Decision Records) |

### ADRs (Decisoes Arquiteturais)

| ADR | Decisao |
|-----|---------|
| [ADR-0001-fastapi-framework.md](arquitetura/decisions/ADR-0001-fastapi-framework.md) | Escolha do FastAPI |
| [ADR-0001-template.md](arquitetura/decisions/ADR-0001-template.md) | Template para novos ADRs |

---

## Sistemas (`sistemas/`)

Documentacao detalhada de cada sistema do portal.

| Sistema | Descricao |
|---------|-----------|
| [gerador_pecas.md](sistemas/gerador_pecas.md) | Sistema principal - geracao de pecas juridicas |
| [pedido_calculo.md](sistemas/pedido_calculo.md) | Geracao de pedidos de calculo |
| [prestacao_contas.md](sistemas/prestacao_contas.md) | Analise de prestacao de contas |
| [relatorio_cumprimento.md](sistemas/relatorio_cumprimento.md) | Relatorios de cumprimento de sentenca |
| [matriculas_confrontantes.md](sistemas/matriculas_confrontantes.md) | Analise de matriculas imobiliarias |
| [assistencia_judiciaria.md](sistemas/assistencia_judiciaria.md) | Consulta e relatorio de processos |
| [bert_training.md](sistemas/bert_training.md) | Treinamento de classificadores |
| [classificador_documentos.md](sistemas/classificador_documentos.md) | Classificacao de PDFs com IA |

---

## Integracoes Externas (`integracoes/`)

Documentacao de integracoes com sistemas externos.

| Documento | Descricao |
|-----------|-----------|
| [PLANO_UNIFICACAO_TJMS.md](integracoes/PLANO_UNIFICACAO_TJMS.md) | **TJ-MS Unificado** - Servico centralizado (services/tjms/) |
| [banco_vetorial.md](integracoes/banco_vetorial.md) | Embeddings e busca vetorial |

> **IMPORTANTE**: Ao alterar `services/tjms/`, atualize `/admin/tjms-docs` e notifique frontend.

---

## API (`api/`)

Documentacao da API REST.

| Documento | Descricao |
|-----------|-----------|
| [API.md](api/API.md) | Referencia completa de endpoints |

---

## Operacoes (`operacoes/`)

Guias de deploy, testes e ambiente de desenvolvimento.

| Documento | Descricao |
|-----------|-----------|
| [CHECKLIST_RELEASE_EQUIPE.md](operacoes/CHECKLIST_RELEASE_EQUIPE.md) | Checklist para dev, teste e deploy |
| [LOCAL-DEV.md](operacoes/LOCAL-DEV.md) | Setup de ambiente local |
| [OPERATIONS.md](operacoes/OPERATIONS.md) | Guia de operacao em producao |
| [TESTING.md](operacoes/TESTING.md) | Guia de testes |
| [ROTACAO_SECRETS.md](operacoes/ROTACAO_SECRETS.md) | Procedimento de rotacao de secrets |

---

## Seguranca (`seguranca/`)

Documentacao de seguranca e boas praticas.

| Documento | Descricao |
|-----------|-----------|
| [PREVENCAO_XSS.md](seguranca/PREVENCAO_XSS.md) | Medidas de protecao contra XSS |

---

## Features (`features/`)

Documentacao de funcionalidades especificas.

| Documento | Descricao |
|-----------|-----------|
| [DOCUMENT_CLASSIFIER.md](features/DOCUMENT_CLASSIFIER.md) | Detalhes do classificador de documentos |
| [EXTRACTION_DETERMINISTIC.md](features/EXTRACTION_DETERMINISTIC.md) | Sistema de regras deterministicas |
| [prompts_conteudo_vetorial.md](features/prompts_conteudo_vetorial.md) | Documentacao de prompts modulares |
| [regras_tipo_peca.md](features/regras_tipo_peca.md) | Regras por tipo de peca juridica |

---

## Dominio (`dominio/`)

Glossarios e conceitos do dominio juridico.

| Documento | Descricao |
|-----------|-----------|
| [GLOSSARIO_CONCEITOS.md](dominio/GLOSSARIO_CONCEITOS.md) | Glossario de termos juridicos e tecnicos |

---

## Planejamento (`planejamento/`)

Roadmaps e planos de evolucao.

| Documento | Descricao |
|-----------|-----------|
| [PLANO_MELHORIAS_BACKEND.md](planejamento/PLANO_MELHORIAS_BACKEND.md) | Roadmap de melhorias e dividas tecnicas |

---

## Arquivados (`_archive/`)

Documentos com valor historico mas nao mais ativos.

| Documento | Motivo |
|-----------|--------|
| [REDESIGN_CLASSIFICADOR_v2.md](_archive/REDESIGN_CLASSIFICADOR_v2.md) | Proposta antiga |
| [skills_frontend_typescript.md](_archive/skills_frontend_typescript.md) | Nao implementado |

---

## Outros (`_outros/`)

Documentos sem classificacao clara ou duplicados.

| Documento | Nota |
|-----------|------|
| [bert_training.md](_outros/bert_training.md) | Duplicado - versao principal em sistemas/ |

---

## Quickstart (rodar local)

```bash
# 1. Criar ambiente e instalar dependencias
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 2. Configurar ambiente
copy .env.example .env
# Edite .env com suas credenciais

# 3. Subir o servidor
uvicorn main:app --reload --host 127.0.0.1 --port 8000

# 4. Acessar
# Portal: http://localhost:8000
# Docs OpenAPI: http://localhost:8000/docs
```

---

## Mapa de Pastas do Projeto

```
portal-pge/
├── .claude/
│   └── CLAUDE.md             # Regras operacionais (LEIA PRIMEIRO)
├── main.py                   # Entry point FastAPI
├── config.py                 # Configuracoes globais
├── admin/                    # Admin de prompts e configuracoes
├── auth/                     # Autenticacao JWT
├── database/                 # Conexao SQLAlchemy
├── docs/                     # Esta documentacao
│   ├── arquitetura/          # Arquitetura e ADRs
│   ├── sistemas/             # Docs por sistema
│   ├── integracoes/          # Integracoes externas
│   ├── api/                  # Docs de API
│   ├── operacoes/            # Deploy, testes
│   ├── features/             # Features especificas
│   ├── dominio/              # Glossario
│   └── planejamento/         # Roadmaps
├── services/                 # Clientes compartilhados
│   ├── tjms/                 # Cliente TJMS Unificado
│   └── gemini_service.py     # Cliente Gemini
├── sistemas/                 # Modulos de negocio (8 sistemas)
├── tests/                    # Testes automatizados
│   ├── e2e/                  # Testes end-to-end
│   ├── services/             # Testes de servicos
│   └── load/                 # Testes de carga (k6)
├── utils/                    # Utilitarios compartilhados
│   ├── metrics.py            # Metricas Prometheus
│   ├── alerting.py           # Sistema de alertas
│   ├── circuit_breaker.py    # Circuit breaker pattern
│   └── ...                   # Outros utilitarios
└── frontend/                 # Assets frontend
```

---

## Como Contribuir com Documentacao

1. **Novo sistema?** Criar `docs/sistemas/<nome>.md` seguindo o padrao existente
2. **Decisao arquitetural?** Criar ADR em `docs/arquitetura/decisions/`
3. **Feature especifica?** Documentar em `docs/features/`
4. **Integracao externa?** Documentar em `docs/integracoes/`
5. **Mudanca significativa?** Atualizar este README
