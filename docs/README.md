# Documentacao do Portal PGE-MS

> Indice central da documentacao tecnica do Portal PGE-MS.

## Inicio Rapido

1. **Novo no projeto?** Comece pelo [CLAUDE.md](../CLAUDE.md) (regras operacionais)
2. **Entender a arquitetura?** Leia [ARQUITETURA_GERAL.md](ARQUITETURA_GERAL.md)
3. **Trabalhar em um sistema?** Acesse [docs/sistemas/](sistemas/)
4. **Fazer deploy?** Siga o [CHECKLIST_RELEASE_EQUIPE.md](CHECKLIST_RELEASE_EQUIPE.md)

## Mapa de Documentacao

### Documentacao Principal

| Documento | Descricao |
|-----------|-----------|
| [../CLAUDE.md](../CLAUDE.md) | **LEIA PRIMEIRO** - Regras operacionais para trabalhar no repo |
| [ARQUITETURA_GERAL.md](ARQUITETURA_GERAL.md) | Visao macro, fluxos principais, onboarding |
| [PLANO_MELHORIAS_BACKEND.md](PLANO_MELHORIAS_BACKEND.md) | Roadmap de melhorias e dividas tecnicas |
| [CHECKLIST_RELEASE_EQUIPE.md](CHECKLIST_RELEASE_EQUIPE.md) | Checklist para dev, teste e deploy |

### Documentacao por Sistema

| Sistema | Descricao | Link |
|---------|-----------|------|
| Gerador de Pecas | Sistema principal - geracao de pecas juridicas | [sistemas/gerador_pecas.md](sistemas/gerador_pecas.md) |
| Pedido de Calculo | Geracao de pedidos de calculo | [sistemas/pedido_calculo.md](sistemas/pedido_calculo.md) |
| Prestacao de Contas | Analise de prestacao de contas | [sistemas/prestacao_contas.md](sistemas/prestacao_contas.md) |
| Relatorio de Cumprimento | Relatorios de cumprimento de sentenca | [sistemas/relatorio_cumprimento.md](sistemas/relatorio_cumprimento.md) |
| Matriculas Confrontantes | Analise de matriculas imobiliarias | [sistemas/matriculas_confrontantes.md](sistemas/matriculas_confrontantes.md) |
| Assistencia Judiciaria | Consulta e relatorio de processos | [sistemas/assistencia_judiciaria.md](sistemas/assistencia_judiciaria.md) |
| BERT Training | Treinamento de classificadores | [sistemas/bert_training.md](sistemas/bert_training.md) |
| Classificador de Documentos | Classificacao de PDFs com IA | [sistemas/classificador_documentos.md](sistemas/classificador_documentos.md) |

### Documentacao Tecnica

| Documento | Descricao |
|-----------|-----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Detalhes tecnicos de arquitetura |
| [API.md](API.md) | Referencia de API REST |
| [DATABASE.md](DATABASE.md) | Modelo de dados e tabelas |
| [MODULES.md](MODULES.md) | Estrutura de modulos Python |

### Documentacao de Operacao

| Documento | Descricao |
|-----------|-----------|
| [OPERATIONS.md](OPERATIONS.md) | Guia de operacao em producao |
| [LOCAL-DEV.md](LOCAL-DEV.md) | Setup de ambiente local |
| [TESTING.md](TESTING.md) | Guia de testes |

### Documentacao de Dominio

| Documento | Descricao |
|-----------|-----------|
| [GLOSSARIO_CONCEITOS.md](GLOSSARIO_CONCEITOS.md) | Glossario de termos juridicos e tecnicos |
| [agents.md](agents.md) | Documentacao dos agentes TJ-MS |
| [banco_vetorial.md](banco_vetorial.md) | Documentacao de embeddings e busca vetorial |

### Documentacao Especifica

| Documento | Descricao |
|-----------|-----------|
| [EXTRACTION_DETERMINISTIC.md](EXTRACTION_DETERMINISTIC.md) | Sistema de regras deterministicas |
| [DOCUMENT_CLASSIFIER.md](DOCUMENT_CLASSIFIER.md) | Detalhes do classificador de documentos |
| [regras_tipo_peca.md](regras_tipo_peca.md) | Regras por tipo de peca juridica |
| [prompts_conteudo_vetorial.md](prompts_conteudo_vetorial.md) | Documentacao de prompts modulares |
| [bert_training.md](bert_training.md) | Detalhes tecnicos do BERT Training |

### ADRs (Architecture Decision Records)

| ADR | Decisao |
|-----|---------|
| [decisions/ADR-0001-fastapi-framework.md](decisions/ADR-0001-fastapi-framework.md) | Escolha do FastAPI |
| [decisions/ADR-0001-template.md](decisions/ADR-0001-template.md) | Template para novos ADRs |

### Propostas e Planejamento

| Documento | Descricao |
|-----------|-----------|
| [BERT_SISTEMA_PRODUTO_REDESIGN.md](BERT_SISTEMA_PRODUTO_REDESIGN.md) | Proposta de redesign do BERT Training |

### Changelog e Historico

| Documento | Descricao |
|-----------|-----------|
| [DOCS_CHANGES.md](DOCS_CHANGES.md) | Historico de alteracoes na documentacao |

### Arquivados

Documentos com valor historico mas nao mais ativos estao em [_archive/](_archive/).

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

## Mapa de Pastas

```
portal-pge/
|-- CLAUDE.md             # Regras operacionais (LEIA PRIMEIRO)
|-- main.py               # Entry point FastAPI
|-- config.py             # Configuracoes globais
|-- admin/                # Admin de prompts e configuracoes
|-- auth/                 # Autenticacao JWT
|-- database/             # Conexao SQLAlchemy
|-- docs/                 # Esta documentacao
|   |-- sistemas/         # Docs por sistema
|   |-- decisions/        # ADRs
|-- services/             # Clientes compartilhados (Gemini, TJ-MS)
|-- sistemas/             # Modulos de negocio (8 sistemas)
|-- tests/                # Testes automatizados
|-- frontend/             # Assets frontend
```

## Como Contribuir com Documentacao

1. **Novo sistema?** Criar `docs/sistemas/<nome>.md` seguindo o padrao existente
2. **Decisao arquitetural?** Criar ADR em `docs/decisions/`
3. **Atualizacao de sistema?** Atualizar o `.md` correspondente
4. **Mudanca significativa?** Registrar em `DOCS_CHANGES.md`
