# utils/security.py
# -*- coding: utf-8 -*-
"""
Utilitários de segurança do Portal PGE-MS

Este módulo fornece funções seguras para operações potencialmente perigosas,
como parsing de XML, manipulação de arquivos, etc.

SECURITY: Todas as funções neste módulo são projetadas para mitigar
vulnerabilidades comuns como XXE, Path Traversal, Injection, etc.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, Union
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# ==================================================
# XML PARSING SEGURO
# ==================================================

def safe_parse_xml(xml_text: str) -> ET.Element:
    """
    SECURITY: Parse XML de forma segura, mitigando ataques XXE.

    Esta função:
    1. Tenta usar defusedxml se disponível (máxima proteção)
    2. Fallback para xml.etree.ElementTree padrão do Python 3
       (tem proteções básicas contra XXE)
    3. Sanitiza o XML antes do parsing

    Args:
        xml_text: String XML para parsear

    Returns:
        Element root do XML parseado

    Raises:
        ET.ParseError: Se o XML for inválido
        ValueError: Se o XML contiver padrões maliciosos detectados
    """
    # SECURITY: Verifica padrões maliciosos conhecidos ANTES do parsing
    _check_xml_for_malicious_patterns(xml_text)

    # Tenta usar defusedxml para máxima proteção
    try:
        import defusedxml.ElementTree as DefusedET
        return DefusedET.fromstring(xml_text)
    except ImportError:
        # defusedxml não instalado, usa ET padrão com sanitização
        logger.debug("defusedxml não disponível, usando xml.etree.ElementTree padrão")
        pass

    # Fallback: xml.etree.ElementTree do Python 3
    # Python 3.x tem proteções básicas contra XXE por padrão
    return ET.fromstring(xml_text)


def _check_xml_for_malicious_patterns(xml_text: str) -> None:
    """
    SECURITY: Verifica padrões maliciosos conhecidos em XML.

    Detecta tentativas de:
    - XXE (XML External Entity)
    - Billion Laughs (expansão exponencial de entidades)
    - DTD externos

    Args:
        xml_text: String XML para verificar

    Raises:
        ValueError: Se padrões maliciosos forem detectados
    """
    # Normaliza para análise (case-insensitive)
    xml_lower = xml_text.lower()

    # SECURITY: Bloqueia ENTITY declarations que podem causar XXE
    xxe_patterns = [
        r'<!entity\s+[^>]*system\s*["\']',  # ENTITY com SYSTEM
        r'<!entity\s+[^>]*public\s*["\']',  # ENTITY com PUBLIC
        r'<!entity\s+%',                     # Parameter entities
        r'file://',                          # File protocol
        r'expect://',                        # PHP expect
        r'php://',                           # PHP filter
        r'data://',                          # Data protocol
        r'gopher://',                        # Gopher protocol
    ]

    for pattern in xxe_patterns:
        if re.search(pattern, xml_lower):
            logger.warning(f"SECURITY: Padrão XXE detectado no XML: {pattern}")
            raise ValueError(
                "XML contém padrões potencialmente maliciosos (XXE). "
                "Parsing rejeitado por segurança."
            )

    # SECURITY: Bloqueia DTDs externos
    if '<!doctype' in xml_lower and ('system' in xml_lower or 'public' in xml_lower):
        logger.warning("SECURITY: DOCTYPE externo detectado no XML")
        raise ValueError(
            "XML contém DOCTYPE externo. Parsing rejeitado por segurança."
        )


# ==================================================
# PATH VALIDATION
# ==================================================

def safe_join_path(base_dir: Union[str, Path], user_path: str) -> Path:
    """
    SECURITY: Junta paths de forma segura, prevenindo path traversal.

    Args:
        base_dir: Diretório base permitido
        user_path: Path fornecido pelo usuário

    Returns:
        Path seguro dentro do diretório base

    Raises:
        ValueError: Se o path resultante estiver fora do diretório base
    """
    base = Path(base_dir).resolve()

    # Sanitiza o path do usuário
    clean_path = user_path.replace("\\", "/")
    # Remove componentes de path traversal
    clean_path = re.sub(r'\.\.[/\\]', '', clean_path)
    clean_path = clean_path.lstrip("/\\")

    full_path = (base / clean_path).resolve()

    # Verifica se está dentro do diretório base
    if not str(full_path).startswith(str(base)):
        raise ValueError(
            f"Path traversal detectado: tentativa de acessar '{full_path}' "
            f"fora do diretório base '{base}'"
        )

    return full_path


def is_safe_filename(filename: str) -> bool:
    """
    SECURITY: Verifica se um nome de arquivo é seguro.

    Args:
        filename: Nome do arquivo para verificar

    Returns:
        True se o filename for seguro, False caso contrário
    """
    if not filename:
        return False

    # Caracteres proibidos em nomes de arquivos
    forbidden_chars = ['/', '\\', '..', '\x00', '\n', '\r']
    for char in forbidden_chars:
        if char in filename:
            return False

    # Verifica caracteres especiais do Windows
    windows_forbidden = ['<', '>', ':', '"', '|', '?', '*']
    for char in windows_forbidden:
        if char in filename:
            return False

    # Verifica se começa com caracteres perigosos
    if filename.startswith('.') or filename.startswith('-'):
        return False

    return True


# ==================================================
# INPUT SANITIZATION
# ==================================================

def sanitize_for_logging(data: str, max_length: int = 500) -> str:
    """
    SECURITY: Sanitiza dados antes de logar, prevenindo log injection.

    Args:
        data: Dados para sanitizar
        max_length: Tamanho máximo do output

    Returns:
        String sanitizada segura para logging
    """
    if not data:
        return ""

    # Remove caracteres de controle que podem causar log injection
    sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', data)

    # Trunca se necessário
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "...[truncated]"

    return sanitized


def mask_sensitive_data(text: str) -> str:
    """
    SECURITY: Mascara dados sensíveis em strings.

    Detecta e mascara:
    - API keys
    - Senhas em URLs
    - Tokens

    Args:
        text: Texto para mascarar

    Returns:
        Texto com dados sensíveis mascarados
    """
    if not text:
        return text

    # Mascara API keys (formatos comuns)
    patterns = [
        (r'(sk-[a-zA-Z0-9-]{20})[a-zA-Z0-9-]+', r'\1****'),
        (r'(AIzaSy[a-zA-Z0-9_-]{10})[a-zA-Z0-9_-]+', r'\1****'),
        (r'(password[=:]\s*)[^\s&]+', r'\1****'),
        (r'(senha[=:]\s*)[^\s&]+', r'\1****'),
        (r'(api[_-]?key[=:]\s*)[^\s&]+', r'\1****'),
        (r'(token[=:]\s*)[^\s&]+', r'\1****'),
        (r'(Bearer\s+)[^\s]+', r'\1****'),
    ]

    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result
