# Arquitetura

Documentacao de arquitetura tecnica e decisoes arquiteturais.

## Conteudo

| Documento | Descricao |
|-----------|-----------|
| [ARQUITETURA_GERAL.md](ARQUITETURA_GERAL.md) | Visao macro do sistema, fluxos principais |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Detalhes tecnicos de implementacao |
| [MODULES.md](MODULES.md) | Estrutura de modulos Python |

## ADRs (Architecture Decision Records)

Decisoes arquiteturais documentadas em `decisions/`:

| ADR | Decisao |
|-----|---------|
| [ADR-0001-fastapi-framework.md](decisions/ADR-0001-fastapi-framework.md) | Escolha do FastAPI |
| [ADR-0001-template.md](decisions/ADR-0001-template.md) | Template para novos ADRs |

### Criando novo ADR

1. Copie `decisions/ADR-0001-template.md`
2. Renomeie para `ADR-XXXX-titulo.md`
3. Preencha os campos
4. Atualize este README
