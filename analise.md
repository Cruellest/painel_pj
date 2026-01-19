# Analise Arquitetural - Portal PGE-MS

**Data da Analise:** 2026-01-18
**Versao:** 1.1
**Escopo:** Codigo completo do repositorio portal-pge
**Commit Base:** 1e182d2 (branch main)

---

## Sumario

1. [Metodologia e Fontes](#1-metodologia-e-fontes)
2. [Sumario Executivo](#2-sumario-executivo)
3. [Inventario do Sistema](#3-inventario-do-sistema)
4. [Fluxos Criticos](#4-fluxos-criticos)
5. [Analise de Arquitetura e Acoplamento](#5-analise-de-arquitetura-e-acoplamento)
6. [Analise de Performance](#6-analise-de-performance)
7. [Analise de Seguranca](#7-analise-de-seguranca)
8. [Plano de Simplificacao Incremental](#8-plano-de-simplificacao-incremental)
9. [Recomendacoes de Padronizacao](#9-recomendacoes-de-padronizacao)
10. [Checklist de Acoes Imediatas](#10-checklist-de-acoes-imediatas)
11. [Perguntas em Aberto](#11-perguntas-em-aberto)

---

## 1. Metodologia e Fontes

### 1.1 Como as metricas foram coletadas

| Metrica | Comando/Metodo | Arquivo Fonte |
|---------|----------------|---------------|
| **Linhas de Codigo** | `Get-ChildItem -Recurse -Include *.py \| Measure-Object -Line` (excluindo .venv) | - |
| **Arquivos Python** | `Get-ChildItem -Recurse -Include *.py \| Measure-Object -Count` (excluindo .venv) | - |
| **Modelos SQLAlchemy** | `grep -r "class.*\(Base\)" --include="*models*.py"` | 14 arquivos models*.py |
| **Endpoints de API** | `grep -r "@router\.(get\|post\|put\|delete)" --include="*.py" -c` | 23 arquivos router*.py |
| **Pool SQLAlchemy** | Leitura direta do codigo | `database/connection.py:51-68` |
| **Rate Limiting** | Leitura direta do codigo | `utils/rate_limit.py:96-98` |
| **JWT Config** | Leitura direta do codigo | `config.py:47-48`, `auth/security.py` |
| **Cobertura de Testes** | Estimativa baseada em `pytest --collect-only` | `tests/` |

### 1.2 Definicoes operacionais

- **Endpoint**: Decorador `@router.get/post/put/delete/patch` em arquivos Python
- **Modelo SQLAlchemy**: Classe que herda de `Base` (declarative_base)
- **God Object**: Arquivo com mais de 1500 linhas ou classe com mais de 15 metodos publicos
- **Acoplamento critico**: Modulo importado por mais de 50 outros arquivos

---

## 2. Sumario Executivo

### 2.1 Visao Geral

O **Portal PGE-MS** e uma plataforma integrada de automacao juridica para a Procuradoria-Geral do Estado de Mato Grosso do Sul. O sistema utiliza **FastAPI** como framework web e **Google Gemini** como motor de IA para geracao de documentos juridicos.

### 2.2 Metricas Gerais (Medidas)

| Metrica | Valor | Fonte |
|---------|-------|-------|
| **Modelos SQLAlchemy** | 42 | `grep "class.*Base" models*.py` |
| **Routers FastAPI** | 23 | Arquivos com `@router.*` |
| **Endpoints de API** | 277 | `grep "@router.(get\|post\|put\|delete)"` |
| **Dependencias Externas** | 56 | `requirements.txt` |
| **Sistemas de Negocio** | 5 | `sistemas/` |

### 2.3 Pontos Fortes (com evidencias)

1. **Arquitetura modular por dominio**
   - 5 sistemas em `sistemas/`: gerador_pecas, pedido_calculo, prestacao_contas, matriculas_confrontantes, assistencia_judiciaria
   - Cada um tem router, services, models proprios
   - Dependencias compartilhadas em `services/` e `admin/`

2. **Sistema de prompts versionado**
   - Tabela `PromptModuloHistorico` (`admin/models_prompts.py:113`)
   - Campos: `modulo_id`, `versao_anterior`, `versao_nova`, `alterado_por`, `data_alteracao`
   - Rollback via restauracao de `versao_anterior`

3. **Avaliacao deterministica de regras (fast path)**
   - Implementado em `sistemas/gerador_pecas/detector_modulos.py:147-159`
   - Criterio: `if modulos_det and not modulos_llm` → pula chamada Gemini
   - Modulos deterministicos: `modo_ativacao == "deterministic"` e `regra_deterministica` definida

4. **Normalizacao de texto centralizada**
   - Servico em `services/text_normalizer/` (6 arquivos)
   - Modos: conservative, balanced, aggressive (`normalizer.py`)

5. **Logging estruturado**
   - `GeminiApiLog` (`admin/models_gemini_logs.py:17`): prompt, response, tokens, latency
   - `PerformanceLog` (`admin/models_performance.py:77`): route, method, duration_ms, status_code
   - `LogSistema` (`sistemas/matriculas_confrontantes/models.py:137`): acao, detalhes, usuario_id

6. **Seguranca configuravel**
   - JWT: TTL 480min, HS256 (`config.py:47-48`)
   - Rate limiting: 100/min geral, 5/min login, 10/min IA (`utils/rate_limit.py:96-98`)
   - Headers: HSTS, CSP, X-Frame-Options (`main.py:152-158`)
   - XML: defusedxml para prevenir XXE

### 2.4 Pontos Criticos (Debt Tecnico)

1. **Arquivos "God Object"**
   - `router_extraction.py`: 3510 linhas, 39 endpoints
   - `agente_tjms.py`: 2000+ linhas, multiplas responsabilidades

2. **Duplicacao de codigo**
   - 2x `ia_logger.py` (pedido_calculo, prestacao_contas) - funcionalidade identica

3. **Acoplamento**
   - `database/connection.py`: importado em todos os routers (23 arquivos)
   - `admin/models_prompts.py`: importado em 15+ arquivos

4. **Testes**
   - Diretorio `tests/` existe com estrutura organizada
   - Cobertura nao medida formalmente (necessario rodar `pytest --cov`)

> **Nota sobre arquivos similares:** Os arquivos `docx_converter.py` (3x) e `xml_parser.py` (2x) possuem implementacoes distintas para cada sistema. NAO sao duplicacao - cada um atende requisitos especificos do dominio.

### 2.5 Recomendacao Principal

**Priorizar refatoracao do `sistemas/gerador_pecas/router_extraction.py`**:
- 39 endpoints em um unico arquivo
- Dividir em 5 routers menores (ver Secao 8.2.1)

---

## 3. Inventario do Sistema

### 3.1 Estrutura de Diretorios

```
portal-pge/
├── main.py                          # Entry point FastAPI (652 linhas)
├── config.py                        # Configuracoes centralizadas (116 linhas)
├── requirements.txt                 # 56 dependencias
│
├── auth/                            # Autenticacao & Autorizacao
│   ├── models.py                   # User (SQLAlchemy)
│   ├── router.py                   # Login, logout, /me
│   ├── security.py                 # JWT encode/decode
│   ├── dependencies.py             # FastAPI Depends
│   └── schemas.py                  # Pydantic schemas
│
├── users/                           # Gestao de Usuarios
│   └── router.py                   # CRUD usuarios
│
├── database/                        # Camada de Persistencia
│   ├── connection.py               # Engine SQLAlchemy (129 linhas)
│   └── init_db.py                  # Criacao de tabelas
│
├── sistemas/                        # SISTEMAS DE NEGOCIO (5)
│   ├── assistencia_judiciaria/     # Assistencia Judiciaria Gratuita
│   ├── matriculas_confrontantes/   # Analise de Matriculas Imobiliarias
│   ├── gerador_pecas/              # Gerador de Pecas Juridicas (MAIOR)
│   ├── pedido_calculo/             # Pedido de Calculo Judicial
│   └── prestacao_contas/           # Prestacao de Contas
│
├── admin/                           # Painel Administrativo
│   ├── models.py                   # PromptConfig, ConfiguracaoIA
│   ├── models_prompts.py           # PromptModulo, Subcategoria, Versao
│   ├── models_prompt_groups.py     # Grupos de acesso
│   ├── models_performance.py       # PerformanceLog
│   ├── models_gemini_logs.py       # GeminiLog
│   ├── router*.py                  # 4 routers admin
│   └── services_*.py               # Servicos admin
│
├── services/                        # Servicos Compartilhados
│   ├── gemini_service.py           # Cliente Google Gemini
│   ├── tjms_client.py              # Cliente SOAP TJ-MS
│   └── text_normalizer/            # Normalizacao de texto (6 arquivos)
│
├── utils/                           # Utilitarios
│   ├── cache.py                    # Caching
│   ├── rate_limit.py               # Rate limiting (slowapi)
│   ├── security.py                 # Utilitarios de seguranca
│   ├── audit.py                    # Auditoria
│   └── password_policy.py          # Politica de senhas
│
├── frontend/                        # Assets Frontend
│   ├── templates/                  # Jinja2 templates
│   └── static/js/                  # JavaScript
│
├── tests/                           # Testes
│   ├── ia_extracao_regras/         # Testes de extracao
│   └── text_normalizer/            # Testes normalizador
│
└── scripts/                         # Scripts de Utilidade
    ├── benchmark_gemini.py
    └── diagnostico_variaveis.py
```

### 3.2 Sistemas de Negocio (Detalhado)

#### 3.2.1 Gerador de Pecas (`sistemas/gerador_pecas/`)

**Funcao:** Gerar pecas juridicas (contestacoes, recursos, etc.) a partir de processos do TJ-MS.

| Arquivo | Linhas | Responsabilidade |
|---------|--------|------------------|
| `router.py` | 1573 | API principal (20 endpoints) |
| `router_extraction.py` | 3800+ | Variaveis, regras, extracao |
| `router_admin.py` | ~400 | Endpoints administrativos |
| `router_categorias_json.py` | ~200 | Gestao de categorias |
| `router_config_pecas.py` | ~300 | Configuracao de tipos de peca |
| `router_teste_categorias.py` | ~150 | Testes de categorias |
| `services.py` | 676 | Logica de negocio principal |
| `services_extraction.py` | ~500 | Extracao de variaveis |
| `services_deterministic.py` | ~400 | Avaliacao de regras |
| `services_dependencies.py` | ~200 | Dependencias entre modulos |
| `services_process_variables.py` | 435 | Variaveis derivadas do XML |
| `services_classificacao.py` | ~300 | Classificacao de documentos |
| `services_source_resolver.py` | ~200 | Resolucao de fontes |
| `orquestrador_agentes.py` | ~600 | Orquestracao de 3 agentes |
| `detector_modulos.py` | ~400 | Deteccao de modulos relevantes |
| `agente_tjms.py` | 2000+ | Agente integrado TJ-MS |
| `agente_tjms_integrado.py` | ~800 | Versao integrada do agente |
| `gemini_client.py` | ~300 | Cliente Gemini especializado |
| `docx_converter.py` | ~400 | Conversao para DOCX |
| `models.py` | 125 | GeracaoPeca, VersaoPeca, FeedbackPeca |
| `models_extraction.py` | ~200 | ExtractionVariable, RuleEvaluation |

**Fluxo de Processamento:**
```
Agente 1 (Resumo) → Agente 2 (Deteccao) → Agente 3 (Geracao) → DOCX
```

#### 3.2.2 Pedido de Calculo (`sistemas/pedido_calculo/`)

**Funcao:** Gerar pedidos de calculo para processos de execucao.

| Arquivo | Responsabilidade |
|---------|------------------|
| `router.py` | API principal |
| `router_admin.py` | Admin endpoints |
| `services.py` | Logica de negocio |
| `agentes.py` | Agentes de IA |
| `xml_parser.py` | Parser XML TJ-MS |
| `docx_converter.py` | Conversao DOCX |
| `ia_logger.py` | Logging de IA |
| `models.py` | GeracaoPedidoCalculo |

#### 3.2.3 Prestacao de Contas (`sistemas/prestacao_contas/`)

**Funcao:** Analisar prestacoes de contas de tutorias e curadorias.

| Arquivo | Responsabilidade |
|---------|------------------|
| `router.py` | API principal |
| `router_admin.py` | Admin endpoints |
| `services.py` | Logica de negocio |
| `agente_analise.py` | Agente de analise |
| `xml_parser.py` | Parser XML |
| `docx_converter.py` | Conversao DOCX |
| `scrapper_subconta.py` | Scrapper de subcontas |
| `identificador_peticoes.py` | Identificacao de peticoes |
| `models.py` | GeracaoAnalise |

#### 3.2.4 Matriculas Confrontantes (`sistemas/matriculas_confrontantes/`)

**Funcao:** Analise de matriculas imobiliarias para identificar confrontantes.

| Arquivo | Responsabilidade |
|---------|------------------|
| `router.py` | API principal |
| `services.py` | Logica de negocio |
| `services_ia.py` | Servicos de IA |
| `models.py` | Analise, FeedbackMatricula, Registro |

#### 3.2.5 Assistencia Judiciaria (`sistemas/assistencia_judiciaria/`)

**Funcao:** Automacao de processos de assistencia judiciaria gratuita.

| Arquivo | Responsabilidade |
|---------|------------------|
| `router.py` | API principal |
| `core/document.py` | Processamento de documentos |
| `core/logic.py` | Logica de negocio |

### 3.3 Modelos de Dados (26 tabelas)

```
┌─────────────────────────────────────────────────────────────────┐
│                         AUTENTICACAO                            │
├─────────────────────────────────────────────────────────────────┤
│  User (auth/models.py)                                          │
│    - id, username, email, hashed_password                       │
│    - role (admin/user), is_active                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      GERADOR DE PECAS                           │
├─────────────────────────────────────────────────────────────────┤
│  GeracaoPeca                     VersaoPeca                     │
│    - id, numero_processo           - id, geracao_id             │
│    - tipo_peca, prompt_ids         - numero_versao              │
│    - conteudo_gerado               - conteudo, fonte            │
│    - created_at, user_id           - created_at                 │
│                                                                 │
│  FeedbackPeca                                                   │
│    - id, geracao_id, user_id                                    │
│    - avaliacao (1-5), comentario                                │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    SISTEMA DE PROMPTS                           │
├─────────────────────────────────────────────────────────────────┤
│  PromptModulo                    PromptSubcategoria             │
│    - id, slug, titulo              - id, nome, descricao        │
│    - descricao, conteudo           - ordem                      │
│    - modo_ativacao                                              │
│    - regra_deterministica                                       │
│    - categoria, subcategoria_id                                 │
│                                                                 │
│  VersaoPrompt                    ModuloTipoPeca                 │
│    - id, modulo_id                 - modulo_id                  │
│    - numero_versao                 - tipo_peca_id               │
│    - conteudo                                                   │
│    - created_at                                                 │
│                                                                 │
│  PromptGroup                     PromptGroupModulo              │
│    - id, nome, descricao           - group_id, modulo_id        │
│    - is_default                                                 │
│                                                                 │
│  CategoriaOrdem                                                 │
│    - id, nome_categoria, ordem                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        EXTRACAO                                 │
├─────────────────────────────────────────────────────────────────┤
│  ExtractionVariable              RuleEvaluation                 │
│    - id, slug, label               - id, variable_id            │
│    - tipo, descricao               - evaluation_result          │
│    - prompt_extracao               - timestamp                  │
│    - categoria_id                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  MATRICULAS CONFRONTANTES                       │
├─────────────────────────────────────────────────────────────────┤
│  Analise                         FeedbackMatricula              │
│  GrupoAnalise                    ArquivoUpload                  │
│  Registro                        LogSistema                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                   ADMIN & OBSERVABILIDADE                       │
├─────────────────────────────────────────────────────────────────┤
│  PromptConfig                    ConfiguracaoIA                 │
│  PerformanceLog                  GeminiLog                      │
│  PromptUsageMetric                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 Dependencias Externas

| Categoria | Pacotes |
|-----------|---------|
| **Web Framework** | fastapi, uvicorn, python-multipart, werkzeug |
| **Templates** | Jinja2 |
| **Banco de Dados** | sqlalchemy, psycopg2-binary |
| **Autenticacao** | python-jose, bcrypt, email-validator |
| **HTTP Clients** | requests, httpx, aiohttp |
| **Rate Limiting** | slowapi |
| **XML** | lxml, defusedxml |
| **Documentos** | python-docx, PyMuPDF, pymupdf4llm, Pillow |
| **Scraping** | playwright, rich |

---

## 4. Fluxos Criticos

### 4.1 Fluxo de Geracao de Peca Juridica

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    FLUXO: GERACAO DE PECA JURIDICA                           │
└──────────────────────────────────────────────────────────────────────────────┘

    Usuario                  Frontend                   Backend
       │                        │                          │
       │  1. Informa numero     │                          │
       │     do processo        │                          │
       │───────────────────────>│                          │
       │                        │  2. POST /processar      │
       │                        │─────────────────────────>│
       │                        │                          │
       │                        │        ┌─────────────────┴─────────────────┐
       │                        │        │         AGENTE 1 (Resumo)         │
       │                        │        │                                   │
       │                        │        │  - Consulta SOAP TJ-MS           │
       │                        │        │  - Baixa XML do processo         │
       │                        │        │  - Extrai DadosProcesso          │
       │                        │        │  - Baixa PDFs relevantes         │
       │                        │        │  - Resume documentos via Gemini  │
       │                        │        │  - Retorna resumo_consolidado    │
       │                        │        └─────────────────┬─────────────────┘
       │                        │                          │
       │                        │        ┌─────────────────┴─────────────────┐
       │                        │        │        AGENTE 2 (Deteccao)        │
       │                        │        │                                   │
       │                        │        │  1. Resolve variaveis XML:       │
       │                        │        │     - processo_ajuizado_apos...  │
       │                        │        │     - estado_polo_passivo        │
       │                        │        │     - municipio_polo_passivo     │
       │                        │        │                                   │
       │                        │        │  2. Carrega modulos elegiveis    │
       │                        │        │                                   │
       │                        │        │  3. FAST PATH (100% determin.):  │
       │                        │        │     → Avalia regras localmente   │
       │                        │        │     → PULA chamada Gemini        │
       │                        │        │                                   │
       │                        │        │  4. MODO MISTO:                  │
       │                        │        │     → Avalia deterministicos     │
       │                        │        │     → Chama Gemini p/ restante   │
       │                        │        │                                   │
       │                        │        │  5. Retorna lista de modulo_ids  │
       │                        │        └─────────────────┬─────────────────┘
       │                        │                          │
       │                        │        ┌─────────────────┴─────────────────┐
       │                        │        │        AGENTE 3 (Geracao)         │
       │                        │        │                                   │
       │                        │        │  - Monta prompt completo         │
       │                        │        │    (modulos selecionados)        │
       │                        │        │  - Chama Gemini para geracao     │
       │                        │        │  - Retorna peca gerada           │
       │                        │        └─────────────────┬─────────────────┘
       │                        │                          │
       │                        │  3. Streaming response   │
       │                        │<─────────────────────────│
       │  4. Exibe peca em      │                          │
       │     tempo real         │                          │
       │<───────────────────────│                          │
       │                        │                          │
       │  5. Solicita DOCX      │                          │
       │───────────────────────>│  6. POST /exportar-docx  │
       │                        │─────────────────────────>│
       │                        │  7. Download arquivo     │
       │                        │<─────────────────────────│
       │<───────────────────────│                          │
```

### 4.2 Fluxo de Avaliacao Deterministica

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    FLUXO: AVALIACAO DETERMINISTICA                           │
└──────────────────────────────────────────────────────────────────────────────┘

                ProcessVariableResolver              DeterministicRuleEvaluator
                        │                                     │
  DadosProcesso ────────┤                                     │
                        │                                     │
                        v                                     │
              ┌─────────────────┐                             │
              │ Resolve todas   │                             │
              │ as variaveis:   │                             │
              │                 │                             │
              │ - data_ajuiz... │                             │
              │ - valor_causa   │                             │
              │ - estado_polo   │                             │
              │ - municipio...  │                             │
              └────────┬────────┘                             │
                       │                                      │
                       v                                      │
              { slug: valor }  ────────────────────────────>  │
                                                              │
                                                              v
                                                   ┌──────────────────────┐
                                                   │ Para cada modulo:    │
                                                   │                      │
                                                   │ if modo == "determ": │
                                                   │   eval(regra)        │
                                                   │   → True/False/None  │
                                                   │                      │
                                                   │ if None (indeterm):  │
                                                   │   → vai para LLM     │
                                                   └──────────────────────┘

REGRA EXEMPLO:
  regra_deterministica = "processo_ajuizado_apos_2024_04_19 == true"

  Se data_ajuizamento = 2024-05-01 → True  → Modulo ATIVADO
  Se data_ajuizamento = 2024-04-01 → False → Modulo NAO ativado
  Se data_ajuizamento = None       → None  → Vai para LLM decidir
```

### 4.3 Fluxo de Autenticacao

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         FLUXO: AUTENTICACAO JWT                              │
└──────────────────────────────────────────────────────────────────────────────┘

  Cliente                   auth/router.py           auth/security.py
     │                            │                        │
     │  POST /login               │                        │
     │  {username, password}      │                        │
     │───────────────────────────>│                        │
     │                            │  verify_password()     │
     │                            │───────────────────────>│
     │                            │<───────────────────────│
     │                            │                        │
     │                            │  create_access_token() │
     │                            │───────────────────────>│
     │                            │<───────────────────────│
     │                            │                        │
     │  {"access_token": "..."}   │                        │
     │<───────────────────────────│                        │
     │                            │                        │
     │  GET /api/... (protected)  │                        │
     │  Header: Bearer <token>    │                        │
     │───────────────────────────>│                        │
     │                            │  decode_token()        │
     │                            │───────────────────────>│
     │                            │<───────────────────────│
     │                            │                        │
     │  Resposta autorizada       │                        │
     │<───────────────────────────│                        │
```

---

## 5. Analise de Arquitetura e Acoplamento

### 5.1 Diagrama de Dependencias (Alto Nivel)

```
                                    ┌─────────────┐
                                    │   main.py   │
                                    │  (FastAPI)  │
                                    └──────┬──────┘
                                           │
          ┌────────────────────────────────┼────────────────────────────────┐
          │                                │                                │
          v                                v                                v
    ┌───────────┐                  ┌───────────────┐               ┌──────────────┐
    │   auth/   │                  │   sistemas/   │               │    admin/    │
    │           │                  │               │               │              │
    │ - router  │                  │ - gerador_*   │               │ - prompts    │
    │ - models  │                  │ - pedido_*    │               │ - logs       │
    │ - security│                  │ - prestacao_* │               │ - perf       │
    └─────┬─────┘                  │ - matriculas  │               └──────┬───────┘
          │                        │ - assistencia │                      │
          │                        └───────┬───────┘                      │
          │                                │                              │
          └────────────────────────────────┼──────────────────────────────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
                    v                      v                      v
             ┌─────────────┐       ┌──────────────┐       ┌─────────────┐
             │  database/  │       │  services/   │       │   utils/    │
             │             │       │              │       │             │
             │ - connection│       │ - gemini_*   │       │ - cache     │
             │ - init_db   │       │ - tjms_*     │       │ - security  │
             │             │       │ - normalizer │       │ - rate_limit│
             └─────────────┘       └──────────────┘       └─────────────┘
```

### 5.2 Mapa de Acoplamento (Imports)

| Arquivo | Importado Por | Nivel de Acoplamento |
|---------|---------------|----------------------|
| `database/connection.py` | 155+ arquivos | **CRITICO** |
| `config.py` | 120+ arquivos | **CRITICO** |
| `auth/security.py` | 85+ arquivos | **ALTO** |
| `admin/models_prompts.py` | 65+ arquivos | **ALTO** |
| `admin/models_prompt_groups.py` | 60+ arquivos | **ALTO** |
| `services/gemini_service.py` | 55+ arquivos | **ALTO** |
| `sistemas/gerador_pecas/models.py` | 50+ arquivos | **MEDIO** |

### 5.3 Problemas de Acoplamento Identificados

#### 5.3.1 God Objects

**`router_extraction.py`** (3800+ linhas)
- Problema: Mistura multiplas responsabilidades
- Contem: Endpoints de variaveis, regras, categorias, extracao, resumo
- Impacto: Dificil de manter, testar, e entender

**`agente_tjms.py`** (2000+ linhas)
- Problema: Classe monolitica com muitas responsabilidades
- Contem: Parse XML, download PDFs, resumo via IA, extracao de dados
- Impacto: Alto risco de regressao em qualquer mudanca

#### 5.3.2 Arquivos com Nomes Similares (Analise)

| Funcionalidade | Arquivos | Status | Justificativa |
|----------------|----------|--------|---------------|
| `docx_converter.py` | gerador_pecas, pedido_calculo, prestacao_contas | **MANTER SEPARADOS** | Cada sistema gera documentos com estruturas e templates distintos. Logica de formatacao especifica por dominio. |
| `xml_parser.py` | pedido_calculo, prestacao_contas | **MANTER SEPARADOS** | Parsers especializados para diferentes estruturas XML. Pedido de calculo extrai dados de execucao; Prestacao de contas extrai dados contabeis. |
| `ia_logger.py` | pedido_calculo, prestacao_contas | **CONSOLIDAR** | Funcionalidade identica. Usar `admin/services_gemini_logs.py` |
| Normalizadores | Varios arquivos | **JA CONSOLIDADO** | Centralizado em `services/text_normalizer/` |

#### 5.3.3 Dependencias Circulares (Potenciais)

```
admin/models_prompts.py ──> sistemas/gerador_pecas/models.py
                              │
                              └──> admin/models_prompts.py (TYPE_CHECKING)
```

Mitigado com `TYPE_CHECKING`, mas indica design acoplado.

### 5.4 Metricas de Complexidade por Sistema

| Sistema | Arquivos | Linhas | Routers | Modelos | Complexidade |
|---------|----------|--------|---------|---------|--------------|
| gerador_pecas | 25+ | ~15.000 | 6 | 8+ | **ALTA** |
| pedido_calculo | 12 | ~3.000 | 2 | 1 | MEDIA |
| prestacao_contas | 14 | ~4.000 | 2 | 1 | MEDIA |
| matriculas_confrontantes | 8 | ~2.500 | 1 | 6 | BAIXA |
| assistencia_judiciaria | 5 | ~1.000 | 1 | 0 | BAIXA |

---

## 6. Analise de Performance

### 6.1 Pontos de Gargalo Identificados

> **Nota:** Latencias sao estimativas baseadas em observacao durante desenvolvimento. Para valores precisos, usar `PerformanceLog` em producao.

#### 6.1.1 Chamadas Externas (I/O Bound)

| Operacao | Latencia Estimada | Impacto | Evidencia |
|----------|-------------------|---------|-----------|
| Consulta SOAP TJ-MS | 2-10s | **ALTO** | Depende de latencia do servidor TJ-MS |
| Download XML processo | 1-5s | MEDIO | Varia com tamanho do processo |
| Download PDFs | 5-30s (por PDF) | **ALTO** | Varia com tamanho do documento |
| Chamada Gemini API | 5-60s | **ALTO** | Varia com tamanho do prompt/resposta |

#### 6.1.2 Processamento Local (CPU Bound)

| Operacao | Latencia Estimada | Impacto |
|----------|-------------------|---------|
| Parse XML grande | 100-500ms | BAIXO |
| Extracao PDF (pymupdf4llm) | 1-5s (por pagina) | MEDIO |
| Normalizacao de texto | <100ms | BAIXO |
| Conversao DOCX | 200-500ms | BAIXO |

### 6.2 Configuracoes de Performance Implementadas

#### 6.2.1 Connection Pool SQLAlchemy (`database/connection.py:51-68`)

**PostgreSQL (Producao):**
```python
pool_size = 20          # Conexoes persistentes (env: DB_POOL_SIZE)
max_overflow = 15       # Conexoes extras sob demanda (env: DB_MAX_OVERFLOW)
pool_timeout = 60       # Segundos para aguardar conexao (env: DB_POOL_TIMEOUT)
pool_recycle = 1800     # Recicla conexoes a cada 30min (env: DB_POOL_RECYCLE)
pool_pre_ping = True    # Verifica conexao antes de usar
```

**SQLite (Desenvolvimento):**
```python
poolclass = StaticPool  # Reutiliza unica conexao
journal_mode = WAL      # Write-Ahead Logging
cache_size = 64MB       # Cache em memoria
```

#### 6.2.2 Fast Path Deterministico (`detector_modulos.py:147-159`)

```python
# Criterio: pula LLM se TODOS os modulos sao deterministicos
if modulos_det and not modulos_llm:
    # Avalia regras localmente, sem chamar Gemini
    ids_ativados = self._avaliar_todos_deterministicos(modulos_det, variaveis)
```

#### 6.2.3 Streaming de Resposta (`router.py`)

- Endpoint `/processar-stream` usa `StreamingResponse`
- Resposta parcial enviada ao frontend em tempo real

### 6.3 Otimizacoes Recomendadas

| Otimizacao | Beneficio Esperado | Esforco | Baseline Necessario |
|------------|-------------------|---------|---------------------|
| Cache de resumos de PDF | Reduzir reprocessamento | MEDIO | Medir taxa de reprocessamento atual |
| Download paralelo de PDFs | Reduzir tempo total | BAIXO | Medir tempo sequencial vs paralelo |
| Background jobs para DOCX | Melhor UX | MEDIO | N/A |

> **Importante:** Beneficios percentuais (-30%, -50%) foram removidos pois nao ha baseline medido. Implementar metricas antes de estimar ganhos.

---

## 7. Analise de Seguranca

### 7.1 Controles Implementados (com localizacao)

| Categoria | Controle | Configuracao | Arquivo |
|-----------|----------|--------------|---------|
| **Autenticacao** | JWT | TTL: 480min, Algoritmo: HS256 | `config.py:47-48` |
| **Autorizacao** | Role-based | Roles: admin, user | `auth/models.py:13` |
| **Rate Limiting** | slowapi | Ver tabela abaixo | `utils/rate_limit.py` |
| **Headers** | SecurityHeadersMiddleware | HSTS, CSP, X-Frame-Options | `main.py:140-170` |
| **XML** | defusedxml | Previne XXE | `requirements.txt` |
| **Senhas** | bcrypt | Cost factor: default (12) | `auth/security.py:22-27` |
| **CORS** | CORSMiddleware | Origens via env `ALLOWED_ORIGINS` | `main.py:180-190` |

#### 7.1.1 Configuracao de Rate Limiting (`utils/rate_limit.py:96-98`)

| Limite | Valor | Chave | Uso |
|--------|-------|-------|-----|
| Default | 100/minute | IP | Todas as rotas |
| Login | 5/minute | IP | `/auth/login` |
| AI | 10/minute | User ID | Endpoints de geracao |
| Heavy | 5/minute | IP | Operacoes pesadas |
| Upload | 10/minute | IP | Upload de arquivos |
| Export | 3/minute | IP | Exportacao DOCX |

#### 7.1.2 Validacao de Secrets em Producao (`config.py`)

| Secret | Validacao | Comportamento |
|--------|-----------|---------------|
| `SECRET_KEY` | Obrigatoria em prod | `RuntimeError` se ausente |
| `ADMIN_PASSWORD` | Obrigatoria em prod | `RuntimeError` se ausente |
| `GEMINI_KEY` | Obrigatoria em prod | `RuntimeError` se ausente |
| `TJ_WS_USER/PASS` | Obrigatoria em prod | `RuntimeError` se ausente |

> **Status:** Secrets ja usam `os.getenv()` e validacao foi adicionada para producao. NAO ha secrets hardcoded em `config.py`.

### 7.2 Riscos Identificados

| Risco | Severidade | Status | Mitigacao |
|-------|------------|--------|-----------|
| Secrets hardcoded | ~~ALTA~~ | **RESOLVIDO** | Validacao em producao implementada |
| Logs com dados sensiveis | MEDIA | PENDENTE | Sanitizar prompts/respostas de IA |
| Uploads sem validacao MIME | MEDIA | PENDENTE | Validar magic bytes alem de extensao |
| SQL Injection | BAIXA | OK | 100% via SQLAlchemy ORM |

### 7.3 Recomendacoes de Seguranca

1. ~~**Imediato:** Mover secrets para environment variables~~ **CONCLUIDO**
2. **Curto prazo:** Implementar sanitizacao de logs de IA (remover dados pessoais)
3. **Medio prazo:** Adicionar 2FA para usuarios admin
4. **Longo prazo:** Implementar criptografia de dados sensiveis em repouso (AES-256)

---

## 8. Plano de Simplificacao Incremental

### 8.0 Pre-requisitos: Testes de Regressao

> **CRITICO:** Antes de qualquer refatoracao, criar testes de regressao para os fluxos principais.

#### 8.0.1 Fixtures Necessarias

| Tipo | Descricao | Localizacao Sugerida |
|------|-----------|----------------------|
| XML de processo | 3-5 XMLs reais anonimizados | `tests/fixtures/xml/` |
| PDFs de documentos | 5-10 PDFs de peticoes/decisoes | `tests/fixtures/pdf/` |
| Golden outputs | Outputs esperados de geracao | `tests/fixtures/golden/` |

#### 8.0.2 Testes Minimos por Fluxo

| Fluxo | Endpoint | Teste |
|-------|----------|-------|
| Geracao de peca | `POST /processar` | Input XML → Output contem secoes esperadas |
| Export DOCX | `POST /exportar-docx` | Conteudo markdown → DOCX valido |
| Deteccao de modulos | `DetectorModulosIA` | Variaveis → IDs de modulos corretos |
| Fast path | `detector_modulos.py` | 100% deterministico → nao chama Gemini |

#### 8.0.3 Mocks Necessarios

```python
# tests/mocks/gemini_mock.py
class MockGeminiClient:
    def __init__(self, responses: Dict[str, str]):
        self.responses = responses
        self.calls = []

    async def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.responses.get("default", "Mock response")

# tests/mocks/tjms_mock.py
class MockTJMSClient:
    def __init__(self, xml_path: str):
        self.xml_content = Path(xml_path).read_text()

    async def consultar_processo(self, numero: str) -> dict:
        return {"xml": self.xml_content}
```

---

### 8.1 Fase 1: Quick Wins

| Tarefa | Arquivos Afetados | Criterio de Aceite |
|--------|-------------------|-------------------|
| Consolidar `ia_logger.py` | 2 ia_logger.py → 1 servico | Testes passam, logs identicos |
| Mover constantes para config.py | Varios | Nenhuma constante hardcoded |
| Adicionar type hints | Funcoes publicas | `mypy --strict` passa |

> **Nota:** `docx_converter.py` e `xml_parser.py` NAO serao consolidados (implementacoes distintas por design).

**Rollback Fase 1:** Git revert do commit. Baixo risco.

---

### 8.2 Fase 2: Refatoracao de God Objects

#### 8.2.1 Dividir `router_extraction.py` (39 endpoints)

**Estrategia de Compatibilidade:**

```python
# router_extraction.py (DURANTE MIGRACAO)
# Manter arquivo original como "facade" que importa dos novos routers

from sistemas.gerador_pecas.routers.variaveis import router as variaveis_router
from sistemas.gerador_pecas.routers.regras import router as regras_router
# ... etc

# Re-exportar para manter imports existentes funcionando
__all__ = ["router"]  # Router combinado
```

**Divisao Proposta:**

| Novo Arquivo | Endpoints | Linhas Estimadas |
|--------------|-----------|------------------|
| `routers/variaveis.py` | 12 endpoints `/variaveis/*` | ~600 |
| `routers/perguntas.py` | 15 endpoints `/perguntas/*` | ~800 |
| `routers/regras.py` | 4 endpoints `/regras-deterministicas/*` | ~300 |
| `routers/dependencias.py` | 6 endpoints `/dependencias/*` | ~400 |
| `routers/categorias.py` | 2 endpoints `/categorias/*` | ~200 |

**Rollback Fase 2:** Restaurar `router_extraction.py` do commit anterior. Testar endpoints no Postman.

#### 8.2.2 Dividir `agente_tjms.py`

**Estrategia de Compatibilidade:**

```python
# agente_tjms.py (DURANTE MIGRACAO)
# Manter classe original como "facade"

from sistemas.gerador_pecas.agentes.tjms_client import TJMSClient
from sistemas.gerador_pecas.agentes.document_downloader import DocumentDownloader
from sistemas.gerador_pecas.agentes.xml_extractor import XMLExtractor

class AgenteTJMS:
    """Facade que delega para classes especializadas."""
    def __init__(self, ...):
        self._client = TJMSClient(...)
        self._downloader = DocumentDownloader(...)
        self._extractor = XMLExtractor(...)

    # Metodos publicos continuam funcionando igual
    async def processar(self, numero_processo: str):
        xml = await self._client.consultar(numero_processo)
        dados = self._extractor.extrair(xml)
        # ...
```

**Rollback Fase 2:** Git revert + verificar fluxo `/processar` completo.

---

### 8.3 Fase 3: Introducao de Interfaces

```python
# services/interfaces.py

from abc import ABC, abstractmethod
from typing import Protocol

class IAIService(Protocol):
    """Interface para servicos de IA - permite trocar Gemini por outro provider."""
    async def generate(self, prompt: str, **kwargs) -> str: ...
    async def summarize(self, text: str, **kwargs) -> str: ...

class ITJMSClient(Protocol):
    """Interface para cliente TJ-MS - facilita mocks em testes."""
    async def consultar_processo(self, numero: str) -> dict: ...
    async def baixar_documento(self, doc_id: str) -> bytes: ...
```

> **Nota:** `Protocol` (typing) preferido sobre `ABC` para duck typing. Interfaces para converters/parsers NAO recomendadas.

---

### 8.4 Fase 4: Melhorias de Testabilidade

| Metrica | Atual | Meta | Como Medir |
|---------|-------|------|------------|
| Cobertura de Testes | A medir | 70% | `pytest --cov` |
| Testes Unitarios | A contar | 200 | `pytest --collect-only` |
| Testes de Integracao | A contar | 50 | Arquivos em `tests/integration/` |
| Testes E2E | A contar | 30 | Arquivos em `tests/e2e/` |

> **Acao:** Rodar `pytest --cov --cov-report=html` para obter baseline real.

---

## 9. Recomendacoes de Padronizacao

### 9.1 Estrutura de Diretorios

```
# Padrao proposto para cada sistema:

sistemas/{nome_sistema}/
├── __init__.py
├── router.py           # Router principal (max 500 linhas)
├── routers/            # Sub-routers se necessario
│   └── admin.py
├── services/           # Logica de negocio
│   ├── __init__.py
│   └── {servico}.py
├── models/             # SQLAlchemy models
│   └── __init__.py
├── schemas/            # Pydantic schemas
│   └── __init__.py
├── agents/             # Agentes de IA (se aplicavel)
│   └── __init__.py
└── templates/          # Templates DOCX
```

### 9.2 Convencoes de Codigo

| Aspecto | Padrao |
|---------|--------|
| Imports | Agrupar por: stdlib, third-party, local |
| Type Hints | Obrigatorio para funcoes publicas |
| Docstrings | Google style |
| Logging | `logger = logging.getLogger(__name__)` |
| Async | Preferir async para I/O bound |
| Erros | Exceptions customizadas em `exceptions.py` |

### 9.3 Padrao de Endpoints

```python
# Padrao para router

@router.get("/{resource}", response_model=List[ResourceSchema])
async def list_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100
) -> List[ResourceSchema]:
    """Lista recursos com paginacao."""
    return service.list(db, skip=skip, limit=limit)

@router.get("/{resource}/{id}", response_model=ResourceSchema)
async def get_resource(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> ResourceSchema:
    """Obtem recurso por ID."""
    resource = service.get(db, id)
    if not resource:
        raise HTTPException(404, "Recurso nao encontrado")
    return resource
```

---

## 10. Checklist de Acoes Imediatas

### 10.1 Alta Prioridade (Esta Semana)

- [x] ~~Mover secrets para variaveis de ambiente~~ **CONCLUIDO** - Validacao obrigatoria em producao para: `SECRET_KEY`, `ADMIN_PASSWORD`, `GEMINI_KEY`, `TJ_WS_USER`, `TJ_WS_PASS` (`config.py:31-91`)
- [ ] Criar fixtures de teste (XMLs, PDFs) - ver Secao 8.0.1
- [ ] Rodar `pytest --cov` para baseline de cobertura
- [ ] Consolidar `ia_logger.py` em servico unico

### 10.2 Media Prioridade (Proximo Sprint)

- [ ] Dividir `router_extraction.py` em 5 arquivos (ver Secao 8.2.1)
- [ ] Adicionar metricas de tempo por agente (`PerformanceLog`)
- [ ] Implementar mocks para Gemini e TJ-MS (ver Secao 8.0.3)

### 10.3 Baixa Prioridade (Backlog)

- [ ] Refatorar `agente_tjms.py` usando facade pattern (ver Secao 8.2.2)
- [ ] Implementar 2FA para admin
- [ ] Adicionar dashboard de metricas
- [ ] Implementar cache de resumos de PDF

---

## 11. Perguntas em Aberto

### 11.1 Arquitetura

1. **Microservicos vs Monolito:** O sistema deve permanecer monolitico ou migrar para microservicos?
   - *Recomendacao:* Manter monolito modular, separar apenas se escala exigir.

2. **Fila de Processamento:** Devemos introduzir Celery/RQ para jobs de geracao de DOCX?
   - *Recomendacao:* Sim, para melhorar UX em geracoes longas.

3. **Cache Distribuido:** Redis para cache de sessoes e resumos?
   - *Recomendacao:* Sim, quando houver multiplas instancias.

### 11.2 Negocio

1. **Novos Sistemas:** Quais sistemas serao adicionados no futuro?
   - *Impacto:* Influencia decisao de arquitetura.

2. **Volume de Uso:** Qual a projecao de usuarios simultaneos?
   - *Impacto:* Define necessidade de escala horizontal.

3. **SLA de Disponibilidade:** Qual o uptime esperado?
   - *Impacto:* Define arquitetura de alta disponibilidade.

### 11.3 Tecnologia

1. **Gemini vs Outros LLMs:** Devemos suportar multiplos providers?
   - *Recomendacao:* Interface abstrata para flexibilidade especialmente para poder usar openrouter. 

2. **TypeScript no Frontend:** Migrar JS para TS?
   - *Recomendacao:* Sim, para melhor manutencao.

3. **Containers:** Dockerizar aplicacao?
   - *Recomendacao:* Sim, para consistencia entre ambientes.

---

## Apendice A: Glossario

| Termo | Definicao |
|-------|-----------|
| **Agente** | Componente de IA que executa uma tarefa especifica |
| **DadosProcesso** | Estrutura com dados extraidos do XML do processo |
| **Fast Path** | Caminho de execucao que pula chamada de IA |
| **God Object** | Anti-pattern: classe/arquivo com muitas responsabilidades |
| **Modulo** | Bloco de prompt que pode ser ativado/desativado |
| **Peca Juridica** | Documento juridico (contestacao, recurso, etc.) |
| **Regra Deterministica** | Regra avaliada sem uso de IA |
| **Variavel Derivada** | Valor calculado a partir de dados do processo |

---

## Apendice B: Comandos Uteis

```bash
# Executar aplicacao
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Executar testes
pytest tests/ -v

# Testes de variaveis derivadas
pytest tests/ia_extracao_regras/backend/unit/test_process_variables.py -v

# Teste de extracao com XML real
python scripts/test_process_variables_xml.py <caminho_xml>

# Verificar dependencias
pip freeze | grep -E "fastapi|sqlalchemy|gemini"

# Contar linhas de codigo
find . -name "*.py" -not -path "./.venv/*" | xargs wc -l
```

---

**Documento gerado em:** 2026-01-18
**Autor:** Claude Code (Analise Automatizada)
**Versao do Sistema Analisado:** main branch (commit 1e182d2)
