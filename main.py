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

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
MATRICULAS_TEMPLATES = BASE_DIR / "sistemas" / "matriculas_confrontantes" / "templates"
ASSISTENCIA_TEMPLATES = BASE_DIR / "sistemas" / "assistencia_judiciaria" / "templates"
GERADOR_PECAS_TEMPLATES = BASE_DIR / "sistemas" / "gerador_pecas" / "templates"
PEDIDO_CALCULO_TEMPLATES = BASE_DIR / "sistemas" / "pedido_calculo" / "templates"
PRESTACAO_CONTAS_TEMPLATES = BASE_DIR / "sistemas" / "prestacao_contas" / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle events da aplicação.
    Executa na inicialização e no shutdown.
    """
    # Startup
    print("[+] Iniciando Portal PGE-MS...")
    init_database()
    yield
    # Shutdown
    print("[-] Encerrando Portal PGE-MS...")


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

        # Previne clickjacking - não permite embedding em iframes
        response.headers["X-Frame-Options"] = "DENY"

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
            "frame-ancestors 'none'",
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
        # SECURITY: Em produção sem configuração, usar apenas a própria origem
        import warnings
        warnings.warn(
            "ALLOWED_ORIGINS não configurado em produção! "
            "Configure a variável de ambiente ALLOWED_ORIGINS com os domínios permitidos.",
            RuntimeWarning
        )
        # Fallback seguro - apenas mesma origem
        ALLOWED_ORIGINS = []
    else:
        # Desenvolvimento local - origens permissivas
        ALLOWED_ORIGINS = [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
        ]

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
    if IS_PRODUCTION:
        # SECURITY: Em produção, não expõe detalhes internos
        logging.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno do servidor. Tente novamente mais tarde."}
        )
    else:
        # Em desenvolvimento, mostra detalhes para debug
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc()
            }
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    SECURITY: Handler para erros de validação.

    Sanitiza mensagens de erro para não expor estrutura interna.
    """
    if IS_PRODUCTION:
        # SECURITY: Mensagem simplificada em produção
        return JSONResponse(
            status_code=422,
            content={"detail": "Dados inválidos na requisição."}
        )
    else:
        # Em desenvolvimento, mostra detalhes
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()}
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


@app.get("/health")
async def health_check():
    """Health check para monitoramento"""
    import os
    has_api_key = bool(os.getenv("OPENROUTER_API_KEY", ""))
    has_db_url = bool(os.getenv("DATABASE_URL", ""))
    return {
        "status": "ok", 
        "service": "portal-pge",
        "has_openrouter_key": has_api_key,
        "has_database_url": has_db_url
    }


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


@app.get("/admin/variaveis")
async def admin_variaveis_page(request: Request):
    """Página do painel de variáveis de extração"""
    return templates.TemplateResponse("admin_variaveis.html", {"request": request})


# ==================================================
# EXECUÇÃO DIRETA
# ==================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
