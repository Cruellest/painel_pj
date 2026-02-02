# config.py
# -*- coding: utf-8 -*-
"""
Configurações centralizadas do Portal PGE-MS
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis de ambiente (apenas se existir .env - não necessário no Railway)
load_dotenv()

# ==================================================
# CONFIGURAÇÕES DO BANCO DE DADOS
# ==================================================
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "ERRO FATAL: DATABASE_URL não definida! "
        "Configure a variável de ambiente DATABASE_URL com a URL do PostgreSQL. "
        "Exemplo: postgresql://user:password@localhost:5432/portal_pge"
    )

# Railway usa postgres:// mas SQLAlchemy precisa de postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Valida que é PostgreSQL
if not DATABASE_URL.startswith("postgresql://"):
    raise RuntimeError(
        f"ERRO FATAL: DATABASE_URL deve ser PostgreSQL! "
        f"URL atual começa com: {DATABASE_URL[:20]}... "
        f"Use o formato: postgresql://user:password@host:port/database"
    )

# ==================================================
# CONFIGURAÇÕES DE AUTENTICAÇÃO JWT
# ==================================================

# SECURITY: Detecta ambiente de produção
IS_PRODUCTION = os.getenv("RAILWAY_ENVIRONMENT") == "production" or os.getenv("ENV") == "production"

# SECURITY: SECRET_KEY é OBRIGATÓRIA em produção
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError(
            "ERRO FATAL: SECRET_KEY não definida em ambiente de produção! "
            "Defina a variável de ambiente SECRET_KEY com um valor seguro. "
            "Gere com: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    import warnings
    warnings.warn(
        "SECRET_KEY não definida! Usando chave temporária APENAS para desenvolvimento local. "
        "NUNCA use em produção!",
        RuntimeWarning
    )
    SECRET_KEY = "DEV-ONLY-INSECURE-KEY-" + "x" * 32

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 horas

# SECURITY: Credenciais do admin inicial
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    if IS_PRODUCTION:
        raise RuntimeError(
            "ERRO FATAL: ADMIN_PASSWORD não definida em ambiente de produção! "
            "Defina a variável de ambiente ADMIN_PASSWORD com uma senha forte."
        )
    import warnings
    warnings.warn(
        "ADMIN_PASSWORD não definida! Usando senha padrão APENAS para desenvolvimento local.",
        RuntimeWarning
    )
    ADMIN_PASSWORD = "admin"

# SECURITY: Senha padrão para novos usuários (devem trocar no primeiro login)
DEFAULT_USER_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "mudar123")

# ==================================================
# CONFIGURAÇÕES DO TJ-MS (Assistência Judiciária)
# ==================================================
TJ_WSDL_URL = os.getenv("TJ_WSDL_URL", "https://proxytjms.fly.dev")
TJ_WS_USER = os.getenv("TJ_WS_USER", "")
TJ_WS_PASS = os.getenv("TJ_WS_PASS", "")
if not TJ_WS_USER or not TJ_WS_PASS:
    if IS_PRODUCTION:
        raise RuntimeError(
            "ERRO FATAL: TJ_WS_USER e TJ_WS_PASS não definidas em ambiente de produção! "
            "Defina as variáveis de ambiente com as credenciais do webservice TJ-MS."
        )
    import warnings
    warnings.warn(
        "TJ_WS_USER/TJ_WS_PASS não definidas! Integração com TJ-MS estará indisponível.",
        RuntimeWarning
    )

# ==================================================
# CONFIGURAÇÕES DO GOOGLE GEMINI (IA)
# ==================================================
GEMINI_API_KEY = os.getenv("GEMINI_KEY", "")
if not GEMINI_API_KEY:
    if IS_PRODUCTION:
        raise RuntimeError(
            "ERRO FATAL: GEMINI_KEY não definida em ambiente de produção! "
            "Defina a variável de ambiente GEMINI_KEY com sua API key do Google Gemini."
        )
    import warnings
    warnings.warn(
        "GEMINI_KEY não definida! Funcionalidades de IA estarão indisponíveis.",
        RuntimeWarning
    )

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

# ==================================================
# CONFIGURAÇÕES DO OPENROUTER (IA - Legado)
# ==================================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3-flash-preview")
FULL_REPORT_MODEL = os.getenv("FULL_REPORT_MODEL", "google/gemini-3-flash-preview")

# ==================================================
# CONFIGURAÇÕES DE ARQUIVOS
# ==================================================
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "sistemas" / "matriculas_confrontantes" / "uploads"
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif", "webp"}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB

# ==================================================
# OUTRAS CONFIGURAÇÕES
# ==================================================
STRICT_CNJ_CHECK = False

# Classes de Cumprimento (Assistência Judiciária)
CLASSES_CUMPRIMENTO = {
    "155", "156", "12231", "15430", "12078", "15215", "15160",
    "12246", "10980", "157", "15161", "10981", "229"
}

# Namespaces XML (TJ-MS)
NS = {
    "soap": "http://schemas.xmlsoap.org/soap/envelope/",
    "ns2": "http://www.cnj.jus.br/intercomunicacao-2.2.2",
}
