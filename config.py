# config.py
# -*- coding: utf-8 -*-
"""
Configurações centralizadas do Portal PGE-MS
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# ==================================================
# CONFIGURAÇÕES DO BANCO DE DADOS
# ==================================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./portal.db")

# ==================================================
# CONFIGURAÇÕES DE AUTENTICAÇÃO JWT
# ==================================================
SECRET_KEY = os.getenv("SECRET_KEY", "pge-ms-secret-key-change-in-production-2024")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 horas

# Credenciais do admin inicial
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
DEFAULT_USER_PASSWORD = "senha"  # Senha padrão para novos usuários

# ==================================================
# CONFIGURAÇÕES DO TJ-MS (Assistência Judiciária)
# ==================================================
TJ_WSDL_URL = os.getenv("TJ_WSDL_URL", "https://esaj.tjms.jus.br/mniws/servico-intercomunicacao-2.2.2/intercomunicacao?wsdl")
TJ_WS_USER = os.getenv("TJ_WS_USER", "PGEMS")
TJ_WS_PASS = os.getenv("TJ_WS_PASS", "SAJ03PGEMS")

# ==================================================
# CONFIGURAÇÕES DO OPENROUTER (IA)
# ==================================================
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-3-pro-preview")
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
