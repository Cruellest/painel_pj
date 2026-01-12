# ARCHITECTURE.md - Arquitetura do Sistema

## Visao Geral

O Portal PGE-MS e uma plataforma de automacao juridica que integra 5 sistemas especializados com inteligencia artificial para auxiliar procuradores do Estado de Mato Grosso do Sul.

```
                                    +------------------+
                                    |    Frontend      |
                                    |  (Vanilla JS +   |
                                    |    Jinja2)       |
                                    +--------+---------+
                                             |
                                             v
+------------------------------------------+-------------------------------------------+
|                                    FastAPI Application                               |
|                                                                                      |
|  +-------------+  +-------------+  +-------------+  +-------------+  +-------------+ |
|  |  Gerador    |  |   Pedido    |  | Prestacao   |  | Matriculas  |  |Assistencia  | |
|  |   Pecas     |  |   Calculo   |  |   Contas    |  |Confrontantes|  | Judiciaria  | |
|  +------+------+  +------+------+  +------+------+  +------+------+  +------+------+ |
|         |                |                |                |                |        |
|         +----------------+----------------+----------------+----------------+        |
|                                           |                                          |
|                              +------------+------------+                             |
|                              |                         |                             |
|                         +----+----+              +-----+-----+                       |
|                         |  Auth   |              |   Admin   |                       |
|                         | (JWT)   |              | (Prompts) |                       |
|                         +---------+              +-----------+                       |
+------------------------------------------+-------------------------------------------+
                                           |
                     +---------------------+---------------------+
                     |                     |                     |
              +------+------+       +------+------+       +------+------+
              |   SQLite    |       |  Google     |       |   TJ-MS    |
              | PostgreSQL  |       |   Gemini    |       |   SOAP     |
              +-------------+       +-------------+       +-------------+
```

---

## Stack Tecnologico

### Backend
- **Framework:** FastAPI 0.110+
- **Server:** Uvicorn (ASGI)
- **ORM:** SQLAlchemy 2.0+
- **Auth:** python-jose (JWT) + bcrypt

### Frontend
- **Templates:** Jinja2
- **JS:** Vanilla JavaScript (ES6+)
- **CSS:** TailwindCSS
- **Estilo:** SPAs por sistema

### Banco de Dados
- **Dev:** SQLite com WAL mode
- **Prod:** PostgreSQL 14+

### Integracoes
- **IA:** Google Gemini API
- **Juridico:** TJ-MS SOAP/MNI

---

## Estrutura de Diretorios

```
portal-pge/
├── main.py                    # Entry point FastAPI
├── config.py                  # Configuracoes centralizadas
├── database/
│   ├── connection.py          # Engine e session factory
│   └── init_db.py             # Migrations e seeds
├── auth/
│   ├── models.py              # User model
│   ├── router.py              # Endpoints de auth
│   ├── security.py            # JWT + bcrypt
│   └── dependencies.py        # FastAPI dependencies
├── admin/
│   ├── models.py              # Configs e prompts
│   ├── router.py              # CRUD de configs
│   └── router_prompts.py      # CRUD de prompts
├── services/
│   └── gemini_service.py      # Wrapper do Gemini
├── utils/
│   ├── security.py            # Funcoes de seguranca
│   └── cache.py               # TTL Cache
├── sistemas/
│   ├── gerador_pecas/         # Sistema 1
│   ├── pedido_calculo/        # Sistema 2
│   ├── prestacao_contas/      # Sistema 3
│   ├── matriculas_confrontantes/  # Sistema 4
│   └── assistencia_judiciaria/    # Sistema 5
└── frontend/
    └── templates/             # Templates Jinja2
```

---

## Sistemas

### 1. Gerador de Pecas Juridicas

**Funcao:** Gera documentos juridicos (peticoes, manifestacoes) usando IA.

**Arquitetura:** 3-Agentes em Pipeline
```
[Agente 1: Coletor] -> [Agente 2: Detector] -> [Agente 3: Gerador]
     TJ-MS SOAP         Classifica tipo         Gera documento
```

**Endpoints:**
- `POST /gerador-pecas/api/gerar` - Gera nova peca
- `GET /gerador-pecas/api/historico` - Lista geracoes
- `POST /gerador-pecas/api/chat` - Refinamento conversacional

### 2. Pedido de Calculo

**Funcao:** Processa pedidos de calculo judicial.

**Fluxo:**
1. Recebe numero CNJ
2. Busca dados via TJ-MS SOAP
3. Extrai documentos relevantes (sentencas, acordaos)
4. Gera pedido de calculo com IA

### 3. Prestacao de Contas

**Funcao:** Analisa prestacoes de contas em processos.

**Diferenciais:**
- Scraping via Playwright para extrair subcontas
- Analise de multiplos anexos
- Geracao de parecer automatico

### 4. Matriculas Confrontantes

**Funcao:** Analisa matriculas imobiliarias com visao computacional.

**Tecnologias:**
- PDF para imagens (PyMuPDF)
- Analise com Gemini Vision
- Comparacao de areas e confrontantes

### 5. Assistencia Judiciaria

**Funcao:** Consulta e analisa processos de assistencia judiciaria.

**Integracao TJ-MS:**
- SOAP via proxy (evitar CORS)
- Parsing XML completo
- Cache de consultas

---

## Modelos de Dados

### Core

```python
User
├── id: int (PK)
├── username: str (unique)
├── email: str
├── password_hash: str
├── role: str (admin|user)
├── sistemas_permitidos: JSON
├── is_active: bool
└── must_change_password: bool

PromptConfig
├── id: int (PK)
├── sistema: str
├── tipo: str
├── conteudo: text
└── ativo: bool

ConfiguracaoIA
├── id: int (PK)
├── sistema: str
├── chave: str
├── valor: str
└── descricao: str
```

### Por Sistema

Cada sistema tem modelos especificos:
- `GeracaoPeca`, `FeedbackPeca` (Gerador)
- `GeracaoPedidoCalculo`, `LogChamadaIA` (Pedido Calculo)
- `GeracaoAnalise` (Prestacao Contas)
- `Analise`, `Registro`, `FeedbackMatricula` (Matriculas)
- `ConsultaProcesso`, `FeedbackAnalise` (Assistencia)

---

## Fluxo de Autenticacao

```
1. Usuario submete credentials em /auth/login
2. Backend valida com bcrypt
3. Gera JWT com claims: {sub: username, user_id, exp}
4. Frontend armazena token em localStorage
5. Requisicoes incluem header: Authorization: Bearer <token>
6. Backend valida token via Depends(get_current_active_user)
```

---

## Integracao com IA

### Google Gemini

```python
# services/gemini_service.py
GeminiService
├── call_gemini_async()      # Chamada async com retry
├── call_gemini_with_images() # Vision API
└── _build_headers()         # Auth headers
```

**Modelos usados:**
- `gemini-3-flash-preview` - Rapido, uso geral
- `gemini-2.5-flash` - Custo otimizado

### Prompts Modulares

```
PROMPT_FINAL = BASE + PECA + CONTEUDO[1] + CONTEUDO[2] + ...
```

- **BASE:** Instrucoes gerais do sistema
- **PECA:** Template especifico do tipo de documento
- **CONTEUDO[n]:** Modulos dinamicos (formatacao, citacoes, etc)

---

## Cache

### Estrategia

```python
# utils/cache.py
config_cache    # TTL: 5 min  - Configuracoes do banco
prompt_cache    # TTL: 15 min - Prompts (raramente mudam)
query_cache     # TTL: 1 min  - Resultados frequentes
```

### Invalidacao

- Automatica por TTL
- Manual via `cache.invalidate()` apos updates
- Por prefixo para invalidar sistema inteiro

---

## Banco de Dados

### Connection Pool (PostgreSQL)

```python
pool_size=20        # Conexoes mantidas
max_overflow=15     # Conexoes extras sob demanda
pool_timeout=60     # Timeout para obter conexao
pool_recycle=1800   # Recicla apos 30 min
pool_pre_ping=True  # Valida antes de usar
```

### SQLite (Dev)

```sql
PRAGMA journal_mode=WAL;     -- Write-Ahead Logging
PRAGMA synchronous=NORMAL;   -- Balance durability/speed
PRAGMA cache_size=-64000;    -- 64MB cache
PRAGMA temp_store=MEMORY;    -- Temp tables em RAM
```

---

## Deploy

### Railway (Producao)

```toml
# railway.toml
[build]
builder = "nixpacks"

[deploy]
healthcheckPath = "/health"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 5
```

### Variaveis de Ambiente

```bash
# Obrigatorias
DATABASE_URL=postgresql://...
SECRET_KEY=<hex-64-chars>
ADMIN_PASSWORD=<strong-password>
GEMINI_KEY=<api-key>

# Opcionais
ALLOWED_ORIGINS=https://...
DB_POOL_SIZE=20
```

---

## Monitoramento

### Health Check

```python
GET /health
{
    "status": "ok",
    "service": "portal-pge",
    "has_openrouter_key": true,
    "has_database_url": true
}
```

### Logs

- **uvicorn.access:** Requisicoes HTTP
- **sistemas.*:** Logs por sistema
- **database:** Queries lentas (quando echo=True)

---

## Decisoes Arquiteturais

Ver `/docs/decisions/` para ADRs completos.

| ADR | Titulo | Status |
|-----|--------|--------|
| ADR-001 | FastAPI como framework | Aceito |
| ADR-002 | SQLAlchemy 2.0 ORM | Aceito |
| ADR-003 | Gemini como provider de IA | Aceito |
| ADR-004 | Prompts modulares | Aceito |
