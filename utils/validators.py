# utils/validators.py
"""
Validadores centralizados para o Portal PGE-MS.

Fornece funções de validação reutilizáveis para:
- CPF/CNPJ
- Números de processo CNJ
- Email
- Telefone
- Datas
- Textos (sanitização, limites)

USO:
    from utils.validators import (
        validate_cpf, validate_cnpj, validate_processo_cnj,
        sanitize_text, validate_email
    )

    if not validate_cpf(cpf):
        raise ValueError("CPF inválido")

Autor: LAB/PGE-MS
"""

import re
from datetime import datetime, date
from typing import Optional, Tuple, Union


# ============================================
# CPF / CNPJ
# ============================================

def validate_cpf(cpf: str) -> bool:
    """
    Valida um CPF brasileiro.

    Args:
        cpf: CPF com ou sem formatação

    Returns:
        True se válido, False caso contrário
    """
    # Remove formatação
    cpf = re.sub(r'[^\d]', '', str(cpf))

    # Verifica tamanho
    if len(cpf) != 11:
        return False

    # Verifica se todos os dígitos são iguais
    if cpf == cpf[0] * 11:
        return False

    # Calcula primeiro dígito verificador
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto

    if int(cpf[9]) != digito1:
        return False

    # Calcula segundo dígito verificador
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto

    return int(cpf[10]) == digito2


def validate_cnpj(cnpj: str) -> bool:
    """
    Valida um CNPJ brasileiro.

    Args:
        cnpj: CNPJ com ou sem formatação

    Returns:
        True se válido, False caso contrário
    """
    # Remove formatação
    cnpj = re.sub(r'[^\d]', '', str(cnpj))

    # Verifica tamanho
    if len(cnpj) != 14:
        return False

    # Verifica se todos os dígitos são iguais
    if cnpj == cnpj[0] * 14:
        return False

    # Pesos para cálculo
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    # Primeiro dígito
    soma = sum(int(cnpj[i]) * pesos1[i] for i in range(12))
    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto

    if int(cnpj[12]) != digito1:
        return False

    # Segundo dígito
    soma = sum(int(cnpj[i]) * pesos2[i] for i in range(13))
    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto

    return int(cnpj[13]) == digito2


def validate_cpf_or_cnpj(documento: str) -> Tuple[bool, str]:
    """
    Valida CPF ou CNPJ automaticamente.

    Args:
        documento: CPF ou CNPJ com ou sem formatação

    Returns:
        Tuple (is_valid, tipo) onde tipo é "cpf", "cnpj" ou "invalid"
    """
    doc = re.sub(r'[^\d]', '', str(documento))

    if len(doc) == 11:
        return validate_cpf(doc), "cpf" if validate_cpf(doc) else "invalid"
    elif len(doc) == 14:
        return validate_cnpj(doc), "cnpj" if validate_cnpj(doc) else "invalid"
    else:
        return False, "invalid"


def format_cpf(cpf: str) -> str:
    """Formata CPF: 123.456.789-00"""
    cpf = re.sub(r'[^\d]', '', str(cpf))
    if len(cpf) != 11:
        return cpf
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def format_cnpj(cnpj: str) -> str:
    """Formata CNPJ: 12.345.678/0001-00"""
    cnpj = re.sub(r'[^\d]', '', str(cnpj))
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


# ============================================
# NÚMERO DE PROCESSO CNJ
# ============================================

def validate_processo_cnj(numero: str) -> bool:
    """
    Valida número de processo no formato CNJ.

    Formato: NNNNNNN-DD.AAAA.J.TR.OOOO
    - NNNNNNN: Número sequencial (7 dígitos)
    - DD: Dígito verificador (2 dígitos)
    - AAAA: Ano de ajuizamento (4 dígitos)
    - J: Segmento do Poder Judiciário (1 dígito)
    - TR: Tribunal (2 dígitos)
    - OOOO: Unidade de origem (4 dígitos)

    Args:
        numero: Número do processo com ou sem formatação

    Returns:
        True se formato válido, False caso contrário
    """
    # Remove formatação
    numero = re.sub(r'[^\d]', '', str(numero))

    # Deve ter 20 dígitos
    if len(numero) != 20:
        return False

    # Extrai componentes
    sequencial = numero[:7]
    digito = numero[7:9]
    ano = numero[9:13]
    segmento = numero[13]
    tribunal = numero[14:16]
    origem = numero[16:20]

    # Validações básicas
    try:
        ano_int = int(ano)
        if ano_int < 1900 or ano_int > datetime.now().year + 1:
            return False
    except ValueError:
        return False

    # Valida dígito verificador (algoritmo módulo 97)
    # Resto = (NNNNNNN * 10000000000000 + AAAA * 100000000 + J * 10000000 + TR * 100000 + OOOO * 100) mod 97
    # DV = 97 - Resto
    try:
        base = int(sequencial + ano + segmento + tribunal + origem + "00")
        resto = base % 97
        dv_calculado = 97 - resto
        dv_informado = int(digito)

        return dv_calculado == dv_informado
    except (ValueError, ZeroDivisionError):
        return False


def format_processo_cnj(numero: str) -> str:
    """
    Formata número de processo no padrão CNJ.

    Args:
        numero: Número do processo (apenas dígitos ou já formatado)

    Returns:
        Número formatado: NNNNNNN-DD.AAAA.J.TR.OOOO
    """
    numero = re.sub(r'[^\d]', '', str(numero))

    if len(numero) != 20:
        return numero

    return f"{numero[:7]}-{numero[7:9]}.{numero[9:13]}.{numero[13]}.{numero[14:16]}.{numero[16:]}"


def extract_processo_info(numero: str) -> Optional[dict]:
    """
    Extrai informações de um número de processo CNJ.

    Args:
        numero: Número do processo

    Returns:
        Dict com componentes ou None se inválido
    """
    numero = re.sub(r'[^\d]', '', str(numero))

    if len(numero) != 20:
        return None

    # Mapeamento de segmentos
    segmentos = {
        "1": "STF",
        "2": "CNJ",
        "3": "STJ",
        "4": "Justiça Federal",
        "5": "Justiça do Trabalho",
        "6": "Justiça Eleitoral",
        "7": "Justiça Militar da União",
        "8": "Justiça Estadual",
        "9": "Justiça Militar Estadual",
    }

    segmento_codigo = numero[13]

    return {
        "numero_sequencial": numero[:7],
        "digito_verificador": numero[7:9],
        "ano": numero[9:13],
        "segmento_codigo": segmento_codigo,
        "segmento_nome": segmentos.get(segmento_codigo, "Desconhecido"),
        "tribunal": numero[14:16],
        "origem": numero[16:20],
        "numero_formatado": format_processo_cnj(numero),
        "valido": validate_processo_cnj(numero)
    }


# ============================================
# EMAIL
# ============================================

def validate_email(email: str) -> bool:
    """
    Valida formato de email.

    Args:
        email: Endereço de email

    Returns:
        True se formato válido
    """
    if not email or not isinstance(email, str):
        return False

    # Regex simplificado para email
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email.strip()))


def normalize_email(email: str) -> str:
    """
    Normaliza email: lowercase e trim.

    Args:
        email: Endereço de email

    Returns:
        Email normalizado
    """
    if not email:
        return ""
    return email.strip().lower()


# ============================================
# TELEFONE
# ============================================

def validate_telefone(telefone: str) -> bool:
    """
    Valida número de telefone brasileiro.

    Aceita formatos:
    - (67) 99999-9999
    - 67999999999
    - +55 67 99999-9999

    Args:
        telefone: Número de telefone

    Returns:
        True se formato válido
    """
    # Remove formatação
    tel = re.sub(r'[^\d]', '', str(telefone))

    # Remove código do país se presente
    if tel.startswith('55') and len(tel) > 11:
        tel = tel[2:]

    # Deve ter 10 ou 11 dígitos (com ou sem 9)
    if len(tel) not in (10, 11):
        return False

    # DDD válido (11-99)
    ddd = int(tel[:2])
    if ddd < 11 or ddd > 99:
        return False

    return True


def format_telefone(telefone: str) -> str:
    """
    Formata telefone: (67) 99999-9999

    Args:
        telefone: Número de telefone

    Returns:
        Telefone formatado
    """
    tel = re.sub(r'[^\d]', '', str(telefone))

    # Remove código do país
    if tel.startswith('55') and len(tel) > 11:
        tel = tel[2:]

    if len(tel) == 11:
        return f"({tel[:2]}) {tel[2:7]}-{tel[7:]}"
    elif len(tel) == 10:
        return f"({tel[:2]}) {tel[2:6]}-{tel[6:]}"
    else:
        return telefone


# ============================================
# TEXTO / SANITIZAÇÃO
# ============================================

def sanitize_text(
    text: str,
    max_length: int = None,
    strip_html: bool = True,
    strip_control_chars: bool = True,
    normalize_whitespace: bool = True
) -> str:
    """
    Sanitiza texto removendo caracteres perigosos.

    Args:
        text: Texto a sanitizar
        max_length: Tamanho máximo (trunca se necessário)
        strip_html: Remove tags HTML
        strip_control_chars: Remove caracteres de controle
        normalize_whitespace: Normaliza espaços em branco

    Returns:
        Texto sanitizado
    """
    if not text:
        return ""

    result = str(text)

    # Remove tags HTML
    if strip_html:
        result = re.sub(r'<[^>]+>', '', result)

    # Remove caracteres de controle (exceto newline e tab)
    if strip_control_chars:
        result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', result)

    # Normaliza whitespace
    if normalize_whitespace:
        result = ' '.join(result.split())

    # Trunca se necessário
    if max_length and len(result) > max_length:
        result = result[:max_length]

    return result.strip()


def sanitize_filename(filename: str) -> str:
    """
    Sanitiza nome de arquivo removendo caracteres perigosos.

    SECURITY: Previne path traversal e caracteres inválidos.

    Args:
        filename: Nome do arquivo

    Returns:
        Nome sanitizado
    """
    if not filename:
        return "unnamed"

    # Remove path components
    filename = filename.replace("\\", "/")
    filename = filename.split("/")[-1]

    # Remove caracteres perigosos
    # Mantém apenas alfanuméricos, underline, hífen, ponto
    filename = re.sub(r'[^\w\-.]', '_', filename)

    # Remove múltiplos pontos consecutivos
    filename = re.sub(r'\.+', '.', filename)

    # Remove pontos no início
    filename = filename.lstrip('.')

    # Limita tamanho
    if len(filename) > 200:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:190] + ('.' + ext if ext else '')

    return filename or "unnamed"


def validate_slug(slug: str) -> bool:
    """
    Valida se string é um slug válido.

    Slug válido: apenas letras minúsculas, números e hífens.

    Args:
        slug: String a validar

    Returns:
        True se slug válido
    """
    if not slug:
        return False
    return bool(re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', slug))


def generate_slug(text: str, max_length: int = 50) -> str:
    """
    Gera slug a partir de texto.

    Args:
        text: Texto para converter
        max_length: Tamanho máximo

    Returns:
        Slug gerado
    """
    if not text:
        return ""

    # Normaliza unicode
    import unicodedata
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ASCII', 'ignore').decode('ASCII')

    # Lowercase
    text = text.lower()

    # Substitui espaços e caracteres especiais por hífen
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)

    # Remove hífens do início e fim
    text = text.strip('-')

    # Trunca
    if len(text) > max_length:
        text = text[:max_length].rstrip('-')

    return text


# ============================================
# DATAS
# ============================================

def validate_date_range(
    start_date: Union[date, datetime, str],
    end_date: Union[date, datetime, str],
    max_days: int = None
) -> Tuple[bool, Optional[str]]:
    """
    Valida intervalo de datas.

    Args:
        start_date: Data inicial
        end_date: Data final
        max_days: Máximo de dias permitido (opcional)

    Returns:
        Tuple (is_valid, error_message)
    """
    # Converte strings para date
    if isinstance(start_date, str):
        try:
            start_date = datetime.fromisoformat(start_date).date()
        except ValueError:
            return False, "Data inicial inválida"

    if isinstance(end_date, str):
        try:
            end_date = datetime.fromisoformat(end_date).date()
        except ValueError:
            return False, "Data final inválida"

    # Converte datetime para date
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()

    # Valida ordem
    if start_date > end_date:
        return False, "Data inicial deve ser anterior à data final"

    # Valida intervalo máximo
    if max_days:
        diff = (end_date - start_date).days
        if diff > max_days:
            return False, f"Intervalo máximo permitido: {max_days} dias"

    return True, None


def parse_date_br(date_str: str) -> Optional[date]:
    """
    Parse de data no formato brasileiro (dd/mm/yyyy).

    Args:
        date_str: Data em formato brasileiro

    Returns:
        Objeto date ou None se inválido
    """
    if not date_str:
        return None

    # Tenta formato brasileiro
    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y-%m-%d",  # ISO
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue

    return None


def format_date_br(d: Union[date, datetime, str]) -> str:
    """
    Formata data para formato brasileiro (dd/mm/yyyy).

    Args:
        d: Data a formatar

    Returns:
        Data formatada ou string vazia se inválido
    """
    if not d:
        return ""

    if isinstance(d, str):
        d = parse_date_br(d)
        if not d:
            return ""

    if isinstance(d, datetime):
        d = d.date()

    return d.strftime("%d/%m/%Y")


# ============================================
# VALORES MONETÁRIOS
# ============================================

def parse_currency_br(value: str) -> Optional[float]:
    """
    Parse de valor monetário brasileiro.

    Aceita: R$ 1.234,56 ou 1234.56 ou 1234,56

    Args:
        value: Valor em string

    Returns:
        Float ou None se inválido
    """
    if not value:
        return None

    # Remove R$ e espaços
    value = str(value).replace("R$", "").strip()

    # Detecta formato (vírgula ou ponto como decimal)
    if "," in value and "." in value:
        # Formato brasileiro: 1.234,56
        value = value.replace(".", "").replace(",", ".")
    elif "," in value:
        # Vírgula como decimal: 1234,56
        value = value.replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def format_currency_br(value: float) -> str:
    """
    Formata valor para moeda brasileira.

    Args:
        value: Valor numérico

    Returns:
        String formatada: R$ 1.234,56
    """
    if value is None:
        return ""

    # Formata com 2 casas decimais
    formatted = f"{value:,.2f}"

    # Converte para formato brasileiro
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")

    return f"R$ {formatted}"


__all__ = [
    # CPF/CNPJ
    "validate_cpf",
    "validate_cnpj",
    "validate_cpf_or_cnpj",
    "format_cpf",
    "format_cnpj",
    # Processo CNJ
    "validate_processo_cnj",
    "format_processo_cnj",
    "extract_processo_info",
    # Email
    "validate_email",
    "normalize_email",
    # Telefone
    "validate_telefone",
    "format_telefone",
    # Texto
    "sanitize_text",
    "sanitize_filename",
    "validate_slug",
    "generate_slug",
    # Datas
    "validate_date_range",
    "parse_date_br",
    "format_date_br",
    # Moeda
    "parse_currency_br",
    "format_currency_br",
]
