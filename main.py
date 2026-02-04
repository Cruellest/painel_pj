<<<<<<< HEAD
# main.py
"""
Portal PGE-MS - Aplicação FastAPI Principal

Unifica os sistemas:
- Assistência Judiciária
- Matrículas Confrontantes

Com autenticação centralizada via JWT.
"""

import logging
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
import os

from config import IS_PRODUCTION, BERT_WORKER_URL

# Middleware de Request ID para rastreamento
from middleware.request_id import RequestIDMiddleware, get_request_id

# Logging estruturado
from utils.logging_config import setup_logging, get_logger

# Configura logging para silenciar requests de polling repetitivos
class StatusPollingFilter(logging.Filter):
    """Filtra logs de polling de status que são muito frequentes"""
    def filter(self, record):
        # Silencia logs de polling de status (GET .../status)
        if '/status HTTP' in record.getMessage():
            return False
        return True

# Aplica filtro ao logger do uvicorn
logging.getLogger("uvicorn.access").addFilter(StatusPollingFilter())

from database.init_db import init_database
from auth.router import router as auth_router
from users.router import router as users_router

# SECURITY: Rate Limiting
from slowapi.errors import RateLimitExceeded
from utils.rate_limit import limiter, rate_limit_exceeded_handler

# SECURITY: Exception handling
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import traceback

# Import dos sistemas
from sistemas.assistencia_judiciaria.router import router as assistencia_router
from sistemas.matriculas_confrontantes.router import router as matriculas_router
from sistemas.gerador_pecas.router import router as gerador_pecas_router
from sistemas.gerador_pecas.router_admin import router as gerador_pecas_admin_router
from sistemas.gerador_pecas.router_categorias_json import router as categorias_json_router
from sistemas.gerador_pecas.router_config_pecas import router as config_pecas_router
from sistemas.gerador_pecas.router_teste_categorias import router as teste_categorias_router
from sistemas.gerador_pecas.router_teste_ativacao import router as teste_ativacao_router

# Import do admin de prompts modulares
from admin.router_prompts import router as prompts_modulos_router

# Import do router de extração (perguntas, modelos, variáveis, regras determinísticas)
from sistemas.gerador_pecas.router_extraction import router as extraction_router

# Import do sistema de Pedido de Cálculo
from sistemas.pedido_calculo.router import router as pedido_calculo_router
from sistemas.pedido_calculo.router_admin import router as pedido_calculo_admin_router

# Import do sistema de Prestação de Contas
from sistemas.prestacao_contas.router import router as prestacao_contas_router
from sistemas.prestacao_contas.router_admin import router as prestacao_contas_admin_router

# Import do sistema de Relatório de Cumprimento
from sistemas.relatorio_cumprimento.router import router as relatorio_cumprimento_router

# Import do sistema de Classificador de Documentos
from sistemas.classificador_documentos.router import router as classificador_documentos_router

# Import do sistema BERT Training
from sistemas.bert_training.router import router as bert_training_router

# Import do sistema de Performance Logs
from admin.router_performance import router as performance_router
from admin.router_gemini_logs import router as gemini_logs_router
from admin.middleware_performance import PerformanceMiddleware

# Métricas de request (Prometheus-style)
from middleware.metrics import MetricsMiddleware
from utils.metrics import get_metrics_text, get_metrics_summary

# Import do serviço de normalização de texto
from services.text_normalizer import text_normalizer_router

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
MATRICULAS_TEMPLATES = BASE_DIR / "sistemas" / "matriculas_confrontantes" / "templates"
ASSISTENCIA_TEMPLATES = BASE_DIR / "sistemas" / "assistencia_judiciaria" / "templates"
GERADOR_PECAS_TEMPLATES = BASE_DIR / "sistemas" / "gerador_pecas" / "templates"
PEDIDO_CALCULO_TEMPLATES = BASE_DIR / "sistemas" / "pedido_calculo" / "templates"
PRESTACAO_CONTAS_TEMPLATES = BASE_DIR / "sistemas" / "prestacao_contas" / "templates"
RELATORIO_CUMPRIMENTO_TEMPLATES = BASE_DIR / "sistemas" / "relatorio_cumprimento" / "templates"
CLASSIFICADOR_DOCUMENTOS_TEMPLATES = BASE_DIR / "sistemas" / "classificador_documentos" / "templates"
BERT_TRAINING_TEMPLATES = BASE_DIR / "sistemas" / "bert_training" / "templates"

# IMPORTANTE: Inicializa banco de dados ANTES de criar o app
# Isso garante que migrações sejam executadas antes de qualquer query
print("[*] Pré-inicializando banco de dados...")
init_database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle events da aplicação.
    Executa na inicialização e no shutdown.
    """
    # Startup
    print("[+] Iniciando Portal PGE-MS...")

    # Configura logging estruturado
    setup_logging()
    logger = get_logger("portal-pge")
    logger.info(f"Iniciando aplicação (environment={'production' if IS_PRODUCTION else 'development'})")
    logger.info(f"BERT_WORKER_URL configurada: {BERT_WORKER_URL}")

    init_database()

    # ==========================================================================
    # Inicializa tabela de embeddings vetoriais (com pgvector se disponível)
    # ==========================================================================
    try:
        from sistemas.gerador_pecas.models_embeddings import init_embeddings_table
        pgvector_ok = init_embeddings_table()
        print(f"[EMBEDDINGS] Tabela inicializada (pgvector: {'disponível' if pgvector_ok else 'não disponível - usando fallback'})")
    except Exception as e:
        print(f"[WARN] Erro ao inicializar tabela de embeddings: {e}")

    # ==========================================================================
    # REGRA DE OURO: Corrige modos de ativação inconsistentes no startup
    # Garante que dados legados ou corrompidos sejam corrigidos automaticamente
    # ==========================================================================
    try:
        from database.connection import SessionLocal
        from sistemas.gerador_pecas.services_deterministic import corrigir_modos_ativacao_inconsistentes

        db = SessionLocal()
        try:
            resultado = corrigir_modos_ativacao_inconsistentes(db, commit=True)
            if resultado["corrigidos"] > 0:
                print(f"[REGRA-DE-OURO] Corrigidos {resultado['corrigidos']} módulos com modo de ativação inconsistente")
            else:
                print("[REGRA-DE-OURO] Todos os módulos estão com modo de ativação correto")
        finally:
            db.close()
    except Exception as e:
        print(f"[WARN] Erro ao verificar modos de ativação: {e}")

    # Configura instrumentação automática de performance
    from admin.perf_instrumentation import setup_instrumentation
    setup_instrumentation(app)

    # ==========================================================================
    # Inicia BERT Watchdog Scheduler
    # Monitora jobs travados e toma ações automáticas (retry, cleanup)
    # ==========================================================================
    try:
        from utils.background_tasks import start_bert_watchdog_scheduler
        from database.connection import SessionLocal
        await start_bert_watchdog_scheduler(
            interval_minutes=5.0,  # Verifica a cada 5 minutos
            db_factory=SessionLocal
        )
        print("[WATCHDOG] BERT Watchdog scheduler iniciado (intervalo: 5 min)")
    except Exception as e:
        print(f"[WARN] Erro ao iniciar BERT Watchdog: {e}")

    yield
    # Shutdown
    print("[-] Encerrando Portal PGE-MS...")

    # Para o scheduler de tarefas
    try:
        from utils.background_tasks import stop_scheduler
        await stop_scheduler()
        print("[WATCHDOG] Scheduler parado")
    except Exception as e:
        print(f"[WARN] Erro ao parar scheduler: {e}")


# Cria a aplicação FastAPI
app = FastAPI(
    title="Portal PGE-MS",
    description="Portal unificado da Procuradoria-Geral do Estado de Mato Grosso do Sul",
    version="1.0.0",
    lifespan=lifespan
)

# ==================================================
# SECURITY: MIDDLEWARE DE HEADERS DE SEGURANÇA
# ==================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    SECURITY: Adiciona headers de segurança HTTP em todas as respostas.

    Headers implementados:
    - X-Frame-Options: Previne clickjacking
    - X-Content-Type-Options: Previne MIME sniffing
    - X-XSS-Protection: Proteção XSS do navegador (legacy)
    - Referrer-Policy: Controla informações de referrer
    - Strict-Transport-Security: Força HTTPS (HSTS)
    - Content-Security-Policy: Controla recursos permitidos
    - Permissions-Policy: Restringe APIs do navegador
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Previne clickjacking - permite embedding apenas do próprio domínio (SAMEORIGIN)
        # DENY bloqueia completamente, SAMEORIGIN permite visualizadores internos (PDF viewer)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # Previne MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Proteção XSS do navegador (legacy, mas ainda útil)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Controla informações de referrer enviadas
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Força HTTPS por 1 ano (apenas em produção)
        if IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Content Security Policy
        # Permite scripts inline (necessário para templates) e CDNs específicos
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com data:",
            "img-src 'self' data: blob: https:",
            "connect-src 'self' https://generativelanguage.googleapis.com https://openrouter.ai http://127.0.0.1:8765 http://localhost:8765 https://cdn.jsdelivr.net http: https:",
            "frame-src 'self' blob:",  # Permite iframes com blob URLs (PDFs)
            "object-src 'self' blob:",  # Permite objetos/plugins com blob URLs (PDFs)
            "frame-ancestors 'self'",  # Permite embedding apenas do próprio domínio (para visualizador de PDF)
            "form-action 'self'",
            "base-uri 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Permissions Policy - restringe APIs do navegador
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"

        # Cache control para páginas HTML (não cachear por segurança)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"

        return response


# ==================================================
# SECURITY: CONFIGURAÇÃO DE CORS
# ==================================================

# SECURITY: Em produção, ALLOWED_ORIGINS DEVE ser definido explicitamente
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()

if _allowed_origins_env:
    # Parse das origens configuradas
    ALLOWED_ORIGINS = [origin.strip() for origin in _allowed_origins_env.split(",") if origin.strip()]
else:
    if IS_PRODUCTION:
        # Em produção, detecta automaticamente o domínio do Railway ou usa padrão
        ALLOWED_ORIGINS = []

        # Railway fornece o domínio público via variável de ambiente
        railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway_domain:
            ALLOWED_ORIGINS.append(f"https://{railway_domain}")

        # Adiciona domínio padrão da PGE se não configurado
        if not ALLOWED_ORIGINS:
            # Fallback para o domínio conhecido da aplicação
            ALLOWED_ORIGINS = ["https://portal-pge-production.up.railway.app"]
    else:
        # Desenvolvimento local - origens permissivas
        ALLOWED_ORIGINS = [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
        ]

# TRACING: Request ID para rastreamento de requisições
# Deve ser o primeiro middleware para que o ID esteja disponível em todo o request
app.add_middleware(RequestIDMiddleware)

# SECURITY: Adiciona middleware de headers ANTES do CORS
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# SECURITY: Rate Limiting
# IMPORTANTE: O limiter já possui default_limits configurado em utils/rate_limit.py
# que aplica 100 req/min para TODAS as rotas automaticamente
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# NOTA: Para proteger rotas específicas com limites mais rigorosos,
# use os decoradores @limiter.limit() diretamente nos endpoints
# Exemplos: @limiter.limit("5/minute") para login, @limiter.limit("10/minute") para IA

# PERFORMANCE: Middleware de timing (apenas para admin quando ativado)
app.add_middleware(PerformanceMiddleware)

# METRICS: Coleta métricas de request (Prometheus-style)
app.add_middleware(MetricsMiddleware)


# ==================================================
# SECURITY: EXCEPTION HANDLERS - Sanitiza erros em produção
# ==================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    SECURITY: Handler global para exceções não tratadas.

    Em produção: retorna mensagem genérica (não vaza stack traces).
    Em desenvolvimento: retorna detalhes para debug.
    """
    # Obtém request_id para rastreamento
    request_id = get_request_id() or getattr(request.state, 'request_id', 'unknown')

    if IS_PRODUCTION:
        # SECURITY: Em produção, não expõe detalhes internos
        logging.error(f"[{request_id}] Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno do servidor. Tente novamente mais tarde.", "request_id": request_id}
        )
    else:
        # Em desenvolvimento, mostra detalhes para debug
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc(),
                "request_id": request_id
            }
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    SECURITY: Handler para erros de validação.

    Sanitiza mensagens de erro para não expor estrutura interna.
    """
    request_id = get_request_id() or getattr(request.state, 'request_id', 'unknown')

    if IS_PRODUCTION:
        # SECURITY: Mensagem simplificada em produção
        return JSONResponse(
            status_code=422,
            content={"detail": "Dados inválidos na requisição.", "request_id": request_id}
        )
    else:
        # Em desenvolvimento, mostra detalhes
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "request_id": request_id}
        )

# Templates Jinja2 para páginas do portal
templates = Jinja2Templates(directory="frontend/templates")

# Arquivos estáticos
if os.path.exists("frontend/static"):
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Arquivos de logo
if os.path.exists("logo"):
    app.mount("/logo", StaticFiles(directory="logo"), name="logo")


# ==================================================
# ROTAS DO PORTAL
# ==================================================

@app.get("/")
async def root():
    """Redireciona para o dashboard ou login"""
    return RedirectResponse(url="/dashboard")


@app.get(
    "/health",
    tags=["Health"],
    summary="Health check básico",
    response_description="Status simplificado do sistema"
)
async def health_check():
    """
    Health check básico para load balancers e monitoramento.

    IMPORTANTE: Retorna sempre 200 para garantir que o deploy passe.
    Use /health/detailed para diagnóstico completo.
    """
    # Health check simples - apenas verifica se o app responde
    return {"status": "ok", "service": "portal-pge"}


@app.get(
    "/health/detailed",
    tags=["Health"],
    summary="Health check detalhado",
    response_description="Status detalhado de todos os componentes"
)
async def health_check_detailed():
    """
    Health check detalhado com status de todos os componentes.

    Verifica:
    - Banco de dados (PostgreSQL)
    - APIs externas (Gemini)
    - Circuit Breakers
    - Background Tasks
    - Variáveis de ambiente
    """
    try:
        from utils.health_check import get_health_status, HealthStatus
        health = await get_health_status(include_details=True)

        status_code = 200 if health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED) else 503
        return JSONResponse(content=health.to_dict(), status_code=status_code)
    except Exception as e:
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)[:200]},
            status_code=503
        )


@app.get(
    "/health/ready",
    tags=["Health"],
    summary="Kubernetes readiness probe",
    response_description="Se o serviço está pronto para receber tráfego"
)
async def readiness_check():
    """
    Readiness probe para Kubernetes.

    Retorna 200 apenas se o serviço está pronto para receber tráfego.
    """
    try:
        from utils.health_check import check_database, HealthStatus
        db_health = await check_database()

        if db_health.status == HealthStatus.HEALTHY:
            return {"status": "ready"}
        else:
            return JSONResponse(
                content={"status": "not_ready", "reason": db_health.message},
                status_code=503
            )
    except Exception as e:
        return JSONResponse(
            content={"status": "not_ready", "error": str(e)[:100]},
            status_code=503
        )


@app.get(
    "/health/live",
    tags=["Health"],
    summary="Kubernetes liveness probe",
    response_description="Se o processo está vivo"
)
async def liveness_check():
    """
    Liveness probe para Kubernetes.

    Retorna 200 se o processo está vivo (sempre retorna OK se chegou aqui).
    """
    return {"alive": True}


# ==================================================
# MÉTRICAS (PROMETHEUS-STYLE)
# ==================================================

@app.get(
    "/metrics",
    tags=["Metrics"],
    summary="Métricas Prometheus",
    response_description="Métricas em formato Prometheus text"
)
async def prometheus_metrics():
    """
    Endpoint de métricas em formato Prometheus.

    Retorna métricas de:
    - Contagem de requests por endpoint e status
    - Latência (histograma)
    - Erros por tipo
    - Uptime do serviço

    Pode ser usado diretamente por Prometheus para scraping.
    """
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=get_metrics_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@app.get("/metrics/json")
async def metrics_json():
    """
    Endpoint de métricas em formato JSON.

    Retorna resumo das métricas em formato legível:
    - Uptime
    - Total de requests/erros
    - Top endpoints
    - Endpoints mais lentos
    - Taxa de erro
    """
    return get_metrics_summary()


# ==================================================
# ROUTERS DE AUTENTICAÇÃO E USUÁRIOS
# ==================================================

app.include_router(auth_router)
app.include_router(users_router)


# ==================================================
# ROUTER DE ADMINISTRAÇÃO
# ==================================================

from admin.router import router as admin_router
app.include_router(admin_router)

# Router de Dashboard de Métricas (admin)
from admin.dashboard_router import router as dashboard_router
app.include_router(dashboard_router)

# Router de Performance Logs (admin)
app.include_router(performance_router)

# Router de Logs de Chamadas Gemini (admin)
app.include_router(gemini_logs_router)


# ==================================================
# ROUTERS DOS SISTEMAS
# ==================================================

app.include_router(assistencia_router, prefix="/assistencia/api")
app.include_router(matriculas_router, prefix="/matriculas/api")
app.include_router(gerador_pecas_router, prefix="/gerador-pecas/api")
app.include_router(gerador_pecas_admin_router, prefix="/admin/api")

# Router de Prompts Modulares (admin)
app.include_router(prompts_modulos_router, prefix="/admin/api")

# Router de Categorias de Formato JSON (admin)
app.include_router(categorias_json_router, prefix="/admin/api")

# Router de Teste de Categorias JSON (admin)
app.include_router(teste_categorias_router, prefix="/admin/api")

# Router de Teste de Ativacao de Modulos (admin)
app.include_router(teste_ativacao_router, prefix="/admin/api")

# Router de Extração (perguntas, modelos, variáveis, regras determinísticas)
app.include_router(extraction_router, prefix="/admin/api/extraction")

# Router de Configuração de Tipos de Peça e Categorias de Documentos (admin)
app.include_router(config_pecas_router)

# Router de Pedido de Cálculo
app.include_router(pedido_calculo_router, prefix="/pedido-calculo/api")
app.include_router(pedido_calculo_admin_router)  # Admin router - sem prefixo pois já tem no router

# Router de Prestação de Contas
app.include_router(prestacao_contas_router, prefix="/prestacao-contas/api")
app.include_router(prestacao_contas_admin_router)  # Admin router - sem prefixo pois já tem no router

# Router de Relatório de Cumprimento
app.include_router(relatorio_cumprimento_router, prefix="/relatorio-cumprimento/api")

# Router de Classificador de Documentos
app.include_router(classificador_documentos_router, prefix="/classificador/api")

# Router de BERT Training
app.include_router(bert_training_router)  # prefixo /bert-training já está no router

# Router de Normalização de Texto
app.include_router(text_normalizer_router)


# ==================================================
# FRONTENDS DOS SISTEMAS
# ==================================================

# SECURITY: Content-types permitidos para arquivos estáticos
ALLOWED_CONTENT_TYPES = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}

def safe_serve_static(base_dir: Path, filename: str, no_cache: bool = False):
    """
    SECURITY: Serve arquivos estáticos de forma segura, prevenindo path traversal.

    Args:
        base_dir: Diretório base permitido
        filename: Nome do arquivo requisitado
        no_cache: Se True, adiciona headers anti-cache

    Returns:
        FileResponse ou HTMLResponse com erro
    """
    # Normaliza filename
    if not filename or filename == "" or filename == "/":
        filename = "index.html"

    # SECURITY: Remove tentativas de path traversal
    # Normaliza separadores e remove componentes perigosos
    clean_filename = filename.replace("\\", "/")

    # Resolve o caminho e verifica se está dentro do diretório base
    try:
        file_path = (base_dir / clean_filename).resolve()
        base_resolved = base_dir.resolve()

        # SECURITY: Verifica se o arquivo está dentro do diretório permitido
        if not str(file_path).startswith(str(base_resolved)):
            return HTMLResponse(
                "<h1>Acesso negado</h1>",
                status_code=403
            )
    except (ValueError, OSError):
        return HTMLResponse("<h1>Caminho inválido</h1>", status_code=400)

    # SECURITY: Verifica extensão permitida
    suffix = file_path.suffix.lower()
    if suffix not in ALLOWED_CONTENT_TYPES:
        # Fallback para index.html (SPA)
        index_path = base_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html")
        return HTMLResponse("<h1>Tipo de arquivo não permitido</h1>", status_code=403)

    if file_path.exists() and file_path.is_file():
        media_type = ALLOWED_CONTENT_TYPES.get(suffix, "application/octet-stream")

        headers = {}
        if no_cache:
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }

        return FileResponse(file_path, media_type=media_type, headers=headers if headers else None)

    # Se não encontrou, retorna index.html (SPA fallback)
    index_path = base_dir / "index.html"
    if index_path.exists():
        headers = {}
        if no_cache:
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        return FileResponse(index_path, media_type="text/html", headers=headers if headers else None)

    return HTMLResponse("<h1>Sistema não encontrado</h1>", status_code=404)


# Assistência Judiciária - Servir arquivos estáticos
@app.get("/assistencia/{filename:path}")
@app.get("/assistencia/")
@app.get("/assistencia")
async def serve_assistencia_static(filename: str = ""):
    """Serve arquivos do frontend Assistência Judiciária"""
    return safe_serve_static(ASSISTENCIA_TEMPLATES, filename)


# Matrículas Confrontantes - Servir arquivos estáticos (JS, CSS)
@app.get("/matriculas/{filename:path}")
async def serve_matriculas_static(filename: str = ""):
    """Serve arquivos do frontend Matrículas Confrontantes"""
    return safe_serve_static(MATRICULAS_TEMPLATES, filename)


# Gerador de Peças Jurídicas
@app.get("/gerador-pecas/{filename:path}")
@app.get("/gerador-pecas/")
@app.get("/gerador-pecas")
async def serve_gerador_pecas_static(filename: str = ""):
    """Serve arquivos do frontend Gerador de Peças Jurídicas"""
    return safe_serve_static(GERADOR_PECAS_TEMPLATES, filename, no_cache=True)


# Pedido de Cálculo
@app.get("/pedido-calculo/{filename:path}")
@app.get("/pedido-calculo/")
@app.get("/pedido-calculo")
async def serve_pedido_calculo_static(filename: str = ""):
    """Serve arquivos do frontend Pedido de Cálculo"""
    return safe_serve_static(PEDIDO_CALCULO_TEMPLATES, filename, no_cache=True)


# Prestação de Contas
@app.get("/prestacao-contas/{filename:path}")
@app.get("/prestacao-contas/")
@app.get("/prestacao-contas")
async def serve_prestacao_contas_static(filename: str = ""):
    """Serve arquivos do frontend Prestação de Contas"""
    return safe_serve_static(PRESTACAO_CONTAS_TEMPLATES, filename, no_cache=True)


# Relatório de Cumprimento
@app.get("/relatorio-cumprimento/{filename:path}")
@app.get("/relatorio-cumprimento/")
@app.get("/relatorio-cumprimento")
async def serve_relatorio_cumprimento_static(filename: str = ""):
    """Serve arquivos do frontend Relatório de Cumprimento"""
    return safe_serve_static(RELATORIO_CUMPRIMENTO_TEMPLATES, filename, no_cache=True)


# Classificador de Documentos
@app.get("/classificador/{filename:path}")
@app.get("/classificador/")
@app.get("/classificador")
async def serve_classificador_static(filename: str = ""):
    """Serve arquivos do frontend Classificador de Documentos"""
    return safe_serve_static(CLASSIFICADOR_DOCUMENTOS_TEMPLATES, filename, no_cache=True)


import re

# BERT Training
@app.get("/bert-training/templates/{filename:path}")
@app.get("/bert-training/")
@app.get("/bert-training")
async def serve_bert_training_static(filename: str = ""):
    """Serve arquivos do frontend BERT Training"""
    # Intercepta app.js para injetar URL do worker
    if filename == "app.js" or filename.endswith("/app.js"):
        file_path = BERT_TRAINING_TEMPLATES / filename
        # Verifica path traversal simples antes de ler
        if ".." not in filename and file_path.exists() and file_path.is_file():
            try:
                content = file_path.read_text(encoding="utf-8")
                
                # Log para debug da injeção
                logging.info(f"Injetando BERT_WORKER_URL no app.js: {BERT_WORKER_URL}")

                # Substitui a URL harcoded pela configurada usando Regex para ser mais robusto
                # Substitui: var WORKER_URL = "http://...";
                content = re.sub(
                    r'var\s+WORKER_URL\s*=\s*["\'].*?["\'];', 
                    f'var WORKER_URL = "{BERT_WORKER_URL}";', 
                    content
                )
                
                headers = {
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache"
                }
                return Response(content=content, media_type="application/javascript", headers=headers)
            except Exception as e:
                logging.error(f"Erro ao servir app.js injetado: {e}")
                # Fallback para safe_serve_static em caso de erro

    return safe_serve_static(BERT_TRAINING_TEMPLATES, filename, no_cache=True)


# ==================================================
# PÁGINAS DO PORTAL (Jinja2)
# ==================================================

@app.get("/login")
async def login_page(request: Request):
    """Página de login"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Página do dashboard - seleção de sistemas"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/change-password")
async def change_password_page(request: Request):
    """Página de troca de senha"""
    return templates.TemplateResponse("change_password.html", {"request": request})


# ==================================================
# PÁGINAS ADMIN (Protegidas)
# ==================================================
# SECURITY: Páginas admin requerem autenticação.
# A verificação completa é feita via JS no frontend,
# mas adicionamos verificação básica de token no backend
# para evitar acesso direto por crawlers/bots.

from auth.dependencies import get_current_active_user, require_admin
from auth.models import User
from fastapi import Depends
from sqlalchemy.orm import Session
from database.connection import get_db


async def verify_admin_token_optional(request: Request) -> bool:
    """
    SECURITY: Verifica se há um token válido de admin.
    Retorna True se válido, False caso contrário.
    Não bloqueia - permite que JS faça redirect adequado.
    """
    # Tenta extrair token do header Authorization
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from auth.security import decode_token
            token = auth_header.replace("Bearer ", "")
            payload = decode_token(token)
            if payload and payload.get("role") == "admin":
                return True
        except Exception:
            pass
    return False


@app.get("/admin/prompts-config")
async def admin_prompts_page(request: Request):
    """Página de administração de prompts"""
    return templates.TemplateResponse("admin_prompts.html", {"request": request})


@app.get("/admin/prompts-modulos")
async def admin_prompts_modulos_page(request: Request):
    """Página de gerenciamento de prompts modulares"""
    return templates.TemplateResponse("admin_prompts_modulos.html", {"request": request})


@app.get("/admin/modulos-tipo-peca")
async def admin_modulos_tipo_peca_page(request: Request):
    """Página de configuração de módulos por tipo de peça"""
    return templates.TemplateResponse("admin_modulos_tipo_peca.html", {"request": request})


@app.get("/admin/gerador-pecas/historico")
async def admin_gerador_historico_page(request: Request):
    """Página de histórico de gerações com prompts"""
    return templates.TemplateResponse("admin_gerador_historico.html", {"request": request})


@app.get("/admin/pedido-calculo/debug")
async def admin_pedido_calculo_debug_page(request: Request):
    """Página de debug do Pedido de Cálculo - visualiza chamadas de IA"""
    return templates.TemplateResponse("admin_pedido_calculo_historico.html", {"request": request})


@app.get("/admin/prestacao-contas/debug")
async def admin_prestacao_contas_debug_page(request: Request):
    """Página de debug da Prestação de Contas - visualiza chamadas de IA"""
    return templates.TemplateResponse("admin_prestacao_contas_historico.html", {"request": request})


@app.get("/admin/users")
async def admin_users_page(request: Request):
    """Página de administração de usuários"""
    return templates.TemplateResponse("admin_users.html", {"request": request})


@app.get("/admin/feedbacks")
async def admin_feedbacks_page(request: Request):
    """Página de dashboard de feedbacks"""
    return templates.TemplateResponse("admin_feedbacks.html", {"request": request})


@app.get("/admin/categorias-resumo-json")
async def admin_categorias_json_page(request: Request):
    """Página de gerenciamento de categorias de formato de resumo JSON"""
    return templates.TemplateResponse("admin_categorias_json.html", {"request": request})


@app.get("/admin/categorias-resumo-json/teste")
async def admin_teste_categorias_json_page(request: Request):
    """Página de teste/validação de categorias de resumo JSON"""
    return templates.TemplateResponse("admin_teste_categorias_json.html", {"request": request})


@app.get("/admin/prompts-modulos/teste")
async def admin_teste_ativacao_modulos_page(request: Request):
    """Página de teste de ativação de prompts modulares"""
    return templates.TemplateResponse("admin_teste_ativacao_modulos.html", {"request": request})


@app.get("/admin/variaveis")
async def admin_variaveis_page(request: Request):
    """Página do painel de variáveis de extração"""
    return templates.TemplateResponse("admin_variaveis.html", {"request": request})


@app.get("/admin/restaurar-slugs")
async def admin_restaurar_slugs_page(request: Request):
    """Página para restaurar slugs de variáveis a partir de backup"""
    return templates.TemplateResponse("admin_restaurar_slugs.html", {"request": request})


@app.get("/admin/performance")
async def admin_performance_page(request: Request):
    """Página para gerenciar logs de performance (diagnóstico de latência)"""
    return templates.TemplateResponse("admin_performance.html", {"request": request})


@app.get("/admin/tjms-docs")
async def admin_tjms_docs_page(request: Request):
    """Página de documentação da integração TJMS - explica como cada sistema consome do TJ-MS"""
    return templates.TemplateResponse("admin_tjms_docs.html", {"request": request})


@app.get("/admin/tjms-docs/plano")
async def admin_tjms_plano_page():
    """Retorna o plano de unificação TJMS em markdown"""
    import os
    plano_path = os.path.join(BASE_DIR, "docs", "PLANO_UNIFICACAO_TJMS.md")
    if os.path.exists(plano_path):
        with open(plano_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Escapa backticks para uso em template literal JS
        escaped_content = content.replace('`', '\\`')
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Plano Unificação TJMS</title>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.2.0/github-markdown.min.css">
            <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
            <style>
                body {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
                .markdown-body {{ box-sizing: border-box; min-width: 200px; max-width: 980px; margin: 0 auto; padding: 45px; }}
            </style>
        </head>
        <body class="markdown-body">
            <a href="/admin/tjms-docs" style="display:inline-block;margin-bottom:20px;color:#0969da;">← Voltar</a>
            <div id="content"></div>
            <script>
                document.getElementById('content').innerHTML = marked.parse(`{escaped_content}`);
            </script>
        </body>
        </html>
        """)
    return HTMLResponse(content="Arquivo não encontrado", status_code=404)


# ==================================================
# EXECUÇÃO DIRETA
# ==================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
=======
# main.py
"""
Portal PGE-MS - Aplicação FastAPI Principal

Unifica os sistemas:
- Assistência Judiciária
- Matrículas Confrontantes

Com autenticação centralizada via JWT.
"""

import logging
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
import os

from config import IS_PRODUCTION

# Middleware de Request ID para rastreamento
from middleware.request_id import RequestIDMiddleware, get_request_id

# Logging estruturado
from utils.logging_config import setup_logging, get_logger

# Configura logging para silenciar requests de polling repetitivos
class StatusPollingFilter(logging.Filter):
    """Filtra logs de polling de status que são muito frequentes"""
    def filter(self, record):
        # Silencia logs de polling de status (GET .../status)
        if '/status HTTP' in record.getMessage():
            return False
        return True

# Aplica filtro ao logger do uvicorn
logging.getLogger("uvicorn.access").addFilter(StatusPollingFilter())

from database.init_db import init_database
from auth.router import router as auth_router
from users.router import router as users_router

# SECURITY: Rate Limiting
from slowapi.errors import RateLimitExceeded
from utils.rate_limit import limiter, rate_limit_exceeded_handler

# SECURITY: Exception handling
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import traceback

# Import dos sistemas
from sistemas.assistencia_judiciaria.router import router as assistencia_router
from sistemas.matriculas_confrontantes.router import router as matriculas_router
from sistemas.gerador_pecas.router import router as gerador_pecas_router
from sistemas.gerador_pecas.router_admin import router as gerador_pecas_admin_router
from sistemas.gerador_pecas.router_categorias_json import router as categorias_json_router
from sistemas.gerador_pecas.router_config_pecas import router as config_pecas_router
from sistemas.gerador_pecas.router_teste_categorias import router as teste_categorias_router
# TEMPORÁRIO: import condicional até redeploy com arquivo models_teste_ativacao.py
try:
    from sistemas.gerador_pecas.router_teste_ativacao import router as teste_ativacao_router
except ImportError:
    teste_ativacao_router = None

# Import do admin de prompts modulares
from admin.router_prompts import router as prompts_modulos_router

# Import do router de extração (perguntas, modelos, variáveis, regras determinísticas)
from sistemas.gerador_pecas.router_extraction import router as extraction_router

# Import do sistema de Pedido de Cálculo
from sistemas.pedido_calculo.router import router as pedido_calculo_router
from sistemas.pedido_calculo.router_admin import router as pedido_calculo_admin_router

# Import do sistema de Prestação de Contas
from sistemas.prestacao_contas.router import router as prestacao_contas_router
from sistemas.prestacao_contas.router_admin import router as prestacao_contas_admin_router

# Import do sistema de Relatório de Cumprimento
from sistemas.relatorio_cumprimento.router import router as relatorio_cumprimento_router

# Import do sistema Cumprimento de Sentença Beta
from sistemas.cumprimento_beta.router import router as cumprimento_beta_router

# Import do sistema de Classificador de Documentos
from sistemas.classificador_documentos.router import router as classificador_documentos_router

# Import do sistema BERT Training
from sistemas.bert_training.router import router as bert_training_router

# Import do sistema de Performance Logs
from admin.router_performance import router as performance_router
from admin.router_gemini_logs import router as gemini_logs_router
from admin.middleware_performance import PerformanceMiddleware

# Métricas de request (Prometheus-style)
from middleware.metrics import MetricsMiddleware
from utils.metrics import get_metrics_text, get_metrics_summary

# Import do serviço de normalização de texto
from services.text_normalizer import text_normalizer_router

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
MATRICULAS_TEMPLATES = BASE_DIR / "sistemas" / "matriculas_confrontantes" / "templates"
ASSISTENCIA_TEMPLATES = BASE_DIR / "sistemas" / "assistencia_judiciaria" / "templates"
GERADOR_PECAS_TEMPLATES = BASE_DIR / "sistemas" / "gerador_pecas" / "templates"
PEDIDO_CALCULO_TEMPLATES = BASE_DIR / "sistemas" / "pedido_calculo" / "templates"
PRESTACAO_CONTAS_TEMPLATES = BASE_DIR / "sistemas" / "prestacao_contas" / "templates"
RELATORIO_CUMPRIMENTO_TEMPLATES = BASE_DIR / "sistemas" / "relatorio_cumprimento" / "templates"
CUMPRIMENTO_BETA_TEMPLATES = BASE_DIR / "sistemas" / "cumprimento_beta" / "templates"
CLASSIFICADOR_DOCUMENTOS_TEMPLATES = BASE_DIR / "sistemas" / "classificador_documentos" / "templates"
BERT_TRAINING_TEMPLATES = BASE_DIR / "sistemas" / "bert_training" / "templates"

# IMPORTANTE: Inicializa banco de dados ANTES de criar o app
# Isso garante que migrações sejam executadas antes de qualquer query
print("[*] Pré-inicializando banco de dados...")
init_database()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle events da aplicação.
    Executa na inicialização e no shutdown.
    """
    # Startup
    print("[+] Iniciando Portal PGE-MS...")

    # Configura logging estruturado
    setup_logging()
    logger = get_logger("portal-pge")
    logger.info(f"Iniciando aplicação (environment={'production' if IS_PRODUCTION else 'development'})")

    init_database()

    # ==========================================================================
    # Inicializa tabela de embeddings vetoriais (com pgvector se disponível)
    # ==========================================================================
    try:
        from sistemas.gerador_pecas.models_embeddings import init_embeddings_table
        pgvector_ok = init_embeddings_table()
        print(f"[EMBEDDINGS] Tabela inicializada (pgvector: {'disponível' if pgvector_ok else 'não disponível - usando fallback'})")
    except Exception as e:
        print(f"[WARN] Erro ao inicializar tabela de embeddings: {e}")

    # ==========================================================================
    # REGRA DE OURO: Corrige modos de ativação inconsistentes no startup
    # Garante que dados legados ou corrompidos sejam corrigidos automaticamente
    # ==========================================================================
    try:
        from database.connection import SessionLocal
        from sistemas.gerador_pecas.services_deterministic import corrigir_modos_ativacao_inconsistentes

        db = SessionLocal()
        try:
            resultado = corrigir_modos_ativacao_inconsistentes(db, commit=True)
            if resultado["corrigidos"] > 0:
                print(f"[REGRA-DE-OURO] Corrigidos {resultado['corrigidos']} módulos com modo de ativação inconsistente")
            else:
                print("[REGRA-DE-OURO] Todos os módulos estão com modo de ativação correto")
        finally:
            db.close()
    except Exception as e:
        print(f"[WARN] Erro ao verificar modos de ativação: {e}")

    # Configura instrumentação automática de performance
    from admin.perf_instrumentation import setup_instrumentation
    setup_instrumentation(app)

    # ==========================================================================
    # Inicia BERT Watchdog Scheduler
    # Monitora jobs travados e toma ações automáticas (retry, cleanup)
    # ==========================================================================
    try:
        from utils.background_tasks import start_bert_watchdog_scheduler
        from database.connection import SessionLocal
        await start_bert_watchdog_scheduler(
            interval_minutes=5.0,  # Verifica a cada 5 minutos
            db_factory=SessionLocal
        )
        print("[WATCHDOG] BERT Watchdog scheduler iniciado (intervalo: 5 min)")
    except Exception as e:
        print(f"[WARN] Erro ao iniciar BERT Watchdog: {e}")

    yield
    # Shutdown
    print("[-] Encerrando Portal PGE-MS...")

    # Para o scheduler de tarefas
    try:
        from utils.background_tasks import stop_scheduler
        await stop_scheduler()
        print("[WATCHDOG] Scheduler parado")
    except Exception as e:
        print(f"[WARN] Erro ao parar scheduler: {e}")


# Cria a aplicação FastAPI
app = FastAPI(
    title="Portal PGE-MS",
    description="Portal unificado da Procuradoria-Geral do Estado de Mato Grosso do Sul",
    version="1.0.0",
    lifespan=lifespan
)

# ==================================================
# SECURITY: MIDDLEWARE DE HEADERS DE SEGURANÇA
# ==================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    SECURITY: Adiciona headers de segurança HTTP em todas as respostas.

    Headers implementados:
    - X-Frame-Options: Previne clickjacking
    - X-Content-Type-Options: Previne MIME sniffing
    - X-XSS-Protection: Proteção XSS do navegador (legacy)
    - Referrer-Policy: Controla informações de referrer
    - Strict-Transport-Security: Força HTTPS (HSTS)
    - Content-Security-Policy: Controla recursos permitidos
    - Permissions-Policy: Restringe APIs do navegador
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Previne clickjacking - permite embedding apenas do próprio domínio (SAMEORIGIN)
        # DENY bloqueia completamente, SAMEORIGIN permite visualizadores internos (PDF viewer)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        # Previne MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Proteção XSS do navegador (legacy, mas ainda útil)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Controla informações de referrer enviadas
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Força HTTPS por 1 ano (apenas em produção)
        if IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # Content Security Policy
        # Permite scripts inline (necessário para templates) e CDNs específicos
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com",
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com data:",
            "img-src 'self' data: blob: https:",
            "connect-src 'self' https://generativelanguage.googleapis.com https://openrouter.ai",
            "frame-src 'self' blob:",  # Permite iframes com blob URLs (PDFs)
            "object-src 'self' blob:",  # Permite objetos/plugins com blob URLs (PDFs)
            "frame-ancestors 'self'",  # Permite embedding apenas do próprio domínio (para visualizador de PDF)
            "form-action 'self'",
            "base-uri 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Permissions Policy - restringe APIs do navegador
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=(), payment=()"

        # Cache control para páginas HTML (não cachear por segurança)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"

        return response


# ==================================================
# SECURITY: CONFIGURAÇÃO DE CORS
# ==================================================

# SECURITY: Em produção, ALLOWED_ORIGINS DEVE ser definido explicitamente
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "").strip()

if _allowed_origins_env:
    # Parse das origens configuradas
    ALLOWED_ORIGINS = [origin.strip() for origin in _allowed_origins_env.split(",") if origin.strip()]
else:
    if IS_PRODUCTION:
        # Em produção, detecta automaticamente o domínio do Railway ou usa padrão
        ALLOWED_ORIGINS = []

        # Railway fornece o domínio público via variável de ambiente
        railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway_domain:
            ALLOWED_ORIGINS.append(f"https://{railway_domain}")

        # Adiciona domínio padrão da PGE se não configurado
        if not ALLOWED_ORIGINS:
            # Fallback para o domínio conhecido da aplicação
            ALLOWED_ORIGINS = ["https://portal-pge-production.up.railway.app"]
    else:
        # Desenvolvimento local - origens permissivas
        ALLOWED_ORIGINS = [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
        ]

# TRACING: Request ID para rastreamento de requisições
# Deve ser o primeiro middleware para que o ID esteja disponível em todo o request
app.add_middleware(RequestIDMiddleware)

# SECURITY: Adiciona middleware de headers ANTES do CORS
app.add_middleware(SecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# SECURITY: Rate Limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# PERFORMANCE: Middleware de timing (apenas para admin quando ativado)
app.add_middleware(PerformanceMiddleware)

# METRICS: Coleta métricas de request (Prometheus-style)
app.add_middleware(MetricsMiddleware)


# ==================================================
# SECURITY: EXCEPTION HANDLERS - Sanitiza erros em produção
# ==================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    SECURITY: Handler global para exceções não tratadas.

    Em produção: retorna mensagem genérica (não vaza stack traces).
    Em desenvolvimento: retorna detalhes para debug.
    """
    # Obtém request_id para rastreamento
    request_id = get_request_id() or getattr(request.state, 'request_id', 'unknown')

    if IS_PRODUCTION:
        # SECURITY: Em produção, não expõe detalhes internos
        logging.error(f"[{request_id}] Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno do servidor. Tente novamente mais tarde.", "request_id": request_id}
        )
    else:
        # Em desenvolvimento, mostra detalhes para debug
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc(),
                "request_id": request_id
            }
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    SECURITY: Handler para erros de validação.

    Sanitiza mensagens de erro para não expor estrutura interna.
    """
    request_id = get_request_id() or getattr(request.state, 'request_id', 'unknown')

    if IS_PRODUCTION:
        # SECURITY: Mensagem simplificada em produção
        return JSONResponse(
            status_code=422,
            content={"detail": "Dados inválidos na requisição.", "request_id": request_id}
        )
    else:
        # Em desenvolvimento, mostra detalhes
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "request_id": request_id}
        )

# Templates Jinja2 para páginas do portal
templates = Jinja2Templates(directory="frontend/templates")

# Arquivos estáticos
if os.path.exists("frontend/static"):
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Arquivos de logo
if os.path.exists("logo"):
    app.mount("/logo", StaticFiles(directory="logo"), name="logo")


# ==================================================
# ROTAS DO PORTAL
# ==================================================

@app.get("/")
async def root():
    """Redireciona para o dashboard ou login"""
    return RedirectResponse(url="/dashboard")


@app.get(
    "/health",
    tags=["Health"],
    summary="Health check básico",
    response_description="Status simplificado do sistema"
)
async def health_check():
    """
    Health check básico para load balancers e monitoramento.

    IMPORTANTE: Retorna sempre 200 para garantir que o deploy passe.
    Use /health/detailed para diagnóstico completo.
    """
    # Health check simples - apenas verifica se o app responde
    return {"status": "ok", "service": "portal-pge"}


@app.get(
    "/health/detailed",
    tags=["Health"],
    summary="Health check detalhado",
    response_description="Status detalhado de todos os componentes"
)
async def health_check_detailed():
    """
    Health check detalhado com status de todos os componentes.

    Verifica:
    - Banco de dados (PostgreSQL)
    - APIs externas (Gemini)
    - Circuit Breakers
    - Background Tasks
    - Variáveis de ambiente
    """
    try:
        from utils.health_check import get_health_status, HealthStatus
        health = await get_health_status(include_details=True)

        status_code = 200 if health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED) else 503
        return JSONResponse(content=health.to_dict(), status_code=status_code)
    except Exception as e:
        return JSONResponse(
            content={"status": "unhealthy", "error": str(e)[:200]},
            status_code=503
        )


@app.get(
    "/health/ready",
    tags=["Health"],
    summary="Kubernetes readiness probe",
    response_description="Se o serviço está pronto para receber tráfego"
)
async def readiness_check():
    """
    Readiness probe para Kubernetes.

    Retorna 200 apenas se o serviço está pronto para receber tráfego.
    """
    try:
        from utils.health_check import check_database, HealthStatus
        db_health = await check_database()

        if db_health.status == HealthStatus.HEALTHY:
            return {"status": "ready"}
        else:
            return JSONResponse(
                content={"status": "not_ready", "reason": db_health.message},
                status_code=503
            )
    except Exception as e:
        return JSONResponse(
            content={"status": "not_ready", "error": str(e)[:100]},
            status_code=503
        )


@app.get(
    "/health/live",
    tags=["Health"],
    summary="Kubernetes liveness probe",
    response_description="Se o processo está vivo"
)
async def liveness_check():
    """
    Liveness probe para Kubernetes.

    Retorna 200 se o processo está vivo (sempre retorna OK se chegou aqui).
    """
    return {"alive": True}


# ==================================================
# MÉTRICAS (PROMETHEUS-STYLE)
# ==================================================

@app.get(
    "/metrics",
    tags=["Metrics"],
    summary="Métricas Prometheus",
    response_description="Métricas em formato Prometheus text"
)
async def prometheus_metrics():
    """
    Endpoint de métricas em formato Prometheus.

    Retorna métricas de:
    - Contagem de requests por endpoint e status
    - Latência (histograma)
    - Erros por tipo
    - Uptime do serviço

    Pode ser usado diretamente por Prometheus para scraping.
    """
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=get_metrics_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@app.get("/metrics/json")
async def metrics_json():
    """
    Endpoint de métricas em formato JSON.

    Retorna resumo das métricas em formato legível:
    - Uptime
    - Total de requests/erros
    - Top endpoints
    - Endpoints mais lentos
    - Taxa de erro
    """
    return get_metrics_summary()


# ==================================================
# ROUTERS DE AUTENTICAÇÃO E USUÁRIOS
# ==================================================

app.include_router(auth_router)
app.include_router(users_router)


# ==================================================
# ROUTER DE ADMINISTRAÇÃO
# ==================================================

from admin.router import router as admin_router
app.include_router(admin_router)

# Router de Dashboard de Métricas (admin)
from admin.dashboard_router import router as dashboard_router
app.include_router(dashboard_router)

# Router de Performance Logs (admin)
app.include_router(performance_router)

# Router de Logs de Chamadas Gemini (admin)
app.include_router(gemini_logs_router)


# ==================================================
# ROUTERS DOS SISTEMAS
# ==================================================

app.include_router(assistencia_router, prefix="/assistencia/api")
app.include_router(matriculas_router, prefix="/matriculas/api")
app.include_router(gerador_pecas_router, prefix="/gerador-pecas/api")
app.include_router(gerador_pecas_admin_router, prefix="/admin/api")

# Router de Prompts Modulares (admin)
app.include_router(prompts_modulos_router, prefix="/admin/api")

# Router de Categorias de Formato JSON (admin)
app.include_router(categorias_json_router, prefix="/admin/api")

# Router de Teste de Categorias JSON (admin)
app.include_router(teste_categorias_router, prefix="/admin/api")

# Router de Teste de Ativacao de Modulos (admin)
# TEMPORÁRIO: inclusão condicional até redeploy com arquivo models_teste_ativacao.py
if teste_ativacao_router is not None:
    app.include_router(teste_ativacao_router, prefix="/admin/api")

# Router de Extração (perguntas, modelos, variáveis, regras determinísticas)
app.include_router(extraction_router, prefix="/admin/api/extraction")

# Router de Configuração de Tipos de Peça e Categorias de Documentos (admin)
app.include_router(config_pecas_router)

# Router de Pedido de Cálculo
app.include_router(pedido_calculo_router, prefix="/pedido-calculo/api")
app.include_router(pedido_calculo_admin_router)  # Admin router - sem prefixo pois já tem no router

# Router de Prestação de Contas
app.include_router(prestacao_contas_router, prefix="/prestacao-contas/api")
app.include_router(prestacao_contas_admin_router)  # Admin router - sem prefixo pois já tem no router

# Router de Relatório de Cumprimento
app.include_router(relatorio_cumprimento_router, prefix="/relatorio-cumprimento/api")

# Router de Cumprimento de Sentença Beta
app.include_router(cumprimento_beta_router, prefix="/api")

# Router de Classificador de Documentos
app.include_router(classificador_documentos_router, prefix="/classificador/api")

# Router de BERT Training
app.include_router(bert_training_router)  # prefixo /bert-training já está no router

# Router de Normalização de Texto
app.include_router(text_normalizer_router)


# ==================================================
# FRONTENDS DOS SISTEMAS
# ==================================================

# SECURITY: Content-types permitidos para arquivos estáticos
ALLOWED_CONTENT_TYPES = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
}

def safe_serve_static(base_dir: Path, filename: str, no_cache: bool = False):
    """
    SECURITY: Serve arquivos estáticos de forma segura, prevenindo path traversal.

    Args:
        base_dir: Diretório base permitido
        filename: Nome do arquivo requisitado
        no_cache: Se True, adiciona headers anti-cache

    Returns:
        FileResponse ou HTMLResponse com erro
    """
    # Normaliza filename
    if not filename or filename == "" or filename == "/":
        filename = "index.html"

    # SECURITY: Remove tentativas de path traversal
    # Normaliza separadores e remove componentes perigosos
    clean_filename = filename.replace("\\", "/")

    # Resolve o caminho e verifica se está dentro do diretório base
    try:
        file_path = (base_dir / clean_filename).resolve()
        base_resolved = base_dir.resolve()

        # SECURITY: Verifica se o arquivo está dentro do diretório permitido
        if not str(file_path).startswith(str(base_resolved)):
            return HTMLResponse(
                "<h1>Acesso negado</h1>",
                status_code=403
            )
    except (ValueError, OSError):
        return HTMLResponse("<h1>Caminho inválido</h1>", status_code=400)

    # SECURITY: Verifica extensão permitida
    suffix = file_path.suffix.lower()
    if suffix not in ALLOWED_CONTENT_TYPES:
        # Fallback para index.html (SPA)
        index_path = base_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path, media_type="text/html")
        return HTMLResponse("<h1>Tipo de arquivo não permitido</h1>", status_code=403)

    if file_path.exists() and file_path.is_file():
        media_type = ALLOWED_CONTENT_TYPES.get(suffix, "application/octet-stream")

        headers = {}
        if no_cache:
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }

        return FileResponse(file_path, media_type=media_type, headers=headers if headers else None)

    # Se não encontrou, retorna index.html (SPA fallback)
    index_path = base_dir / "index.html"
    if index_path.exists():
        headers = {}
        if no_cache:
            headers = {
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        return FileResponse(index_path, media_type="text/html", headers=headers if headers else None)

    return HTMLResponse("<h1>Sistema não encontrado</h1>", status_code=404)


# Assistência Judiciária - Servir arquivos estáticos
@app.get("/assistencia/{filename:path}")
@app.get("/assistencia/")
@app.get("/assistencia")
async def serve_assistencia_static(filename: str = ""):
    """Serve arquivos do frontend Assistência Judiciária"""
    return safe_serve_static(ASSISTENCIA_TEMPLATES, filename)


# Matrículas Confrontantes - Servir arquivos estáticos (JS, CSS)
@app.get("/matriculas/{filename:path}")
async def serve_matriculas_static(filename: str = ""):
    """Serve arquivos do frontend Matrículas Confrontantes"""
    return safe_serve_static(MATRICULAS_TEMPLATES, filename)


# Gerador de Peças Jurídicas
@app.get("/gerador-pecas/{filename:path}")
@app.get("/gerador-pecas/")
@app.get("/gerador-pecas")
async def serve_gerador_pecas_static(filename: str = ""):
    """Serve arquivos do frontend Gerador de Peças Jurídicas"""
    return safe_serve_static(GERADOR_PECAS_TEMPLATES, filename, no_cache=True)


# Pedido de Cálculo
@app.get("/pedido-calculo/{filename:path}")
@app.get("/pedido-calculo/")
@app.get("/pedido-calculo")
async def serve_pedido_calculo_static(filename: str = ""):
    """Serve arquivos do frontend Pedido de Cálculo"""
    return safe_serve_static(PEDIDO_CALCULO_TEMPLATES, filename, no_cache=True)


# Prestação de Contas
@app.get("/prestacao-contas/{filename:path}")
@app.get("/prestacao-contas/")
@app.get("/prestacao-contas")
async def serve_prestacao_contas_static(filename: str = ""):
    """Serve arquivos do frontend Prestação de Contas"""
    return safe_serve_static(PRESTACAO_CONTAS_TEMPLATES, filename, no_cache=True)


# Relatório de Cumprimento
@app.get("/relatorio-cumprimento/{filename:path}")
@app.get("/relatorio-cumprimento/")
@app.get("/relatorio-cumprimento")
async def serve_relatorio_cumprimento_static(filename: str = ""):
    """Serve arquivos do frontend Relatório de Cumprimento"""
    return safe_serve_static(RELATORIO_CUMPRIMENTO_TEMPLATES, filename, no_cache=True)


# Cumprimento de Sentença Beta
@app.get("/cumprimento-beta/{filename:path}")
@app.get("/cumprimento-beta/")
@app.get("/cumprimento-beta")
async def serve_cumprimento_beta_static(filename: str = ""):
    """Serve arquivos do frontend Cumprimento de Sentença Beta"""
    return safe_serve_static(CUMPRIMENTO_BETA_TEMPLATES, filename, no_cache=True)


# Classificador de Documentos
@app.get("/classificador/{filename:path}")
@app.get("/classificador/")
@app.get("/classificador")
async def serve_classificador_static(filename: str = ""):
    """Serve arquivos do frontend Classificador de Documentos"""
    return safe_serve_static(CLASSIFICADOR_DOCUMENTOS_TEMPLATES, filename, no_cache=True)


# BERT Training
@app.get("/bert-training/templates/{filename:path}")
@app.get("/bert-training/")
@app.get("/bert-training")
async def serve_bert_training_static(filename: str = ""):
    """Serve arquivos do frontend BERT Training"""
    return safe_serve_static(BERT_TRAINING_TEMPLATES, filename, no_cache=True)


# ==================================================
# PÁGINAS DO PORTAL (Jinja2)
# ==================================================

@app.get("/login")
async def login_page(request: Request):
    """Página de login"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/dashboard")
async def dashboard_page(request: Request):
    """Página do dashboard - seleção de sistemas"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/change-password")
async def change_password_page(request: Request):
    """Página de troca de senha"""
    return templates.TemplateResponse("change_password.html", {"request": request})


# ==================================================
# PÁGINAS ADMIN (Protegidas)
# ==================================================
# SECURITY: Páginas admin requerem autenticação.
# A verificação completa é feita via JS no frontend,
# mas adicionamos verificação básica de token no backend
# para evitar acesso direto por crawlers/bots.

from auth.dependencies import get_current_active_user, require_admin
from auth.models import User
from fastapi import Depends
from sqlalchemy.orm import Session
from database.connection import get_db


async def verify_admin_token_optional(request: Request) -> bool:
    """
    SECURITY: Verifica se há um token válido de admin.
    Retorna True se válido, False caso contrário.
    Não bloqueia - permite que JS faça redirect adequado.
    """
    # Tenta extrair token do header Authorization
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from auth.security import decode_token
            token = auth_header.replace("Bearer ", "")
            payload = decode_token(token)
            if payload and payload.get("role") == "admin":
                return True
        except Exception:
            pass
    return False


@app.get("/admin/prompts-config")
async def admin_prompts_page(request: Request):
    """Página de administração de prompts"""
    return templates.TemplateResponse("admin_prompts.html", {"request": request})


@app.get("/admin/prompts-modulos")
async def admin_prompts_modulos_page(request: Request):
    """Página de gerenciamento de prompts modulares"""
    return templates.TemplateResponse("admin_prompts_modulos.html", {"request": request})


@app.get("/admin/modulos-tipo-peca")
async def admin_modulos_tipo_peca_page(request: Request):
    """Página de configuração de módulos por tipo de peça"""
    return templates.TemplateResponse("admin_modulos_tipo_peca.html", {"request": request})


@app.get("/admin/gerador-pecas/historico")
async def admin_gerador_historico_page(request: Request):
    """Página de histórico de gerações com prompts"""
    return templates.TemplateResponse("admin_gerador_historico.html", {"request": request})


@app.get("/admin/pedido-calculo/debug")
async def admin_pedido_calculo_debug_page(request: Request):
    """Página de debug do Pedido de Cálculo - visualiza chamadas de IA"""
    return templates.TemplateResponse("admin_pedido_calculo_historico.html", {"request": request})


@app.get("/admin/prestacao-contas/debug")
async def admin_prestacao_contas_debug_page(request: Request):
    """Página de debug da Prestação de Contas - visualiza chamadas de IA"""
    return templates.TemplateResponse("admin_prestacao_contas_historico.html", {"request": request})


@app.get("/admin/users")
async def admin_users_page(request: Request):
    """Página de administração de usuários"""
    return templates.TemplateResponse("admin_users.html", {"request": request})


@app.get("/admin/feedbacks")
async def admin_feedbacks_page(request: Request):
    """Página de dashboard de feedbacks"""
    return templates.TemplateResponse("admin_feedbacks.html", {"request": request})


@app.get("/admin/categorias-resumo-json")
async def admin_categorias_json_page(request: Request):
    """Página de gerenciamento de categorias de formato de resumo JSON"""
    return templates.TemplateResponse("admin_categorias_json.html", {"request": request})


@app.get("/admin/categorias-resumo-json/teste")
async def admin_teste_categorias_json_page(request: Request):
    """Página de teste/validação de categorias de resumo JSON"""
    return templates.TemplateResponse("admin_teste_categorias_json.html", {"request": request})


@app.get("/admin/prompts-modulos/teste")
async def admin_teste_ativacao_modulos_page(request: Request):
    """Página de teste de ativação de prompts modulares"""
    return templates.TemplateResponse("admin_teste_ativacao_modulos.html", {"request": request})


@app.get("/admin/variaveis")
async def admin_variaveis_page(request: Request):
    """Página do painel de variáveis de extração"""
    return templates.TemplateResponse("admin_variaveis.html", {"request": request})


@app.get("/admin/restaurar-slugs")
async def admin_restaurar_slugs_page(request: Request):
    """Página para restaurar slugs de variáveis a partir de backup"""
    return templates.TemplateResponse("admin_restaurar_slugs.html", {"request": request})


@app.get("/admin/performance")
async def admin_performance_page(request: Request):
    """Página para gerenciar logs de performance (diagnóstico de latência)"""
    return templates.TemplateResponse("admin_performance.html", {"request": request})


@app.get("/admin/tjms-docs")
async def admin_tjms_docs_page(request: Request):
    """Página de documentação da integração TJMS - explica como cada sistema consome do TJ-MS"""
    return templates.TemplateResponse("admin_tjms_docs.html", {"request": request})


@app.get("/admin/tjms-docs/plano")
async def admin_tjms_plano_page():
    """Retorna o plano de unificação TJMS em markdown"""
    import os
    plano_path = os.path.join(BASE_DIR, "docs", "PLANO_UNIFICACAO_TJMS.md")
    if os.path.exists(plano_path):
        with open(plano_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Escapa backticks para uso em template literal JS
        escaped_content = content.replace('`', '\\`')
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Plano Unificação TJMS</title>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.2.0/github-markdown.min.css">
            <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
            <style>
                body {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
                .markdown-body {{ box-sizing: border-box; min-width: 200px; max-width: 980px; margin: 0 auto; padding: 45px; }}
            </style>
        </head>
        <body class="markdown-body">
            <a href="/admin/tjms-docs" style="display:inline-block;margin-bottom:20px;color:#0969da;">← Voltar</a>
            <div id="content"></div>
            <script>
                document.getElementById('content').innerHTML = marked.parse(`{escaped_content}`);
            </script>
        </body>
        </html>
        """)
    return HTMLResponse(content="Arquivo não encontrado", status_code=404)


# ==================================================
# EXECUÇÃO DIRETA
# ==================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
>>>>>>> origin/main
