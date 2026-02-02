# RELATÓRIO DE ESCALABILIDADE — PREPARO PARA ATÉ 50 USUÁRIOS SIMULTÂNEOS

**Data:** 2026-01-24
**Autor:** Análise Automatizada Ralph Loop
**Versão:** 1.0

---

## 1. RESUMO EXECUTIVO

### Veredicto: **PARCIAL**

O sistema Portal PGE-MS possui uma arquitetura **bem fundamentada** com componentes de resiliência já implementados (Circuit Breaker, Retry, Rate Limiting, Health Checks). No entanto, para suportar com **segurança e estabilidade** 50 usuários simultâneos em múltiplos sistemas, existem **gargalos críticos** que precisam ser endereçados.

### Top 5 Gargalos Prováveis

| # | Gargalo | Risco | Impacto |
|---|---------|-------|---------|
| 1 | **Pool de conexões DB limitado** | ALTO | Pool padrão de 20 conexões pode saturar com 50 usuários gerando peças simultâneas |
| 2 | **Operações LLM sem limite de concorrência** | ALTO | 50 chamadas simultâneas ao Gemini podem causar rate limiting e timeouts em cascata |
| 3 | **Download TJMS sequencial por batch** | MÉDIO | Múltiplos usuários baixando documentos do TJ-MS podem saturar o proxy |
| 4 | **Jobs BERT Training sem isolamento** | MÉDIO | Jobs de treinamento competem por CPU/RAM com requests da API |
| 5 | **Cache em memória com limite baixo** | MÉDIO | Cache de resumos (5000 itens) pode não ser suficiente para 50 usuários ativos |

### Top 5 Riscos Críticos

| # | Risco | Probabilidade | Severidade |
|---|-------|---------------|------------|
| 1 | **Cascata de timeouts em pico** | Alta | Alta - múltiplos agentes falhando simultaneamente |
| 2 | **Exaustão de conexões DB** | Média | Alta - bloqueia toda a aplicação |
| 3 | **Rate limit do Gemini API** | Alta | Média - interrompe geração de peças |
| 4 | **OOM em OCR de PDFs grandes** | Média | Alta - pode derrubar o processo |
| 5 | **Circuit Breaker em loop de falhas** | Média | Média - serviços ficam indisponíveis por muito tempo |

### Top 10 Ações Recomendadas (Ordem de Impacto)

| Prioridade | Ação | Esforço |
|------------|------|---------|
| P0-1 | Aumentar pool DB para 35 conexões (50 * 0.7) | Baixo |
| P0-2 | Implementar semáforo global para chamadas LLM (max 10 concorrentes) | Médio |
| P0-3 | Adicionar timeout explícito em todas as rotas de streaming | Baixo |
| P0-4 | Configurar rate limit por rota específica de geração de peças | Baixo |
| P1-1 | Implementar fila (Redis/Celery) para jobs BERT Training | Alto |
| P1-2 | Adicionar limite de tamanho de PDF para OCR (50MB) | Baixo |
| P1-3 | Aumentar cache de resumos para 10.000 itens | Baixo |
| P1-4 | Adicionar métricas de concorrência ativa por endpoint | Médio |
| P2-1 | Implementar cache distribuído (Redis) para multi-instância | Alto |
| P2-2 | Separar workers para jobs pesados (BERT, OCR) | Alto |

---

## 2. MODELO DE CARGA REALISTA

### Perfil de Uso Simultâneo (50 usuários)

```
+--------------------+--------+---------------------------------+
| Atividade          | Usuários| Operações/Minuto               |
+--------------------+--------+---------------------------------+
| Gerador de Peças   | 15     | 15 gerações streaming          |
| Classificador      | 10     | 30 classificações              |
| Pedido de Cálculo  | 8      | 8 processamentos               |
| Relatórios         | 7      | 20 consultas DB                |
| BERT Training      | 3      | 1-2 jobs de treinamento        |
| Admin/Outros       | 7      | 50 requests diversos           |
+--------------------+--------+---------------------------------+
```

### Operações Mais Pesadas e Efeitos

| Operação | Recurso Principal | Duração Típica | Concorrência Máxima Recomendada |
|----------|-------------------|----------------|----------------------------------|
| **Geração de Peça (streaming)** | LLM + DB | 30-120s | 10 simultâneas |
| **Download Documentos TJMS** | Network + Proxy | 10-60s | 5 simultâneas |
| **OCR de PDF** | CPU + RAM | 5-30s | 3 simultâneas |
| **Geração DOCX** | CPU | 2-5s | 10 simultâneas |
| **BERT Training** | CPU + GPU | 10min-2h | 1 por vez |
| **Classificação de Documentos** | LLM | 5-15s | 15 simultâneas |

### Rotas Críticas (Hot Paths)

1. **`POST /gerador-pecas/api/processar-stream`** - Orquestra 3 agentes com streaming
2. **`POST /classificador/api/classificar`** - Classificação via LLM
3. **`POST /pedido-calculo/api/processar`** - Processamento de cálculos
4. **`POST /bert-training/api/jobs/start`** - Início de treinamento
5. **`GET /assistencia/api/consultar`** - Consulta TJMS

### Rotas Secundárias

- Admin routes (`/admin/*`)
- Health checks (`/health/*`)
- Métricas (`/metrics`)
- Downloads de DOCX exportados

---

## 3. AUDITORIA POR CAMADA

### 3.1 Frontend (Consumo de API)

**Status:** ✅ Adequado

**Localização:** `sistemas/*/templates/`, `frontend/`

**Observações:**
- Frontend TypeScript com fetch adequado
- Suporte a streaming SSE implementado
- Não há polling agressivo (filtro de status aplicado)

**Riscos:**
- Reconexão em caso de erro de streaming não documentada
- Não há backoff em retry de requests

**Mitigação:**
- Implementar exponential backoff no frontend para reconexões

---

### 3.2 Backend API (FastAPI)

**Status:** ⚠️ Parcial

**Localização:** `main.py`, `sistemas/*/router.py`

**Pontos Positivos:**
- Framework async (FastAPI) adequado para concorrência
- Middleware de request ID implementado (`middleware/request_id.py`)
- Middleware de métricas implementado (`middleware/metrics.py`)
- Exception handlers sanitizados em produção

**Problemas Identificados:**

| Problema | Arquivo | Linha | Risco |
|----------|---------|-------|-------|
| Streaming sem timeout global | `gerador_pecas/router.py` | 426-700 | Conexões podem ficar abertas indefinidamente |
| Sem limite de concorrência por operação | N/A | N/A | Saturação em pico |
| `db.commit()` síncrono em endpoint async | `gerador_pecas/router.py` | 673 | Bloqueia event loop |

**Mitigação:**
```python
# Adicionar timeout no streaming
async with asyncio.timeout(300):  # 5 minutos máximo
    async for event in event_generator():
        yield event
```

---

### 3.3 Banco de Dados (PostgreSQL)

**Status:** ⚠️ Parcial

**Localização:** `database/connection.py`, `config.py`

**Configuração Atual:**
```python
# Produção
POOL_SIZE = 20  # via DB_POOL_SIZE
MAX_OVERFLOW = 15  # via DB_MAX_OVERFLOW
POOL_TIMEOUT = 10s
POOL_RECYCLE = 1800s (30min)
pool_pre_ping = True  # Ativo em produção
```

**Cálculo de Pool para 50 Usuários:**
```
Conexões necessárias (estimativa):
- 50 usuários * 0.6 conexão média = 30 conexões base
- Pico (burst): 30 * 1.5 = 45 conexões
- Recomendado: pool_size=35, max_overflow=15 = 50 conexões máximas
```

**Problemas:**
- Pool atual (20+15=35) pode ser insuficiente em pico
- Commits síncronos bloqueiam conexões por mais tempo

**Mitigação:**
```python
# Em database/connection.py
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "35"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "15"))
```

---

### 3.4 Storage (Upload/Download)

**Status:** ✅ Adequado

**Localização:** `config.py` (MAX_CONTENT_LENGTH)

**Configuração:**
```python
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", ...}
```

**Observações:**
- Limite de 100MB adequado para PDFs jurídicos
- Arquivos temporários em `sistemas/gerador_pecas/temp_docs/`

**Risco Menor:**
- Não há limpeza automática de temp_docs

**Mitigação:**
- Implementar task periódica para limpeza de arquivos antigos (>24h)

---

### 3.5 Integrações Externas (TJMS, Gemini)

**Status:** ⚠️ Parcial (com boa base)

#### TJ-MS (SOAP/MNI)

**Localização:** `services/tjms/`

**Componentes Implementados:**
- ✅ Cliente async (`client.py`)
- ✅ Circuit Breaker (`failure_threshold=3, recovery_timeout=60s`)
- ✅ Retry com backoff exponencial (`max_retries=3, base_delay=2s`)
- ✅ Timeouts configuráveis (SOAP: 60s, Download: 180s)
- ✅ Batch download com `batch_size=5`

**Problemas:**
| Problema | Risco |
|----------|-------|
| Sem limite de downloads concorrentes entre usuários | Alto |
| Proxy único (Fly.io) pode saturar | Médio |

**Mitigação:**
```python
# Adicionar semáforo global
TJMS_SEMAPHORE = asyncio.Semaphore(5)  # Max 5 downloads simultâneos

async def baixar_documentos(...):
    async with TJMS_SEMAPHORE:
        # código existente
```

#### Google Gemini

**Localização:** `services/gemini_service.py`

**Componentes Implementados:**
- ✅ HTTP Client reutilizável (connection pooling)
- ✅ Circuit Breaker (`failure_threshold=5, recovery_timeout=30s`)
- ✅ Retry com backoff (`MAX_RETRIES=3, RETRY_BASE_DELAY=1s`)
- ✅ Timeouts granulares (Connect: 15s, Read: 180s, Total: 240s)
- ✅ Cache de respostas (`max_size=100, ttl=300s`)
- ✅ Métricas de latência

**Problemas:**
| Problema | Risco |
|----------|-------|
| Sem limite de concorrência global | Alto |
| Rate limit do Gemini (RPM/TPM) não monitorado | Médio |

**Mitigação:**
```python
# Adicionar semáforo global para Gemini
GEMINI_SEMAPHORE = asyncio.Semaphore(10)  # Max 10 chamadas simultâneas

async def chamar_gemini_async(...):
    async with GEMINI_SEMAPHORE:
        # código existente
```

---

### 3.6 Jobs/Fila/Workers

**Status:** ❌ Crítico

**Localização:** `sistemas/bert_training/`, `utils/background_tasks.py`

**Situação Atual:**
- Jobs BERT Training executam no mesmo processo da API
- Watchdog para detecção de jobs travados (`interval=5min`)
- Background tasks com tracking básico

**Problemas Críticos:**
| Problema | Arquivo | Risco |
|----------|---------|-------|
| Sem fila de jobs (tudo em memória) | `bert_training/services.py` | Jobs perdidos em restart |
| Sem isolamento CPU/RAM | N/A | Job pesado afeta API |
| Sem limite de jobs concorrentes | `bert_training/router.py` | OOM possível |
| Sem dead letter queue | N/A | Falhas silenciosas |

**Mitigação P0:**
```python
# Adicionar limite de jobs concorrentes
MAX_CONCURRENT_BERT_JOBS = 1

@router.post("/jobs/start")
async def start_job(...):
    active_jobs = count_active_jobs(db)
    if active_jobs >= MAX_CONCURRENT_BERT_JOBS:
        raise HTTPException(429, "Limite de jobs atingido")
```

**Mitigação P1:**
- Implementar Celery + Redis para fila de jobs
- Separar workers para tarefas pesadas

---

### 3.7 Observabilidade

**Status:** ✅ Bom

**Localização:** `utils/logging_config.py`, `utils/metrics.py`, `utils/health_check.py`

**Implementado:**
- ✅ Logging estruturado (structlog)
- ✅ Request ID para correlação
- ✅ Métricas Prometheus-style em `/metrics`
- ✅ Health checks detalhados em `/health/detailed`
- ✅ Métricas por endpoint (latência, status)
- ✅ Tracking de background tasks

**Melhorias Sugeridas:**
- Adicionar métrica de conexões DB ativas
- Adicionar métrica de concorrência por tipo de operação
- Dashboard visual em `/admin/dashboard` (já existe)

---

### 3.8 Segurança e Limites

**Status:** ⚠️ Parcial

**Localização:** `utils/rate_limit.py`, `utils/brute_force.py`

**Implementado:**
- ✅ Rate limiting global (`100/minute` por IP)
- ✅ Rate limiting de login (`5/minute`)
- ✅ Rate limiting de IA (`10/minute` por usuário)
- ✅ Proteção brute-force
- ✅ Headers de segurança (CSP, HSTS, etc.)

**Configuração Atual:**
```python
RATE_LIMIT_DEFAULT = "100/minute"
RATE_LIMIT_LOGIN = "5/minute"
RATE_LIMIT_AI = "10/minute"
LIMITS["heavy"] = "5/minute"
LIMITS["export"] = "3/minute"
```

**Problemas:**
| Problema | Risco |
|----------|-------|
| Rate limit de IA por usuário, não global | Médio |
| Limite de geração de peças não específico | Médio |
| Storage de rate limit em memória (não persiste) | Baixo |

**Mitigação:**
```python
# Adicionar limites específicos
LIMITS["geracao_peca"] = "6/minute"  # Por usuário
LIMITS["geracao_peca_global"] = "30/minute"  # Global
```

---

## 4. CONCORRÊNCIA E LIMITES

### Simulação: 50 Usuários Simultâneos

#### Cenário: Geração de Peças em Streaming

| Métrica | Valor Atual | Limite Seguro | Risco |
|---------|-------------|---------------|-------|
| Chamadas Gemini simultâneas | Ilimitado | 10 | ALTO |
| Conexões DB ativas | 35 max | 50 | MÉDIO |
| Streams SSE abertos | Ilimitado | 20 | MÉDIO |
| Memória por stream | ~50MB | - | MÉDIO |

**O que acontece:**
1. 15 usuários iniciam geração simultaneamente
2. Agente 1: 15 consultas TJMS (saturação do proxy possível)
3. Agente 3: 15 chamadas Gemini (rate limit possível)
4. Conexões DB: 15 * 2 = 30 (dentro do pool)
5. **Risco: Timeout em cascata se Gemini rate limitar**

#### Cenário: Classificação em Lote

| Métrica | Valor Atual | Limite Seguro | Risco |
|---------|-------------|---------------|-------|
| Classificações simultâneas | Ilimitado | 15 | MÉDIO |
| Chamadas LLM por classificação | 1 | - | - |

**O que acontece:**
1. 10 usuários classificando 5 documentos cada = 50 chamadas LLM
2. Rate limit do Gemini provavelmente atingido
3. Circuit Breaker abre após 5 falhas
4. **Risco: Serviço indisponível por 30s**

#### Cenário: Download TJMS em Massa

| Métrica | Valor Atual | Limite Seguro | Risco |
|---------|-------------|---------------|-------|
| Downloads simultâneos | batch_size=5 por usuário | 5 global | ALTO |
| Conexões ao proxy | Ilimitado | 10 | MÉDIO |

**O que acontece:**
1. 5 usuários baixando documentos simultaneamente
2. 5 * 5 (batch) = 25 requisições ao TJMS
3. Proxy Fly.io pode saturar
4. **Risco: Timeouts e falhas em cascata**

#### Cenário: OCR em Massa

| Métrica | Valor Atual | Limite Seguro | Risco |
|---------|-------------|---------------|-------|
| OCR simultâneo | Ilimitado | 3 | ALTO |
| RAM por PDF | 100-500MB | - | ALTO |

**O que acontece:**
1. 5 PDFs grandes (50MB cada) em OCR simultâneo
2. Uso de RAM: 5 * 500MB = 2.5GB
3. **Risco: OOM killer pode derrubar processo**

### Estimativa de Recursos Necessários

```
CPU:
- Base: 2 vCPUs
- Pico (50 usuários): 4-6 vCPUs
- Com BERT Training: 8+ vCPUs

RAM:
- Base: 2GB
- Pico (50 usuários): 4-6GB
- Com BERT Training: 8-16GB

Network:
- Outbound: ~50 Mbps em pico (downloads TJMS)
- Latência Gemini: 100-500ms por chamada

DB Connections:
- Recomendado: 50 conexões no pool
```

---

## 5. PLANO DE MELHORIA

### P0 — Obrigatório Antes de 50 Usuários

| ID | Ação | Arquivo | Esforço |
|----|------|---------|---------|
| P0-1 | Aumentar pool DB para 35+15 conexões | `database/connection.py` | 1h |
| P0-2 | Implementar semáforo Gemini (max 10) | `services/gemini_service.py` | 2h |
| P0-3 | Implementar semáforo TJMS (max 5) | `services/tjms/client.py` | 2h |
| P0-4 | Adicionar timeout global em streaming (5min) | `gerador_pecas/router.py` | 1h |
| P0-5 | Limitar jobs BERT concorrentes (max 1) | `bert_training/router.py` | 1h |
| P0-6 | Adicionar rate limit específico geração (6/min) | `utils/rate_limit.py` | 1h |
| P0-7 | Limitar OCR simultâneo (max 3) | `sistemas/*/services.py` | 2h |

### P1 — Estabilidade e Custo

| ID | Ação | Arquivo | Esforço |
|----|------|---------|---------|
| P1-1 | Implementar fila Celery + Redis para BERT | `sistemas/bert_training/` | 2d |
| P1-2 | Aumentar cache de resumos (10.000 itens) | `utils/cache.py` | 30min |
| P1-3 | Adicionar métrica de concorrência ativa | `utils/metrics.py` | 4h |
| P1-4 | Limpeza automática de temp_docs | `utils/background_tasks.py` | 2h |
| P1-5 | Monitorar rate limit Gemini (RPM/TPM) | `services/gemini_service.py` | 4h |
| P1-6 | Implementar graceful shutdown completo | `main.py` | 4h |

### P2 — Evolução e Manutenção

| ID | Ação | Arquivo | Esforço |
|----|------|---------|---------|
| P2-1 | Cache distribuído Redis (multi-instância) | `utils/cache.py` | 1d |
| P2-2 | Workers separados para BERT/OCR | Infra | 2d |
| P2-3 | Auto-scaling baseado em métricas | Infra | 1d |
| P2-4 | Rate limit com Redis (persistente) | `utils/rate_limit.py` | 4h |
| P2-5 | Tracing distribuído (OpenTelemetry) | `utils/` | 1d |

---

## 6. CHECKLIST DE READINESS

### Infraestrutura

| Item | Status | Notas |
|------|--------|-------|
| Pool de conexões DB adequado | ⚠️ Parcial | Aumentar para 35+15 |
| Timeouts configurados | ✅ Pronto | Gemini: 240s, TJMS: 60s |
| Health checks | ✅ Pronto | /health/detailed funcional |
| Métricas Prometheus | ✅ Pronto | /metrics disponível |
| Rate limiting | ⚠️ Parcial | Falta limite específico de geração |

### Resiliência

| Item | Status | Notas |
|------|--------|-------|
| Circuit Breaker Gemini | ✅ Pronto | 5 falhas, 30s recovery |
| Circuit Breaker TJMS | ✅ Pronto | 3 falhas, 60s recovery |
| Retry com backoff | ✅ Pronto | Exponencial implementado |
| Graceful degradation | ⚠️ Parcial | Falta fallback em alguns casos |

### Concorrência

| Item | Status | Notas |
|------|--------|-------|
| Semáforo Gemini | ❌ Faltando | Crítico - implementar |
| Semáforo TJMS | ❌ Faltando | Crítico - implementar |
| Semáforo OCR | ❌ Faltando | Importante - implementar |
| Limite jobs BERT | ❌ Faltando | Importante - implementar |

### Observabilidade

| Item | Status | Notas |
|------|--------|-------|
| Logging estruturado | ✅ Pronto | structlog configurado |
| Request ID | ✅ Pronto | Correlação funcional |
| Métricas de latência | ✅ Pronto | Por endpoint |
| Métricas de concorrência | ❌ Faltando | Adicionar |
| Dashboard visual | ✅ Pronto | /admin/dashboard |

### Segurança

| Item | Status | Notas |
|------|--------|-------|
| Rate limiting global | ✅ Pronto | 100/min por IP |
| Rate limiting login | ✅ Pronto | 5/min |
| Rate limiting IA | ✅ Pronto | 10/min por usuário |
| Headers de segurança | ✅ Pronto | CSP, HSTS, etc. |
| CORS configurado | ✅ Pronto | Produção restritivo |

### Jobs/Workers

| Item | Status | Notas |
|------|--------|-------|
| Fila de jobs | ❌ Faltando | P1 - implementar Celery |
| Workers isolados | ❌ Faltando | P2 - separar processos |
| Watchdog BERT | ✅ Pronto | Intervalo 5min |
| Idempotência | ⚠️ Parcial | Alguns endpoints vulneráveis |

---

## 7. ARQUIVOS E ÁREAS INSPECIONADAS

### Configuração e Inicialização
- `config.py` - Configurações centralizadas
- `main.py` - Aplicação FastAPI principal
- `database/connection.py` - Pool de conexões DB

### Sistemas Principais
- `sistemas/gerador_pecas/router.py` - Rotas de geração de peças
- `sistemas/gerador_pecas/orquestrador_agentes.py` - Orquestração dos 3 agentes
- `sistemas/classificador_documentos/router.py` - Classificação de documentos
- `sistemas/bert_training/router.py` - Treinamento BERT
- `sistemas/bert_training/services.py` - Serviços BERT

### Serviços Compartilhados
- `services/gemini_service.py` - Cliente Gemini centralizado
- `services/tjms/client.py` - Cliente TJMS unificado
- `services/tjms/config.py` - Configuração TJMS

### Utilitários de Resiliência
- `utils/circuit_breaker.py` - Padrão Circuit Breaker
- `utils/retry.py` - Retry com backoff exponencial
- `utils/rate_limit.py` - Rate limiting (slowapi)
- `utils/timeouts.py` - Timeouts centralizados (se existir)
- `utils/cache.py` - Cache em memória TTL
- `utils/background_tasks.py` - Tarefas em background

### Observabilidade
- `utils/metrics.py` - Métricas Prometheus-style
- `utils/health_check.py` - Health checks detalhados
- `utils/logging_config.py` - Logging estruturado
- `middleware/request_id.py` - Correlação de requests
- `middleware/metrics.py` - Middleware de métricas

### Documentação
- `.claude/CLAUDE.md` - Regras operacionais
- `docs/README.md` - Índice da documentação

---

## 8. CONCLUSÃO

O Portal PGE-MS possui uma **base sólida** para escalabilidade com componentes de resiliência bem implementados. Para suportar **50 usuários simultâneos com segurança**, as seguintes ações P0 são **obrigatórias**:

1. **Aumentar pool DB** (config simples)
2. **Implementar semáforos de concorrência** (Gemini, TJMS, OCR)
3. **Adicionar timeouts em streaming**
4. **Limitar jobs BERT concorrentes**

Com essas implementações, estimadas em **1-2 dias de trabalho**, o sistema estará preparado para o cenário de 50 usuários.

As melhorias P1/P2 (fila de jobs, cache distribuído, workers separados) são recomendadas para **estabilidade a longo prazo** e **redução de custos operacionais**.

---

**RALPH_OK_RELATORIO_ESCALABILIDADE_50_20260124**
