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
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./portal.db")

# Railway usa postgres:// mas SQLAlchemy precisa de postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# ==================================================
# CONFIGURAÇÕES DE AUTENTICAÇÃO JWT
# ==================================================
# ATENÇÃO: Em produção, SEMPRE defina SECRET_KEY via variável de ambiente
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    import warnings
    warnings.warn("SECRET_KEY não definida! Usando chave temporária. DEFINA EM PRODUÇÃO!", RuntimeWarning)
    SECRET_KEY = "INSECURE-DEV-KEY-CHANGE-IN-PRODUCTION"

ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 horas

# Credenciais do admin inicial (DEVEM ser definidas via variáveis de ambiente em produção)
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
if not ADMIN_PASSWORD:
    import warnings
    warnings.warn("ADMIN_PASSWORD não definida! Usando senha padrão insegura.", RuntimeWarning)
    ADMIN_PASSWORD = "admin"

DEFAULT_USER_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "mudar123")  # Senha padrão para novos usuários

# ==================================================
# CONFIGURAÇÕES DO TJ-MS (Assistência Judiciária)
# ==================================================
TJ_WSDL_URL = os.getenv("TJ_WSDL_URL", "https://proxytjms.fly.dev")
# ATENÇÃO: Credenciais DEVEM ser definidas via variáveis de ambiente
TJ_WS_USER = os.getenv("TJ_WS_USER", "")
TJ_WS_PASS = os.getenv("TJ_WS_PASS", "")

# ==================================================
# CONFIGURAÇÕES DO OPENROUTER (IA)
# ==================================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
FULL_REPORT_MODEL = os.getenv("FULL_REPORT_MODEL", "google/gemini-2.5-flash")

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
