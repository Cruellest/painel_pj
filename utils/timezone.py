# utils/timezone.py
"""
POLÍTICA GLOBAL DE TIMEZONE DO SISTEMA

Este módulo define a política única de timezone para todo o sistema:

REGRAS:
1. GRAVAÇÃO NO BANCO: Sempre UTC (timezone-aware)
2. EXIBIÇÃO NO FRONTEND: Sempre America/Campo_Grande (UTC-4)
3. SERIALIZAÇÃO JSON: ISO 8601 com timezone explícito

USO:
    from utils.timezone import now_utc, now_local, to_local, to_utc, TIMEZONE_LOCAL

    # Para gravar no banco (UTC)
    created_at = now_utc()

    # Para exibir ao usuário (UTC-4)
    display_time = to_local(created_at)

    # Constante para frontend
    TIMEZONE_LOCAL = "America/Campo_Grande"

IMPORTANTE:
- Nunca use datetime.utcnow() ou datetime.now() diretamente
- Sempre use as funções deste módulo
- O frontend DEVE converter timestamps recebidos para TIMEZONE_LOCAL
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
import pytz

# =============================================================================
# CONFIGURAÇÃO DE TIMEZONE
# =============================================================================

# Timezone local do sistema (Mato Grosso do Sul)
TIMEZONE_LOCAL_NAME = "America/Campo_Grande"
TIMEZONE_LOCAL = pytz.timezone(TIMEZONE_LOCAL_NAME)

# Offset fixo para referência (UTC-4)
TIMEZONE_OFFSET_HOURS = -4

# UTC timezone
UTC = timezone.utc


# =============================================================================
# FUNÇÕES PRINCIPAIS
# =============================================================================

def now_utc() -> datetime:
    """
    Retorna o datetime atual em UTC com timezone-aware.

    USE ESTA FUNÇÃO para gravar timestamps no banco de dados.

    Returns:
        datetime: Datetime atual em UTC (timezone-aware)

    Example:
        >>> from utils.timezone import now_utc
        >>> created_at = now_utc()
        >>> print(created_at)
        2026-01-20 18:30:00+00:00
    """
    return datetime.now(UTC)


def now_local() -> datetime:
    """
    Retorna o datetime atual no timezone local (America/Campo_Grande).

    USE ESTA FUNÇÃO para exibir horários ao usuário.

    Returns:
        datetime: Datetime atual em UTC-4 (timezone-aware)

    Example:
        >>> from utils.timezone import now_local
        >>> local_time = now_local()
        >>> print(local_time)
        2026-01-20 14:30:00-04:00
    """
    return datetime.now(TIMEZONE_LOCAL)


def to_local(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Converte um datetime para o timezone local (America/Campo_Grande).

    Aceita tanto naive quanto aware datetimes:
    - Se naive: assume que está em UTC
    - Se aware: converte para o timezone local

    Args:
        dt: Datetime a converter (pode ser None)

    Returns:
        datetime: Datetime no timezone local (ou None se input for None)

    Example:
        >>> from utils.timezone import to_local, now_utc
        >>> utc_time = now_utc()
        >>> local_time = to_local(utc_time)
        >>> print(local_time.strftime('%Y-%m-%d %H:%M:%S %Z'))
        2026-01-20 14:30:00 -04
    """
    if dt is None:
        return None

    # Se naive, assume UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    # Converte para timezone local
    return dt.astimezone(TIMEZONE_LOCAL)


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Converte um datetime para UTC.

    Aceita tanto naive quanto aware datetimes:
    - Se naive: assume que está no timezone local
    - Se aware: converte para UTC

    Args:
        dt: Datetime a converter (pode ser None)

    Returns:
        datetime: Datetime em UTC (ou None se input for None)

    Example:
        >>> from utils.timezone import to_utc, now_local
        >>> local_time = now_local()
        >>> utc_time = to_utc(local_time)
    """
    if dt is None:
        return None

    # Se naive, assume timezone local
    if dt.tzinfo is None:
        dt = TIMEZONE_LOCAL.localize(dt)

    # Converte para UTC
    return dt.astimezone(UTC)


def format_local(dt: Optional[datetime], format: str = "%d/%m/%Y %H:%M:%S") -> str:
    """
    Formata um datetime no timezone local para exibição.

    Args:
        dt: Datetime a formatar
        format: Formato strftime (default: DD/MM/YYYY HH:MM:SS)

    Returns:
        str: Data formatada no timezone local (ou "-" se None)

    Example:
        >>> from utils.timezone import format_local, now_utc
        >>> print(format_local(now_utc()))
        20/01/2026 14:30:00
    """
    if dt is None:
        return "-"

    local_dt = to_local(dt)
    return local_dt.strftime(format)


def format_iso_local(dt: Optional[datetime]) -> Optional[str]:
    """
    Formata um datetime como ISO 8601 no timezone local.

    Útil para serialização JSON com timezone explícito.

    Args:
        dt: Datetime a formatar

    Returns:
        str: ISO 8601 com offset (ex: 2026-01-20T14:30:00-04:00)

    Example:
        >>> from utils.timezone import format_iso_local, now_utc
        >>> print(format_iso_local(now_utc()))
        2026-01-20T14:30:00-04:00
    """
    if dt is None:
        return None

    local_dt = to_local(dt)
    return local_dt.isoformat()


def parse_iso(iso_string: str) -> Optional[datetime]:
    """
    Parseia uma string ISO 8601 para datetime timezone-aware.

    Args:
        iso_string: String no formato ISO 8601

    Returns:
        datetime: Datetime timezone-aware (ou None se inválido)
    """
    if not iso_string:
        return None

    try:
        # Tenta parsear com timezone
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt
    except (ValueError, AttributeError):
        return None


# =============================================================================
# FUNÇÕES PARA SQLALCHEMY
# =============================================================================

def get_utc_now():
    """
    Função callable para uso em Column(default=...).

    USE EM MODELS:
        from utils.timezone import get_utc_now
        created_at = Column(DateTime(timezone=True), default=get_utc_now)

    Returns:
        datetime: Datetime atual em UTC (timezone-aware)
    """
    return now_utc()


# =============================================================================
# CONSTANTES PARA FRONTEND
# =============================================================================

# Nome do timezone para uso em JavaScript
TIMEZONE_JS = TIMEZONE_LOCAL_NAME

# Snippet JavaScript para conversão de timezone
JS_TIMEZONE_HELPER = f"""
// Timezone do sistema (Mato Grosso do Sul)
const SYSTEM_TIMEZONE = '{TIMEZONE_LOCAL_NAME}';

/**
 * Converte um timestamp ISO para o timezone local do sistema.
 * @param {{string}} isoString - Timestamp no formato ISO 8601
 * @returns {{Date}} - Date object no timezone local
 */
function toLocalTime(isoString) {{
    if (!isoString) return null;
    return new Date(isoString);
}}

/**
 * Formata um timestamp ISO para exibição no timezone local.
 * @param {{string}} isoString - Timestamp no formato ISO 8601
 * @param {{object}} options - Opções de formatação (opcional)
 * @returns {{string}} - Data/hora formatada
 */
function formatDateTime(isoString, options = {{}}) {{
    if (!isoString) return '-';
    const defaultOptions = {{
        timeZone: SYSTEM_TIMEZONE,
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    }};
    return new Date(isoString).toLocaleString('pt-BR', {{ ...defaultOptions, ...options }});
}}

/**
 * Formata apenas a data no timezone local.
 * @param {{string}} isoString - Timestamp no formato ISO 8601
 * @returns {{string}} - Data formatada (DD/MM/YYYY)
 */
function formatDate(isoString) {{
    if (!isoString) return '-';
    return new Date(isoString).toLocaleDateString('pt-BR', {{ timeZone: SYSTEM_TIMEZONE }});
}}

/**
 * Formata apenas a hora no timezone local.
 * @param {{string}} isoString - Timestamp no formato ISO 8601
 * @returns {{string}} - Hora formatada (HH:MM:SS)
 */
function formatTime(isoString) {{
    if (!isoString) return '-';
    return new Date(isoString).toLocaleTimeString('pt-BR', {{ timeZone: SYSTEM_TIMEZONE }});
}}
"""


# =============================================================================
# VALIDAÇÃO
# =============================================================================

def validate_timezone_setup():
    """
    Valida que o setup de timezone está correto.

    Útil para testes e diagnóstico.

    Returns:
        dict: Informações de timezone do sistema
    """
    utc_now = now_utc()
    local_now = now_local()

    return {
        "utc_now": utc_now.isoformat(),
        "local_now": local_now.isoformat(),
        "timezone_name": TIMEZONE_LOCAL_NAME,
        "offset_hours": TIMEZONE_OFFSET_HOURS,
        "utc_formatted": format_local(utc_now),
        "difference_hours": (local_now.utcoffset().total_seconds() / 3600) if local_now.utcoffset() else 0
    }


if __name__ == "__main__":
    # Teste rápido
    print("=" * 60)
    print("TESTE DE TIMEZONE")
    print("=" * 60)
    info = validate_timezone_setup()
    for key, value in info.items():
        print(f"{key}: {value}")
