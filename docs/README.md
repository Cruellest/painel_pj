# Documentacao - Portal PGE-MS

Esta pasta concentra a documentacao tecnica do Portal PGE-MS. O objetivo e dar
visao confiavel do que existe no codigo, sem adivinhar comportamento.

## Indice

- [Visao geral e quickstart](README.md)
- [Arquitetura](ARCHITECTURE.md)
- [Modulos e pastas](MODULES.md)
- [API](API.md)
- [Banco de dados](DATABASE.md)
- [Testes](TESTING.md)
- [Operacoes e deploy](OPERATIONS.md)
- [Glossario de conceitos](GLOSSARIO_CONCEITOS.md)
- [Extracao deterministica](EXTRACTION_DETERMINISTIC.md)
- [Decisoes arquiteturais](decisions/)
- [Runbook legado](../RUNBOOK.md)
- [Arquitetura legado](../ARCHITECTURE.md)

## Visao geral

O Portal PGE-MS e um monolito FastAPI que hospeda varios sistemas juridicos
(gerador de pecas, pedido de calculo, prestacao de contas, matriculas
confrontantes e assistencia judiciaria). A autenticacao e centralizada
(JWT via cookie e header), e os modulos compartilham banco SQLAlchemy
(SQLite em dev e PostgreSQL em prod) e integracoes com IA.

## Mapa de pastas (alto nivel)

```
portal-pge/
|-- admin/                # Admin de prompts e configuracoes de IA
|-- auth/                 # Autenticacao JWT, dependencias e seguranca
|-- database/             # Conexao SQLAlchemy e migrations manuais
|-- docs/                 # Esta documentacao + decisoes
|-- frontend/             # Templates Jinja2 do portal e admin
|-- services/             # Clientes compartilhados (Gemini, TJ-MS)
|-- sistemas/             # Modulos de negocio
|-- tests/                # Testes unitarios/integracao/e2e
|-- users/                # CRUD de usuarios (admin)
|-- utils/                # Rate limit, audit, cache, seguranca
|-- main.py               # App FastAPI e roteamento
|-- config.py             # Configuracoes e variaveis de ambiente
|-- requirements.txt      # Dependencias Python
```

## Quickstart (rodar local)

1) Criar ambiente e instalar dependencias

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

2) Configurar ambiente

```bash
copy .env.example .env
# Edite .env com suas credenciais
```

3) Subir o servidor

```bash
python main.py
# ou
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

4) URLs principais

- Portal: http://localhost:8000
- Dashboard: http://localhost:8000/dashboard
- Docs OpenAPI: http://localhost:8000/docs

Atalho Windows: `run.bat`

## Comandos principais

- Dev server: `uvicorn main:app --reload --host 127.0.0.1 --port 8000`
- Testes (unittest): `python -m unittest`
- Testes especificos: `python -m unittest tests.test_prompt_groups`
- Migracoes manuais: `python run_migration.py`

## Onde mexer (tarefas comuns)

- Novo endpoint de API: `main.py` (include_router) + `sistemas/<modulo>/router.py`
- Prompts e configuracoes de IA: `admin/` + tabelas `prompt_configs` e `configuracoes_ia`
- Prompts modulares (gerador de pecas): `admin/router_prompts.py` e `admin/models_prompts.py`
- Extracao de dados e regras deterministicas: `sistemas/gerador_pecas/router_extraction.py`
- Banco de dados: models em `*/models.py` + migrations em `database/init_db.py`
- Frontend SPA de cada sistema: `sistemas/<modulo>/templates/`
- Templates admin/portal: `frontend/templates/`

Se algum comportamento nao estiver claro no codigo, isso e sinalizado nas paginas
especificas desta documentacao.
