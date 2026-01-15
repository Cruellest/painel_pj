# AGENTS.md - Guia para Agentes de IA

> Ultima atualizacao: 15 Janeiro 2026

---

## REGRA DE OURO: MANTENHA ESTE DOCUMENTO ATUALIZADO

**OBRIGATÓRIO:** Sempre que você (agente de IA) realizar alterações significativas no codebase, **ATUALIZE ESTE ARQUIVO** imediatamente.

### Quando atualizar:
- Criar novo sistema/módulo
- Adicionar nova tabela no banco de dados
- Criar novo padrão de código
- Modificar arquitetura existente
- Adicionar nova integração externa
- Criar novos endpoints importantes
- Modificar fluxo de agentes de IA
- Alterar estrutura de prompts
- Descobrir informação relevante não documentada

### Como atualizar:
1. Localize a seção apropriada neste documento
2. Adicione a informação de forma concisa e clara
3. Mantenha o formato consistente (tabelas, blocos de código, diagramas ASCII)
4. Atualize a data "Última atualização" no topo do documento
5. Se criar nova seção, adicione no índice implícito do documento

### Por que isso é crítico:
- Agentes futuros terão contexto completo e atualizado
- Evita retrabalho e erros por falta de informação
- Mantém a documentação como **fonte única de verdade**
- Acelera significativamente o trabalho de agentes subsequentes
- Reduz alucinações por falta de contexto

---

## VISÃO GERAL DO PROJETO

**Portal PGE-MS** é um sistema web para a Procuradoria-Geral do Estado de Mato Grosso do Sul que utiliza IA para automatizar tarefas jurídicas.

| Aspecto | Detalhes |
|---------|----------|
| **Framework** | FastAPI + Uvicorn |
| **Banco de Dados** | PostgreSQL (prod) / SQLite (dev) |
| **ORM** | SQLAlchemy 2.0 |
| **IA** | Google Gemini API |
| **Frontend** | Vanilla JS + TailwindCSS (SPAs) |
| **Deploy** | Railway |

---

## ESTRUTURA DE DIRETÓRIOS

```
portal-pge/
├── admin/                    # Painel administrativo
│   ├── models.py             # PromptConfig, ConfiguracaoIA
│   ├── models_prompts.py     # PromptModulo (sistema modular)
│   ├── models_prompt_groups.py  # Grupos e subgrupos de prompts
│   ├── router.py             # API admin (~1600 LOC)
│   └── router_prompts.py     # CRUD de prompts modulares
│
├── auth/                     # Autenticação JWT
│   ├── models.py             # User com roles e permissões
│   ├── router.py             # Login, logout, change password
│   ├── security.py           # JWT + bcrypt
│   └── dependencies.py       # get_current_active_user
│
├── database/
│   ├── connection.py         # Engine SQLAlchemy
│   └── init_db.py            # Migrations automáticas (~1073 LOC)
│
├── frontend/templates/       # Templates Jinja2 do portal
│   ├── dashboard.html
│   ├── login.html
│   └── admin_*.html          # 10+ páginas admin
│
├── services/
│   └── gemini_service.py     # Wrapper Gemini API (~552 LOC)
│
├── sistemas/                 # MÓDULOS DE NEGÓCIO
│   ├── gerador_pecas/        # Gerador de peças jurídicas
│   ├── pedido_calculo/       # Cálculo de danos
│   ├── prestacao_contas/     # Análise de prestação de contas
│   ├── matriculas_confrontantes/
│   └── assistencia_judiciaria/
│
├── main.py                   # Entry point FastAPI
├── config.py                 # Configurações centralizadas
└── requirements.txt          # Dependências Python
```

---

## SISTEMAS PRINCIPAIS

### 1. GERADOR DE PEÇAS JURÍDICAS (`/gerador-pecas`)

**Objetivo:** Gerar documentos jurídicos (contestações, recursos, pareceres) usando IA.

**Arquitetura: Pipeline de 3 Agentes**

```
┌─────────────────────────────────────────────────────────────┐
│ AGENTE 1: Coletor (AgenteTJMSIntegrado)                     │
│ - Busca processo no TJ-MS via SOAP                          │
│ - Baixa PDFs de documentos                                  │
│ - Extrai texto com PyMuPDF                                  │
│ - Gera RESUMO CONSOLIDADO                                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ AGENTE 2: Detector (DetectorModulosIA)                      │
│ - Analisa resumo com Gemini Flash                           │
│ - Ativa módulos de CONTEÚDO relevantes                      │
│ - Retorna: tipo_peca, modulos_ids[], justificativa          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ AGENTE 3: Gerador (Gemini Pro)                              │
│ - Monta prompt: BASE + PEÇA + CONTEÚDO[n]                   │
│ - Gera peça completa em Markdown                            │
│ - Suporta chat para edições incrementais                    │
└─────────────────────────────────────────────────────────────┘
```

**Arquivos-chave:**
- `orquestrador_agentes.py` - Coordena os 3 agentes
- `detector_modulos.py` - Detecção inteligente de módulos
- `router.py` - Endpoints da API
- `docx_converter.py` - Markdown → DOCX

**Modularidade de Prompts:**
```
PROMPT_FINAL = BASE_SYSTEM + PROMPT_PEÇA + PROMPT_CONTEÚDO_1 + ... + PROMPT_CONTEÚDO_N
```

**Grupos e Subgrupos (Prompts de Conteudo):**
- Apenas prompts CONTEUDO usam grupo/subgrupo; BASE e PECA continuam globais.
- Usuarios possuem default_group_id e allowed_group_ids; multi-grupo exige selecao no gerador-pecas.

**Endpoints de grupos (gerador-pecas):**
- /gerador-pecas/api/grupos-disponiveis
- /gerador-pecas/api/grupos/{group_id}/subgrupos

**Admin (prompts modulares):**
- /admin/api/prompts-modulos/grupos
- /admin/api/prompts-modulos/grupos/{group_id}/subgrupos

**Modo de Ativação de Prompts:**

O sistema suporta dois modos de ativação de prompts:
1. **LLM (padrão)**: IA decide se ativa o módulo
2. **Determinístico**: Regras JSON avaliadas sem LLM

**Geração de Regras via Linguagem Natural:**
```
┌─────────────────────────────────────────────────────────────┐
│ UI: Campo "Condição em linguagem natural"                   │
│ Ex: "Ativar quando medicamento não estiver incorporado SUS" │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Backend: POST /admin/api/extraction/regras-deterministicas/gerar│
│ - Chama Gemini 3 Flash Preview                              │
│ - Gera AST JSON da regra                                    │
│ - Valida variáveis existentes                               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Resposta:                                                   │
│ - success: true → regra AST + variáveis usadas              │
│ - success: false → variaveis_faltantes + sugestões          │
└─────────────────────────────────────────────────────────────┘
```

**Arquivos de Regras Determinísticas:**
- `services_deterministic.py` - DeterministicRuleGenerator, DeterministicRuleEvaluator
- `router_extraction.py` - Endpoints de geração/validação/avaliação

**Formato AST JSON:**
```json
{
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "valor_causa", "operator": "greater_than", "value": 100000},
        {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": true}
    ]
}
```

**Operadores suportados:**
- equals, not_equals, contains, not_contains
- greater_than, less_than, greater_or_equal, less_or_equal
- exists, not_exists, is_empty, is_not_empty
- in_list, not_in_list, matches_regex
- and, or, not (lógicos)

---

### 2. PEDIDO DE CÁLCULO (`/pedido-calculo`)

**Objetivo:** Extrair dados de processos e calcular valores de condenação.

**Pipeline:**
1. **Agente 1:** Análise XML (sem IA) - extrai estrutura do processo
2. **Agente 2:** Extração de PDFs (Gemini Flash) - dados estruturados
3. **Agente 3:** Geração (Gemini Flash) - cálculo + documento final

**Arquivos-chave:**
- `agentes.py` (~1720 LOC) - Implementação dos agentes
- `xml_parser.py` - Parser de documentos XML do TJ-MS
- `document_downloader.py` - Download de PDFs

---

### 3. PRESTAÇÃO DE CONTAS (`/prestacao-contas`)

**Objetivo:** Analisar prestações de contas de processos de medicamentos.

**Fluxo:**
1. Scraping do extrato da subconta (Playwright)
2. Coleta de documentos do processo
3. Identificação de tipos de documentos (IA)
4. Análise e parecer final (favorável/desfavorável/dúvida)

**Arquivos-chave:**
- `agente_analise.py` - Agente de análise com IA
- `identificador_peticoes.py` - Classificação de documentos
- `scrapper_subconta.py` - Extração de PDF via Playwright
- `services.py` - Lógica de negócio principal

**Formato de Resposta (Markdown estruturado):**
```
PARECER: [FAVORAVEL ou DESFAVORAVEL ou DUVIDA]

---FUNDAMENTACAO---
[Análise em Markdown]

---IRREGULARIDADES---
[Lista ou "Nenhuma"]

---PERGUNTAS---
[Lista ou "Nenhuma"]
```

---

## PADRÕES DE CÓDIGO

### Estrutura de Módulos
```
sistemas/<modulo>/
├── router.py           # Endpoints FastAPI
├── services.py         # Lógica de negócio
├── models.py           # SQLAlchemy + Pydantic
├── schemas.py          # Schemas Pydantic (opcional)
├── templates/          # Frontend SPA
│   ├── index.html
│   └── app.js
└── <arquivos específicos>
```

### Padrão de Routers
```python
from fastapi import APIRouter, Depends, HTTPException
from auth.dependencies import get_current_active_user
from database.connection import get_db

router = APIRouter()

@router.post("/endpoint")
async def handler(
    request: RequestSchema,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    # Verificar permissões
    if not current_user.pode_acessar_sistema("nome_sistema"):
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Lógica...
    return {"success": True}
```

### Padrão de Agentes IA
```python
class AgenteExemplo:
    def __init__(self, modelo: str, temperatura: float, db: Session = None):
        self.modelo = modelo
        self.temperatura = temperatura
        self.db = db

    async def executar(self, dados: DadosEntrada) -> ResultadoAgente:
        # 1. Preparar prompt
        prompt = self._montar_prompt(dados)

        # 2. Chamar IA
        service = GeminiService()
        resposta = await service.generate(prompt, model=self.modelo)

        # 3. Parsear resposta
        resultado = self._parse_resposta(resposta.content)

        return resultado
```

### Tratamento de Erros
```python
try:
    resultado = await operacao_arriscada()
except Exception as e:
    logger.error(f"Erro em operacao: {e}")
    raise HTTPException(status_code=500, detail=str(e))
```

---

## BANCO DE DADOS

### Tabelas Principais

| Tabela | Propósito |
|--------|-----------|
| `users` | Usuários com roles e permissões |
| `prompt_configs` | Prompts legado (sistema, tipo, conteudo) |
| `prompt_modulos` | Prompts modulares (BASE/PEÇA/CONTEÚDO) |
| `prompt_groups` | Grupos principais dos prompts modulares |
| `prompt_subgroups` | Subgrupos por grupo (filtro adicional) |
| `user_prompt_groups` | Relacao N:N entre usuarios e grupos |
| `prompt_modulos_historico` | Versionamento de prompts |
| `geracoes_pecas` | Histórico de peças geradas |
| `feedbacks_pecas` | Feedback dos usuários |
| `versoes_pecas` | Versões de cada peça |
| `geracoes_pedido_calculo` | Histórico de pedidos de cálculo |
| `geracoes_prestacao_contas` | Histórico de análises de prestação |
| `configuracoes_ia` | Configurações de modelos por sistema |

### Migrações
As migrações são automáticas em `database/init_db.py`. Para adicionar coluna:
```python
# Em init_db.py, adicionar na lista de migrações:
migrations = [
    # ... existentes ...
    ("nome_tabela", "nova_coluna", "TEXT", "NULL"),
]
```

---

## AUTENTICAÇÃO E AUTORIZAÇÃO

### Modelo de Usuário
```python
class User:
    username: str
    hashed_password: str
    role: str  # "admin" ou "user"
    is_active: bool
    sistemas_permitidos: List[str]  # ["gerador_pecas", "pedido_calculo"]
    permissoes_especiais: List[str]  # ["edit_prompts", "view_logs"]
    default_group_id: int  # Grupo padrao de prompts
    allowed_group_ids: List[int]  # Grupos de conteudo permitidos
```

### Verificação de Acesso
```python
# Verificar acesso a sistema
if not user.pode_acessar_sistema("gerador_pecas"):
    raise HTTPException(403)

# Verificar permissão especial
if not user.tem_permissao("edit_prompts"):
    raise HTTPException(403)

# Admin tem acesso total
if user.role == "admin":
    pass  # Acesso liberado
```

---

## INTEGRAÇÃO COM IA

### GeminiService
```python
from services.gemini_service import GeminiService

service = GeminiService()

# Geração simples
response = await service.generate(
    prompt="Analise este texto...",
    system_prompt="Você é um analista jurídico...",
    model="gemini-3-flash-preview",
    temperature=0.3
)

# Com imagens
response = await service.generate_with_images(
    prompt="Analise estas notas fiscais...",
    images_base64=["data:image/jpeg;base64,..."],
    model="gemini-3-flash-preview"
)
```

### Modelos Disponíveis
- `gemini-3-flash-preview` - padrão
- `gemini-3-pro-preview` - Mais capaz, mais caro
- `gemini-2.5-flash-lite` - Mais rápido e mais barato, usado para classificações simples

---

## INTEGRAÇÃO COM TJ-MS

### IMPORTANTE: Arquitetura de Proxy

O TJ-MS **bloqueia requisições de IPs de cloud providers** (Railway, Fly.io, etc.) através de WAF.
Por isso, TODAS as requisições ao TJ-MS devem passar por proxy.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ARQUITETURA DE PROXY TJ-MS                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  [Railway]  ──────►  [Proxy Fly.io]  ──────►  [esaj.tjms.jus.br]    │
│     │                (TJMS_PROXY_URL)              (SOAP API)        │
│     │                     │                                          │
│     │                     ▼                                          │
│     │               Latência: ~0.15s                                 │
│     │                                                                │
│     └──────────►  [Proxy Local/ngrok]  ──────►  [www.tjms.jus.br]   │
│               (TJMS_PROXY_LOCAL_URL)           (Subconta/Web)        │
│                         │                                            │
│                         ▼                                            │
│                  Playwright no PC                                    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Cliente Centralizado: `services/tjms_client.py`

**SEMPRE use este módulo para comunicação com TJ-MS.** Não crie implementações paralelas.

```python
from services import (
    soap_consultar_processo,
    soap_baixar_documentos,
    extrair_subconta,
    ResultadoSubconta,
    diagnostico_tjms,
)

# Consulta SOAP (usa Fly.io automaticamente)
xml_resposta = await soap_consultar_processo(
    numero_processo="0857327-80.2025.8.12.0001",
    movimentos=True,
    incluir_documentos=True,
)

# Download de documentos
xml_docs = await soap_baixar_documentos(
    numero_processo="0857327-80.2025.8.12.0001",
    ids_documentos=["123456", "789012"],
)

# Extrato de subconta (usa Proxy Local automaticamente)
resultado = await extrair_subconta("0857327-80.2025.8.12.0001")
if resultado.status == "ok":
    pdf_bytes = resultado.pdf_bytes
    texto = resultado.texto_extraido
```

### Variáveis de Ambiente TJ-MS

```env
# Proxies (OBRIGATÓRIOS em produção)
TJMS_PROXY_URL=https://proxytjms.fly.dev          # Fly.io - para SOAP
TJMS_PROXY_LOCAL_URL=https://xxx.ngrok-free.dev   # PC local - para subconta

# Credenciais SOAP (MNI)
MNI_USER=usuario_mni
MNI_PASS=senha_mni

# Credenciais Web (Subconta)
TJMS_USUARIO=usuario_web
TJMS_SENHA=senha_web

# Timeouts (opcionais)
TJMS_SOAP_TIMEOUT=60
TJMS_SUBCONTA_TIMEOUT=180
```

### Quando Usar Cada Proxy

| Operação | Proxy | Motivo |
|----------|-------|--------|
| **SOAP** (consultar processo, baixar docs) | Fly.io | Latência menor (~0.15s), mais estável |
| **Subconta** (extrato PDF) | Proxy Local | Playwright precisa rodar no PC local |

### Proxy Local (ngrok)

O proxy local roda no PC do desenvolvedor e é exposto via ngrok:

**Repositório:** `E:\Projetos\PGE\tjms-proxy-local\`

**Iniciar:**
```bash
cd E:\Projetos\PGE\tjms-proxy-local
iniciar_ngrok.bat
```

**Endpoints disponíveis:**
- `POST /soap` - Proxy para SOAP
- `POST /extrair-subconta` - Executa Playwright e retorna PDF/texto
- `GET /diagnostico` - Testa conectividade

**URL fixo ngrok:** `https://uncommonplace-unsubserviently-azalee.ngrok-free.dev`

### Diagnóstico

```python
from services import diagnostico_tjms

resultado = await diagnostico_tjms()
# {
#   "config": {
#     "proxy_local": "https://...",
#     "proxy_flyio": "https://...",
#     "soap_url": "https://.../soap",
#     "subconta_endpoint": "https://.../extrair-subconta",
#   },
#   "testes": {
#     "proxy_local": {"ok": true, "tempo_ms": 120.5, "mensagem": "OK"},
#     "proxy_flyio": {"ok": true, "tempo_ms": 55.2, "mensagem": "OK"},
#   }
# }
```

---

## FRONTEND

### Arquitetura SPA
Cada sistema tem seu próprio SPA em `sistemas/<modulo>/templates/`:
- `index.html` - Entry point
- `app.js` - Lógica JavaScript

### Padrões de Comunicação
```javascript
// Fetch com autenticação (cookies JWT)
const response = await fetch('/gerador-pecas/api/processar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ numero_cnj: '0000000-00.2024.8.12.0001' })
});

// SSE para streaming
const eventSource = new EventSource('/api/stream?id=123');
eventSource.onmessage = (e) => {
    const data = JSON.parse(e.data);
    // Atualizar UI...
};
```

---

## CONVENÇÕES IMPORTANTES

### Nomenclatura
- **Routers:** `router.py`, `router_admin.py`
- **Modelos:** `models.py` (SQLAlchemy + Pydantic)
- **Serviços:** `services.py`
- **Templates:** `templates/index.html`, `templates/app.js`

### Commits
Seguir Conventional Commits:
```
feat: adicionar nova funcionalidade
fix: corrigir bug específico
refactor: refatorar código sem mudar comportamento
docs: atualizar documentação
```

### Logs
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Operação iniciada")
logger.warning("Situação inesperada")
logger.error(f"Erro: {e}")
```

---

## CONFIGURAÇÃO

### Variáveis de Ambiente Obrigatórias
```env
# Banco de dados
DATABASE_URL=postgresql://user:pass@host:5432/db

# Segurança
SECRET_KEY=chave-secreta-jwt-256-bits

# IA
GEMINI_KEY=sua-api-key

# TJ-MS (integração)
TJ_WS_USER=usuario
TJ_WS_PASS=senha

# Admin inicial
ADMIN_USERNAME=admin
ADMIN_PASSWORD=senha-inicial
```

### Configuração Local
1. Copiar `.env.example` para `.env`
2. Preencher variáveis
3. Executar: `python main.py` ou `uvicorn main:app --reload`

---

## DICAS PARA AGENTES DE IA

### Ao Adicionar Funcionalidade
1. Seguir estrutura existente do módulo mais similar
2. Criar router + services + models se necessário
3. Adicionar rota em `main.py`
4. Criar template frontend se houver UI

### Ao Modificar Prompts
1. Verificar se prompt está em `prompt_configs` ou `prompt_modulos`
2. Prompts do admin têm prioridade sobre hardcoded
3. Usar `_buscar_prompt_admin(db, "nome")` para buscar

### Ao Debugar
1. Verificar logs no terminal (uvicorn)
2. Usar `/admin/*/historico` para ver chamadas de IA
3. Tabelas de log: `log_chamadas_ia_*`

### Ao Criar Novo Sistema
```
1. Criar pasta: sistemas/novo_sistema/
2. Criar arquivos base:
   - __init__.py
   - router.py
   - models.py
   - services.py
   - templates/index.html
3. Registrar router em main.py
4. Adicionar migrations em init_db.py
5. Criar página admin se necessário
```

---

## ARQUIVOS CRÍTICOS

| Arquivo | Importância | LOC |
|---------|-------------|-----|
| `main.py` | Entry point, rotas principais | ~480 |
| `database/init_db.py` | Migrations, seeds | ~1073 |
| `config.py` | Configurações | ~93 |
| `auth/models.py` | User + permissões | ~58 |
| `services/gemini_service.py` | Wrapper IA | ~552 |
| `admin/router.py` | API admin completa | ~1600 |
| `admin/router_prompts.py` | CRUD prompts | ~1016 |

---

## FLUXO DE DADOS TÍPICO

```
[Frontend] → [Router] → [Service] → [Agente IA] → [Gemini API]
                ↓                        ↓
            [Database]              [Log chamada]
                ↓
           [Response]
                ↓
          [Frontend]
```

---

## TROUBLESHOOTING

### Erro de Permissão 403
- Verificar `sistemas_permitidos` do usuário
- Verificar `permissoes_especiais` se for área admin
- Admin tem bypass total

### Erro de IA
- Verificar `GEMINI_KEY` no `.env`
- Verificar modelo selecionado em `configuracoes_ia`
- Consultar logs de chamadas no admin

### Erro de Banco
- Verificar `DATABASE_URL`
- Rodar migrations: reiniciar aplicação
- Verificar se tabela existe em init_db.py

### Frontend não carrega
- Verificar se rota está registrada em `main.py`
- Verificar se template existe em `templates/`
- Checar console do navegador para erros JS

---

*Este documento deve ser atualizado sempre que houver mudanças significativas na arquitetura.*
