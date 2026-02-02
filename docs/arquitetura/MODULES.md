# Modulos e Pastas

Este arquivo descreve cada pasta/sistema do repositorio, com foco em
responsabilidades reais do codigo. Onde algo nao for claro, fica marcado.

## main.py

- Proposito: entry point da app FastAPI, middleware de seguranca e roteamento.
- Entradas/Saidas: HTTP (JSON, SSE, arquivos); entrega SPAs e templates Jinja2.
- Responsabilidades: lifecycle, CORS, headers, rate limiting, handlers globais.
- Principais arquivos: `main.py`.
- Dependencias internas: `auth`, `admin`, `users`, `sistemas/*`, `database`.
- Configuracoes importantes: `ALLOWED_ORIGINS`, `IS_PRODUCTION`.
- Como testar esse modulo: iniciar app e validar `/health` e `/docs`.

## config.py

- Proposito: centralizar configuracoes e leitura de variaveis de ambiente.
- Entradas/Saidas: env vars e defaults (SQLite em dev).
- Responsabilidades: secrets, modelos IA, configuracoes TJ-MS.
- Principais arquivos: `config.py`, `.env.example`.
- Dependencias internas: usado por praticamente todos os modulos.
- Configuracoes importantes: `DATABASE_URL`, `SECRET_KEY`, `GEMINI_KEY`.
- Como testar esse modulo: carregar app e verificar logs de warnings/erros.

## auth/

- Proposito: autenticacao JWT, senha, dependencias de acesso.
- Entradas/Saidas: login via form, cookie HttpOnly e header Authorization.
- Responsabilidades: criar/validar token, politicas de senha, revogacao.
- Principais arquivos: `auth/router.py`, `auth/security.py`, `auth/dependencies.py`.
- Dependencias internas: `database`, `utils/token_blacklist.py`, `utils/audit.py`.
- Configuracoes importantes: `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`.
- Como testar esse modulo: `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`.

## users/

- Proposito: CRUD de usuarios (admin only).
- Entradas/Saidas: JSON de usuarios e permissoes.
- Responsabilidades: criar/editar/ativar/inativar usuarios e grupos de prompts.
- Principais arquivos: `users/router.py`.
- Dependencias internas: `auth/models.py`, `admin/models_prompt_groups.py`.
- Configuracoes importantes: `DEFAULT_USER_PASSWORD`.
- Como testar esse modulo: `GET /users`, `POST /users` (requer admin).

## admin/

- Proposito: administracao de prompts e configuracoes de IA.
- Entradas/Saidas: JSON de prompts, configuracoes e feedbacks.
- Responsabilidades: CRUD de prompts base, configuracoes IA e feedbacks.
- Principais arquivos: `admin/router.py`, `admin/router_prompts.py`, `admin/seed_prompts.py`.
- Dependencias internas: `auth`, `database`, `utils/cache.py`.
- Configuracoes importantes: registros em `configuracoes_ia`.
- Como testar esse modulo: `GET /admin/prompts` e `GET /admin/config-ia` (admin).

## database/

- Proposito: conexao SQLAlchemy e migrations manuais.
- Entradas/Saidas: conexao DB e execucao de DDL/seed.
- Responsabilidades: criar tabelas e manter compatibilidade de schema.
- Principais arquivos: `database/connection.py`, `database/init_db.py`.
- Dependencias internas: modelos de todos os sistemas.
- Configuracoes importantes: `DATABASE_URL`, `DB_POOL_*`.
- Como testar esse modulo: iniciar app e verificar criacao das tabelas.

## services/

- Proposito: clientes compartilhados para IA e TJ-MS.
- Entradas/Saidas: chamadas HTTP externas, respostas padronizadas.
- Responsabilidades: Gemini API, proxies TJ-MS e diagnostico.
- Principais arquivos: `services/gemini_service.py`, `services/tjms_client.py`.
- Dependencias internas: usado por `sistemas/*`.
- Configuracoes importantes: `GEMINI_KEY`, `TJMS_PROXY_URL`, `TJMS_PROXY_LOCAL_URL`.
- Como testar esse modulo: chamar `diagnostico_tjms()` e `GeminiService.is_configured()`.

## utils/

- Proposito: seguranca, rate limiting, cache e auditoria.
- Entradas/Saidas: logs, tokens revogados, cache TTL.
- Responsabilidades: audit log, policy de senha, rate limit e sanitizacao.
- Principais arquivos: `utils/rate_limit.py`, `utils/audit.py`, `utils/cache.py`.
- Dependencias internas: usado por `auth` e routers.
- Configuracoes importantes: `RATE_LIMIT_*`.
- Como testar esse modulo: validar `/auth/login` com limite e `logs/audit.log`.

## frontend/

- Proposito: templates Jinja2 para login/dashboard/admin.
- Entradas/Saidas: HTML servido pelo backend.
- Responsabilidades: UI do portal e telas administrativas.
- Principais arquivos: `frontend/templates/*.html`, `frontend/static/js/security.js`.
- Dependencias internas: usado pelo `main.py`.
- Configuracoes importantes: CSP em `main.py`.
- Como testar esse modulo: abrir `/login`, `/dashboard` e `/admin/*`.

## sistemas/gerador_pecas/

- Proposito: gerar pecas juridicas com pipeline de 3 agentes.
- Entradas/Saidas: numero CNJ ou PDFs; saida em Markdown e DOCX.
- Responsabilidades: coleta TJ-MS, deteccao de modulos e geracao de peca.
- Principais arquivos:
  - `router.py` (API e SSE)
  - `orquestrador_agentes.py` (pipeline)
  - `detector_modulos.py` (ativacao de prompts)
  - `services_extraction.py` e `services_deterministic.py` (extracao e regras)
- Dependencias internas: `admin/models_prompts.py`, `services/gemini_service.py`.
- Configuracoes importantes: `ConfiguracaoIA` chaves `modelo_agente1`, `modelo_deteccao`, `modelo_geracao`, `temperatura_geracao`.
- Como testar esse modulo: `POST /gerador-pecas/api/processar` ou `processar-stream`.

## sistemas/pedido_calculo/

- Proposito: gerar pedido de calculo a partir de XML/PDFs.
- Entradas/Saidas: numero CNJ ou XML; saida em Markdown/DOCX.
- Responsabilidades: parser XML, extracao de PDFs, geracao final com IA.
- Principais arquivos:
  - `router.py`, `agentes.py`, `xml_parser.py`, `document_downloader.py`, `docx_converter.py`.
- Dependencias internas: `services/gemini_service.py`, `admin/PromptConfig`.
- Configuracoes importantes: `ConfiguracaoIA` para modelos e prompt configs.
- Como testar esse modulo: `POST /pedido-calculo/api/processar-stream`.

## sistemas/prestacao_contas/

- Proposito: analisar prestacao de contas de processos de saude.
- Entradas/Saidas: numero CNJ; saida com parecer Markdown/DOCX.
- Responsabilidades: scraping subconta, identificacao de docs e parecer IA.
- Principais arquivos:
  - `router.py`, `services.py`, `scrapper_subconta.py`, `agente_analise.py`.
- Dependencias internas: `sistemas/pedido_calculo/document_downloader.py`, `scrapper_subconta.py`, `services/gemini_service.py`.
- Configuracoes importantes: `ConfiguracaoIA` do sistema `prestacao_contas`.
- Como testar esse modulo: `POST /prestacao-contas/api/analisar-stream`.

## sistemas/matriculas_confrontantes/

- Proposito: analise visual de matriculas imobiliarias.
- Entradas/Saidas: upload de PDF/imagem; saida JSON com confronto e relatorio.
- Responsabilidades: upload, extracao visual, relatorios e feedback.
- Principais arquivos:
  - `router.py`, `services.py`, `services_ia.py`, `templates/*`.
- Dependencias internas: `OPENROUTER_API_KEY`, `FULL_REPORT_MODEL`.
- Configuracoes importantes: `UPLOAD_FOLDER`, `ALLOWED_EXTENSIONS`.
- Como testar esse modulo: `POST /matriculas/api/files/upload` e `POST /matriculas/api/analisar/{file_id}`.

## sistemas/assistencia_judiciaria/

- Proposito: consulta e relatorio de processos de assistencia judiciaria.
- Entradas/Saidas: numero CNJ; saida em relatorio textual e DOCX/PDF.
- Responsabilidades: consulta SOAP, parser XML e geracao de relatorio IA.
- Principais arquivos:
  - `router.py`, `core/logic.py`, `core/document.py`, `models.py`.
- Dependencias internas: `TJ_WSDL_URL`, `DEFAULT_MODEL`, `GEMINI_KEY`.
- Configuracoes importantes: `TJ_WS_USER`, `TJ_WS_PASS`.
- Como testar esse modulo: `POST /assistencia/api/consultar`.

## tests/

- Proposito: testes unitarios, integracao e e2e (unittest).
- Principais arquivos: `tests/test_prompt_groups.py`, `tests/test_deterministic_grouping.py`, `tests/ia_extracao_regras/*`.
- Como testar esse modulo: ver `docs/TESTING.md`.

## scripts/

- Proposito: utilitarios e diagnosticos.
- Principais arquivos: `scripts/diagnostico/*`, `scripts/prompts_producao.sql`.
- Como testar esse modulo: executar scripts manualmente em ambiente controlado.

## docs/

- Proposito: documentacao tecnica e ADRs.
- Principais arquivos: `docs/README.md`, `docs/ARCHITECTURE.md`, `docs/GLOSSARIO_CONCEITOS.md`.
- Como testar esse modulo: revisar links e consistencia.

## logo/

- Proposito: assets de marca usados pelo portal.
- Principais arquivos: `logo/logo-pge.png`.
- Como testar esse modulo: abrir `/logo/logo-pge.png` quando app estiver rodando.
