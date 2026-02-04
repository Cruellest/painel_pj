# utils/security_sanitizer.py
"""
SECURITY: Utilitários para sanitização de dados e prevenção de XSS/Injeção.
"""

import re
import html
from typing import Optional, Any

# Bibliotecas de limpeza (tentativa de importação de bleach ou similar)
# Caso não esteja disponível, usa regex safe fallback
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False


def sanitize_html(text: Optional[str]) -> Optional[str]:
    """
    Remove tags HTML perigosas e atributos de eventos (onmouseover, etc).
    
    Estratégia: Whitelist de tags seguras para Markdown (opcional) 
    ou remoção total dependendo do contexto.
    """
    if text is None:
        return None
    
    if not isinstance(text, str):
        return str(text)

    if BLEACH_AVAILABLE:
        # Whitelist de tags permitidas (ex: para Markdown básico)
        allowed_tags = [
            'p', 'br', 'b', 'i', 'strong', 'em', 'code', 'pre', 
            'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'blockquote', 'a', 'hr'
        ]
        allowed_attrs = {
            'a': ['href', 'title', 'target'],
            '*': ['class']
        }
        return bleach.clean(text, tags=allowed_tags, attributes=allowed_attrs, strip=True)
    else:
        # Fallback: Remove todas as tags HTML se bleach não estiver disponível
        # e escapa caracteres especiais
        clean = re.sub(r'<[^>]*?>', '', text)
        return html.escape(clean)


def sanitize_input(data: Any) -> Any:
    """
    Higieniza recursivamente strings em dicts ou lists.
    """
    if isinstance(data, str):
        return sanitize_html(data)
    elif isinstance(data, dict):
        return {k: sanitize_input(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_input(i) for i in data]
    return data


def validate_file_signature(file_content: bytes, expected_mime: str) -> bool:
    """
    SECURITY: Valida a assinatura binária (Magic Numbers) de um arquivo.
    Previne ataques de upload de scripts disfarçados de imagem.
    """
    # Assinaturas comuns (Magic Numbers)
    signatures = {
        "image/png": [b"\x89PNG\r\n\x1a\n"],
        "image/jpeg": [b"\xff\xd8\xff"],
        "application/pdf": [b"%PDF-"],
        "application/zip": [b"PK\x03\x04"],
        "image/gif": [b"GIF87a", b"GIF89a"],
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [b"PK\x03\x04"], # .xlsx
        "application/vnd.ms-excel": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"], # .xls
    }
    
    if expected_mime not in signatures:
        # Se não temos a assinatura mapeada, permitimos (ou bloqueamos por segurança)
        return True
        
    for sig in signatures[expected_mime]:
        if file_content.startswith(sig):
            return True
            
    return False
