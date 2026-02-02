# sistemas/matriculas_confrontantes/services.py
"""
Serviços de análise com IA para Matrículas Confrontantes

Este módulo encapsula a lógica de análise visual que estava no main.py original.
Importa as funções de análise do módulo services_ia.py
"""

import os
import json
import base64
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

from config import (
    OPENROUTER_ENDPOINT, 
    DEFAULT_MODEL, FULL_REPORT_MODEL,
    UPLOAD_FOLDER, ALLOWED_EXTENSIONS
)


# Versão do sistema
APP_VERSION = "1.0.0"


def allowed_file(filename: str) -> bool:
    """Verifica se o arquivo é permitido"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_type(filename: str) -> str:
    """Retorna o tipo do arquivo"""
    ext = filename.rsplit(".", 1)[1].lower() if "." in filename else ""
    if ext == "pdf":
        return "pdf"
    if ext in {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "tif", "webp"}:
        return "image"
    return "unknown"


def get_file_size(filepath: Path) -> str:
    """Retorna o tamanho formatado do arquivo"""
    try:
        size = filepath.stat().st_size
    except OSError:
        return "0 B"

    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def get_openrouter_api_key() -> str:
    """Busca a API key dinamicamente do ambiente."""
    # Tenta do ambiente
    return os.getenv("OPENROUTER_API_KEY", "")


def load_api_key() -> str:
    """Carrega a API Key do ambiente"""
    return get_openrouter_api_key()


def save_api_key(api_key: str) -> bool:
    """
    OBSOLETO: Salvar API Key em arquivo é inseguro.
    Esta função agora apenas retorna False para indicar que a operação não é suportada.
    Configure a variável de ambiente OPENROUTER_API_KEY.
    """
    print("⚠️ Tentativa de salvar API Key em arquivo ignorada por segurança.")
    return False


def result_to_dict(result) -> dict:
    """Converte resultado de análise para dicionário serializável"""
    if not result:
        return {}

    if isinstance(result, dict):
        return result

    try:
        # Converte dataclass para dict
        if hasattr(result, '__dataclass_fields__'):
            return asdict(result)
        
        # Se tem atributos, converte manualmente
        result_dict = {}
        for attr in ['arquivo', 'matricula_principal', 'matriculas_confrontantes',
                     'lotes_confrontantes', 'matriculas_nao_confrontantes',
                     'lotes_sem_matricula', 'confrontacao_completa',
                     'proprietarios_identificados', 'confidence', 'reasoning',
                     'matriculas_encontradas', 'resumo_analise']:
            if hasattr(result, attr):
                value = getattr(result, attr)
                if hasattr(value, '__dataclass_fields__'):
                    result_dict[attr] = asdict(value)
                elif isinstance(value, list):
                    result_dict[attr] = [
                        asdict(item) if hasattr(item, '__dataclass_fields__') else item 
                        for item in value
                    ]
                else:
                    result_dict[attr] = value
        
        return result_dict
    except Exception as e:
        print(f"Erro ao converter resultado: {e}")
        return {}
