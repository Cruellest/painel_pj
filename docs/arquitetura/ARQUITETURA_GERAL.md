# Arquitetura Geral do Portal PGE-MS

> Visao macro do repositorio, fluxos principais e guia de onboarding para equipes externas.

## 1. Visao Geral

O Portal PGE-MS e uma plataforma de automacao juridica que utiliza IA para auxiliar procuradores do Estado de Mato Grosso do Sul na elaboracao de pecas juridicas, analise de processos e gestao de documentos.

### Stack Tecnologico

| Camada | Tecnologia |
|--------|------------|
| Backend | Python 3.10+ / FastAPI |
| Banco de Dados | PostgreSQL 15 |
| Frontend | JavaScript/TypeScript (em migracao) |
| IA/LLM | Google Gemini (Vertex AI) |
| Integracao | TJ-MS via SOAP/MNI (proxy Fly.io) |
| Deploy | Railway (producao), Docker (local) |
| ML Local | PyTorch + Transformers (BERT) |

### Arquitetura de Alto Nivel

```
                    ┌─────────────────────────────────────────────────┐
                    │                   USUARIOS                      │
                    │              (Procuradores PGE-MS)               │
                    └───────────────────────┬─────────────────────────┘
                                            │
                                            ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (SPA)                                    │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │
│   │Gerador  │ │Pedido   │ │Prestacao│ │Relatorio│ │Matricula│ │BERT     │    │
│   │Pecas    │ │Calculo  │ │Contas   │ │Cumprim. │ │Confront.│ │Training │    │
│   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘    │
└───────────────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                              BACKEND (FastAPI)                                 │
│                                                                               │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│   │   Routers   │  │  Services   │  │   Models    │  │    Utils    │         │
│   │  (sistemas/)│  │  (core)     │  │ (SQLAlchemy)│  │  (helpers)  │         │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│          │                │                │                │                 │
│          └────────────────┴────────────────┴────────────────┘                 │
│                                    │                                          │
│   ┌────────────────────────────────┼───────────────────────────────────────┐  │
│   │                           INTEGRAÇÕES                                  │  │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐              │  │
│   │  │ TJ-MS    │  │ Gemini   │  │ Storage  │  │ OCR      │              │  │
│   │  │ (SOAP)   │  │ (LLM)    │  │ (Files)  │  │ (PDF)    │              │  │
│   │  └──────────┘  └──────────┘  └──────────┘  └──────────┘              │  │
│   └────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────┘
                                            │
                                            ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                              PERSISTENCIA                                      │
│   ┌──────────────────────────────────────────────────────────────────────┐    │
│   │                          PostgreSQL                                   │    │
│   │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐             │    │
│   │  │ users  │ │geracoes│ │prompts │ │configs │ │ logs   │             │    │
│   │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘             │    │
│   └──────────────────────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────────────────────┘
```

## 2. Estrutura de Diretorios

```
portal-pge/
├── main.py                    # Entry point FastAPI
├── config.py                  # Configuracoes globais
├── CLAUDE.md                  # Regras operacionais para IA
│
├── admin/                     # Modulo de administracao
│   ├── router.py              # Endpoints admin
│   ├── models_prompts.py      # Modelos de prompts
│   └── templates/             # UI admin
│
├── auth/                      # Autenticacao e autorizacao
│   ├── router.py              # Endpoints auth
│   ├── models.py              # User, Role
│   └── dependencies.py        # FastAPI dependencies
│
├── database/                  # Conexao e migrations
│   ├── connection.py          # Engine SQLAlchemy
│   └── init_db.py             # Inicializacao e migrations
│
├── services/                  # Servicos compartilhados
│   ├── tjms_client.py         # Cliente SOAP TJ-MS
│   ├── gemini_service.py      # Cliente Google Gemini
│   └── storage.py             # Armazenamento de arquivos
│
├── sistemas/                  # Modulos de negocio
│   ├── gerador_pecas/         # Sistema principal
│   ├── pedido_calculo/
│   ├── prestacao_contas/
│   ├── relatorio_cumprimento/
│   ├── matriculas_confrontantes/
│   ├── assistencia_judiciaria/
│   ├── bert_training/
│   └── classificador_documentos/
│
├── utils/                     # Utilitarios
│   ├── timezone.py            # Funcoes de timezone
│   └── validators.py          # Validadores
│
├── frontend/                  # Assets frontend
│   ├── static/                # JS/CSS
│   └── src/                   # TypeScript (migracao)
│
├── docs/                      # Documentacao
│   ├── sistemas/              # Docs por sistema
│   └── decisions/             # ADRs
│
└── tests/                     # Testes automatizados
```

## 3. Fluxos Principais

### 3.1 Fluxo do Gerador de Pecas (Principal)

```
[Usuario] CNJ + Tipo de Peca
           │
           ▼
    ┌──────────────┐
    │   AGENTE 1   │  Coletor
    │              │
    │  • Consulta TJ-MS
    │  • Filtra documentos
    │  • Baixa PDFs
    │  • Extrai texto
    │  • Gera resumo JSON
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │   AGENTE 2   │  Detector
    │              │
    │  • Analisa resumo
    │  • Avalia regras deterministicas
    │  • Ativa modulos relevantes
    │  • Monta prompts
    └──────┬───────┘
           │
           ▼
    ┌──────────────┐
    │   AGENTE 3   │  Gerador
    │              │
    │  • Recebe prompts
    │  • Chama Gemini Pro
    │  • Streaming de resposta
    │  • Gera peca em Markdown
    └──────┬───────┘
           │
           ▼
    [Peca Juridica]
```

### 3.2 Fluxo de Integracao TJ-MS

```
[Portal PGE]
      │
      │ HTTPS
      ▼
┌─────────────────┐
│   Proxy Fly.io  │  (tjms-proxy.fly.dev)
│                 │
│  • SSL offload
│  • Timeout 120s
│  • Retry logic
└────────┬────────┘
         │
         │ SOAP/MNI
         ▼
┌─────────────────┐
│     TJ-MS       │
│                 │
│  • consultarProcesso
│  • consultarDocumento
│  • consultarMovimentos
└─────────────────┘
```

### 3.3 Fluxo de Classificacao com IA

```
[PDF Upload]
      │
      ▼
┌─────────────────┐
│  Extrator de    │
│  Conteudo       │
│                 │
│  • PyMuPDF texto
│  • Se ilegivel → imagem
│  • Limite de tokens
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Gemini Flash   │
│                 │
│  • Categorias do banco
│  • Threshold de confianca
│  • Fallback residual
└────────┬────────┘
         │
         ▼
[Categoria + Confianca]
```

## 4. Dependencias Entre Modulos

```
                        ┌─────────────────────┐
                        │   gerador_pecas     │
                        │   (principal)       │
                        └──────────┬──────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
              ▼                    ▼                    ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │ classificador   │  │  tjms_client    │  │ gemini_service  │
    │ _documentos     │  │  (services/)    │  │ (services/)     │
    └─────────────────┘  └─────────────────┘  └─────────────────┘
                                   │
                                   ▼
                         ┌─────────────────┐
                         │ Usados por      │
                         │ TODOS os outros │
                         │ sistemas        │
                         └─────────────────┘

    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
    │pedido_calc. │  │prestacao_c. │  │relat_cumpr. │  │matriculas   │
    └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

## 5. Decisoes Arquiteturais

### 5.1 FastAPI como Framework

- **Motivo**: Async nativo, OpenAPI automatico, Pydantic
- **ADR**: `docs/decisions/ADR-0001-fastapi-framework.md`

### 5.2 Proxy TJ-MS no Fly.io

- **Motivo**: Railway nao permite conexoes SOAP diretas, timeout de 60s
- **Solucao**: Proxy dedicado no Fly.io com timeout de 120s

### 5.3 Agentes em Pipeline (3 agentes)

- **Motivo**: Separacao de responsabilidades, reuso entre sistemas
- **Beneficio**: Cada agente pode evoluir independentemente

### 5.4 Regras Deterministicas + LLM

- **Motivo**: Performance (fast path) e custo (evita chamadas desnecessarias)
- **Implementacao**: AST JSON avaliado antes de chamar LLM

### 5.5 Worker Local para BERT Training

- **Motivo**: GPU nao disponivel na nuvem (Railway), custo
- **Arquitetura**: Cloud gerencia fila, worker local faz treinamento

## 6. Variaveis de Ambiente Principais

| Variavel | Descricao | Obrigatoria |
|----------|-----------|-------------|
| `DATABASE_URL` | URL PostgreSQL | Sim |
| `SECRET_KEY` | Chave JWT | Sim |
| `GEMINI_KEY` | API Key Google AI | Sim |
| `TJ_WS_USER` | Usuario MNI TJ-MS | Sim |
| `TJ_WS_PASS` | Senha MNI TJ-MS | Sim |
| `TJMS_PROXY_URL` | URL do proxy SOAP | Sim |
| `ENVIRONMENT` | development/production | Nao |
| `LOG_LEVEL` | DEBUG/INFO/WARNING | Nao |

## 7. Onboarding para Novas Equipes

### 7.1 Pre-requisitos

- Python 3.10+
- PostgreSQL 15+
- Git
- Node.js 18+ (para frontend)

### 7.2 Setup Local

```bash
# 1. Clone
git clone <repo>
cd portal-pge

# 2. Ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# 3. Dependencias
pip install -r requirements.txt

# 4. Variaveis de ambiente
cp .env.example .env
# Editar .env com credenciais

# 5. Banco de dados
python -c "from database.init_db import init_db; init_db()"

# 6. Executar
uvicorn main:app --reload

# 7. Acessar
# http://localhost:8000
# http://localhost:8000/docs (OpenAPI)
```

### 7.3 Onde Comecar

1. **Entender o dominio**: Ler `docs/GLOSSARIO_CONCEITOS.md`
2. **Arquitetura**: Este documento + `docs/ARCHITECTURE.md`
3. **Sistema principal**: `docs/sistemas/gerador_pecas.md`
4. **API**: `http://localhost:8000/docs`
5. **Testes**: `docs/TESTING.md`

### 7.4 Padrao de Desenvolvimento

- **Branches**: `feature/`, `fix/`, `refactor/`
- **Commits**: Convencionais (`feat:`, `fix:`, `docs:`)
- **PRs**: Requerem review + testes passando
- **Deploy**: Automatico via Railway (main → producao)

## 8. Mapa de Documentacao

| Documento | Conteudo |
|-----------|----------|
| `CLAUDE.md` | Regras operacionais para IA |
| `docs/README.md` | Indice central |
| `docs/ARQUITETURA_GERAL.md` | Este documento |
| `docs/sistemas/*.md` | Documentacao por sistema |
| `docs/PLANO_MELHORIAS_BACKEND.md` | Roadmap de melhorias |
| `docs/CHECKLIST_RELEASE_EQUIPE.md` | Checklist para releases |
| `docs/ARCHITECTURE.md` | Detalhes tecnicos |
| `docs/API.md` | Referencia de API |
| `docs/DATABASE.md` | Modelo de dados |
| `docs/TESTING.md` | Guia de testes |
| `docs/OPERATIONS.md` | Operacao em producao |
| `docs/LOCAL-DEV.md` | Desenvolvimento local |
