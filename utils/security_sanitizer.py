# utils/security_sanitizer.py
"""
Módulo de sanitização de inputs para prevenir XSS e injeções maliciosas.

SECURITY: Implementa sanitização de HTML e validação de inputs
"""

import re
import html
from typing import Optional


def sanitize_html_input(text: Optional[str]) -> Optional[str]:
    """
    Remove tags HTML e atributos perigosos de texto antes de salvar no banco.
    
    SECURITY: Previne XSS Persistente (Stored XSS)
    
    Args:
        text: Texto a ser sanitizado
        
    Returns:
        Texto limpo sem tags HTML perigosas
    """
    if not text:
        return text
    
    # Remove todas as tags HTML e seus atributos
    # Isso previne injeção de <script>, <img onerror="">, etc.
    text = re.sub(r'<[^>]*>', '', text)
    
    # Escapa caracteres especiais HTML remanescentes
    text = html.escape(text)
    
    # Remove caracteres de controle perigosos
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    return text


def sanitize_user_input(data: dict) -> dict:
    """
    Sanitiza todos os campos de texto em um dicionário de dados de usuário.
    
    Args:
        data: Dicionário com dados do usuário
        
    Returns:
        Dicionário com dados sanitizados
    """
    text_fields = ['username', 'full_name', 'email', 'setor']
    
    for field in text_fields:
        if field in data and isinstance(data[field], str):
            data[field] = sanitize_html_input(data[field])
    
    return data


def sanitize_feedback_input(text: Optional[str]) -> Optional[str]:
    """
    Sanitiza feedbacks preservando quebras de linha mas removendo HTML perigoso.
    
    Args:
        text: Texto do feedback
        
    Returns:
        Texto sanitizado
    """
    if not text:
        return text
    
    # Preserva quebras de linha
    text = text.replace('\r\n', '\n')
    
    # Remove tags HTML
    text = re.sub(r'<[^>]*>', '', text)
    
    # Escapa caracteres especiais
    text = html.escape(text)
    
    return text


def validate_file_magic_number(file_content: bytes, expected_extensions: list) -> bool:
    """
    Valida o magic number (assinatura binária) de um arquivo.
    
    SECURITY: Previne upload de arquivos maliciosos disfarçados
    
    Args:
        file_content: Conteúdo binário do arquivo
        expected_extensions: Lista de extensões esperadas
        
    Returns:
        True se o arquivo é válido, False caso contrário
    """
    # Magic numbers conhecidos
    magic_numbers = {
        'png': b'\x89PNG\r\n\x1a\n',
        'jpg': b'\xff\xd8\xff',
        'jpeg': b'\xff\xd8\xff',
        'pdf': b'%PDF',
        'zip': b'PK\x03\x04',
        'docx': b'PK\x03\x04',  # DOCX é um ZIP
        'xlsx': b'PK\x03\x04',  # XLSX é um ZIP
    }
    
    # Verifica se alguma extensão esperada corresponde
    for ext in expected_extensions:
        ext_lower = ext.lower().lstrip('.')
        if ext_lower in magic_numbers:
            magic = magic_numbers[ext_lower]
            if file_content.startswith(magic):
                return True
    
    # Se não encontrou match e é uma extensão conhecida, rejeita
    known_exts = set(magic_numbers.keys())
    if any(ext.lower().lstrip('.') in known_exts for ext in expected_extensions):
        return False
    
    # Para extensões não conhecidas, permite (mas registra warning)
    return True
