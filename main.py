# main.py
"""
Portal PGE-MS - Aplicação FastAPI Principal

Unifica os sistemas:
- Assistência Judiciária
- Matrículas Confrontantes

Com autenticação centralizada via JWT.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import os

from database.init_db import init_database
from auth.router import router as auth_router
from users.router import router as users_router

# Import dos sistemas
from sistemas.assistencia_judiciaria.router import router as assistencia_router
from sistemas.matriculas_confrontantes.router import router as matriculas_router

# Diretórios base
BASE_DIR = Path(__file__).resolve().parent
MATRICULAS_TEMPLATES = BASE_DIR / "sistemas" / "matriculas_confrontantes" / "templates"
ASSISTENCIA_TEMPLATES = BASE_DIR / "sistemas" / "assistencia_judiciaria" / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle events da aplicação.
    Executa na inicialização e no shutdown.
    """
    # Startup
    print("🚀 Iniciando Portal PGE-MS...")
    init_database()
    yield
    # Shutdown
    print("👋 Encerrando Portal PGE-MS...")


# Cria a aplicação FastAPI
app = FastAPI(
    title="Portal PGE-MS",
    description="Portal unificado da Procuradoria-Geral do Estado de Mato Grosso do Sul",
    version="1.0.0",
    lifespan=lifespan
)

# Configuração de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, Railway define automaticamente
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


# ==================================================
# FRONTENDS DOS SISTEMAS
# ==================================================

# Assistência Judiciária - Servir arquivos estáticos
@app.get("/assistencia/{filename:path}")
@app.get("/assistencia/")
@app.get("/assistencia")
async def serve_assistencia_static(filename: str = ""):
    """Serve arquivos do frontend Assistência Judiciária"""
    if not filename or filename == "" or filename == "/":
        filename = "index.html"
    
    file_path = ASSISTENCIA_TEMPLATES / filename
    
    if file_path.exists() and file_path.is_file():
        suffix = file_path.suffix.lower()
        content_types = {
            ".html": "text/html",
            ".js": "application/javascript",
            ".css": "text/css",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
        }
        media_type = content_types.get(suffix, "application/octet-stream")
        return FileResponse(file_path, media_type=media_type)
    
    # Se não encontrou, retorna index.html (SPA fallback)
    index_path = ASSISTENCIA_TEMPLATES / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    
    return HTMLResponse("<h1>Sistema não encontrado</h1>", status_code=404)


# Matrículas Confrontantes - Servir arquivos estáticos (JS, CSS)
@app.get("/matriculas/{filename:path}")
async def serve_matriculas_static(filename: str):
    """Serve arquivos do frontend Matrículas Confrontantes"""
    if not filename or filename == "" or filename == "/":
        filename = "index.html"
    
    file_path = MATRICULAS_TEMPLATES / filename
    
    if file_path.exists() and file_path.is_file():
        # Determina content-type
        suffix = file_path.suffix.lower()
        content_types = {
            ".html": "text/html",
            ".js": "application/javascript",
            ".css": "text/css",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".svg": "image/svg+xml",
        }
        media_type = content_types.get(suffix, "application/octet-stream")
        return FileResponse(file_path, media_type=media_type)
    
    # Se não encontrou, retorna index.html (SPA fallback)
    index_path = MATRICULAS_TEMPLATES / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    
    return HTMLResponse("<h1>Sistema não encontrado</h1>", status_code=404)


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


@app.get("/admin/prompts-config")
async def admin_prompts_page(request: Request):
    """Página de administração de prompts (requer autenticação via JS)"""
    return templates.TemplateResponse("admin_prompts.html", {"request": request})


@app.get("/admin/users")
async def admin_users_page(request: Request):
    """Página de administração de usuários (requer autenticação via JS)"""
    return templates.TemplateResponse("admin_users.html", {"request": request})


@app.get("/admin/feedbacks")
async def admin_feedbacks_page(request: Request):
    """Página de dashboard de feedbacks (requer autenticação via JS)"""
    return templates.TemplateResponse("admin_feedbacks.html", {"request": request})


# ==================================================
# EXECUÇÃO DIRETA
# ==================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
