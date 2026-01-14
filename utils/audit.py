# utils/audit.py
"""
SECURITY: Sistema de Audit Logging para eventos de segurança.

Este módulo registra eventos sensíveis para:
- Detecção de atividades suspeitas
- Compliance e auditoria
- Investigação de incidentes
- Monitoramento de segurança

Eventos registrados:
- AUTH_LOGIN_SUCCESS/FAILURE: Tentativas de login
- AUTH_LOGOUT: Logout de usuário
- AUTH_PASSWORD_CHANGE: Alteração de senha
- USER_CREATED/UPDATED/DELETED: Gestão de usuários
- ADMIN_ACTION: Ações administrativas
- ACCESS_DENIED: Tentativas de acesso não autorizado
- SECURITY_ALERT: Alertas de segurança (rate limit, etc.)
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from fastapi import Request
from sqlalchemy.orm import Session

# Configura logger dedicado para auditoria
audit_logger = logging.getLogger("security.audit")
audit_logger.setLevel(logging.INFO)

# Handler para arquivo de auditoria (em produção, usar sistema centralizado)
import os
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# File handler para auditoria
audit_handler = logging.FileHandler(
    os.path.join(LOG_DIR, "audit.log"),
    encoding="utf-8"
)
audit_handler.setLevel(logging.INFO)

# Formato estruturado para fácil parsing
audit_format = logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
audit_handler.setFormatter(audit_format)
audit_logger.addHandler(audit_handler)

# Também loga no console em desenvolvimento
if os.getenv("ENV") != "production":
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(audit_format)
    audit_logger.addHandler(console_handler)


class AuditEvent(str, Enum):
    """Tipos de eventos de auditoria"""
    # Autenticação
    AUTH_LOGIN_SUCCESS = "AUTH_LOGIN_SUCCESS"
    AUTH_LOGIN_FAILURE = "AUTH_LOGIN_FAILURE"
    AUTH_LOGOUT = "AUTH_LOGOUT"
    AUTH_PASSWORD_CHANGE = "AUTH_PASSWORD_CHANGE"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"

    # Gestão de usuários
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_DELETED = "USER_DELETED"
    USER_ACTIVATED = "USER_ACTIVATED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_PASSWORD_RESET = "USER_PASSWORD_RESET"

    # Ações administrativas
    ADMIN_ACTION = "ADMIN_ACTION"
    ADMIN_CONFIG_CHANGE = "ADMIN_CONFIG_CHANGE"
    ADMIN_PROMPT_CHANGE = "ADMIN_PROMPT_CHANGE"

    # Controle de acesso
    ACCESS_DENIED = "ACCESS_DENIED"
    ACCESS_GRANTED = "ACCESS_GRANTED"
    IDOR_ATTEMPT = "IDOR_ATTEMPT"

    # Segurança
    SECURITY_ALERT = "SECURITY_ALERT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    SUSPICIOUS_ACTIVITY = "SUSPICIOUS_ACTIVITY"

    # Dados sensíveis
    DATA_EXPORT = "DATA_EXPORT"
    DATA_ACCESS = "DATA_ACCESS"


def get_client_ip(request: Optional[Request]) -> str:
    """
    SECURITY: Extrai IP real do cliente considerando proxies.
    """
    if not request:
        return "unknown"

    # Verifica headers de proxy (em ordem de confiabilidade)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For pode ter múltiplos IPs, pega o primeiro (cliente original)
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fallback para conexão direta
    if request.client:
        return request.client.host

    return "unknown"


def mask_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    SECURITY: Remove ou mascara dados sensíveis antes de logar.
    """
    sensitive_keys = {
        "password", "senha", "secret", "token", "api_key", "apikey",
        "authorization", "credential", "hashed_password"
    }

    masked = {}
    for key, value in data.items():
        key_lower = key.lower()

        if any(s in key_lower for s in sensitive_keys):
            masked[key] = "***MASKED***"
        elif isinstance(value, dict):
            masked[key] = mask_sensitive_data(value)
        elif isinstance(value, str) and len(value) > 100:
            # Trunca strings muito longas
            masked[key] = value[:100] + "...[truncated]"
        else:
            masked[key] = value

    return masked


def log_audit_event(
    event: AuditEvent,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    request: Optional[Request] = None,
    details: Optional[Dict[str, Any]] = None,
    success: bool = True,
    severity: str = "INFO"
):
    """
    SECURITY: Registra evento de auditoria.

    Args:
        event: Tipo do evento (AuditEvent enum)
        user_id: ID do usuário (se aplicável)
        username: Nome do usuário (se aplicável)
        request: Objeto Request do FastAPI (para extrair IP, user-agent, etc.)
        details: Detalhes adicionais do evento
        success: Se a ação foi bem sucedida
        severity: Nível de severidade (INFO, WARNING, ERROR, CRITICAL)

    Example:
        log_audit_event(
            AuditEvent.AUTH_LOGIN_SUCCESS,
            user_id=user.id,
            username=user.username,
            request=request,
            details={"method": "password"}
        )
    """
    # Constrói registro de auditoria
    audit_record = {
        "event": event.value,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "success": success,
        "user_id": user_id,
        "username": username,
        "ip_address": get_client_ip(request),
        "user_agent": request.headers.get("User-Agent", "unknown") if request else "unknown",
        "path": str(request.url.path) if request else "unknown",
        "method": request.method if request else "unknown",
    }

    # Adiciona detalhes (mascarando dados sensíveis)
    if details:
        audit_record["details"] = mask_sensitive_data(details)

    # Serializa para JSON
    log_message = json.dumps(audit_record, ensure_ascii=False, default=str)

    # Loga com nível apropriado
    if severity == "CRITICAL":
        audit_logger.critical(log_message)
    elif severity == "ERROR":
        audit_logger.error(log_message)
    elif severity == "WARNING":
        audit_logger.warning(log_message)
    else:
        audit_logger.info(log_message)


# ============================================
# Funções de conveniência para eventos comuns
# ============================================

def log_login_success(user_id: int, username: str, request: Request):
    """Registra login bem sucedido"""
    log_audit_event(
        AuditEvent.AUTH_LOGIN_SUCCESS,
        user_id=user_id,
        username=username,
        request=request
    )


def log_login_failure(username: str, request: Request, reason: str = "invalid_credentials"):
    """Registra falha de login"""
    log_audit_event(
        AuditEvent.AUTH_LOGIN_FAILURE,
        username=username,
        request=request,
        details={"reason": reason},
        success=False,
        severity="WARNING"
    )


def log_logout(user_id: int, username: str, request: Request):
    """Registra logout"""
    log_audit_event(
        AuditEvent.AUTH_LOGOUT,
        user_id=user_id,
        username=username,
        request=request
    )


def log_password_change(user_id: int, username: str, request: Request, changed_by: Optional[str] = None):
    """Registra alteração de senha"""
    log_audit_event(
        AuditEvent.AUTH_PASSWORD_CHANGE,
        user_id=user_id,
        username=username,
        request=request,
        details={"changed_by": changed_by or username}
    )


def log_user_created(created_user_id: int, created_username: str, created_by: str, request: Request):
    """Registra criação de usuário"""
    log_audit_event(
        AuditEvent.USER_CREATED,
        user_id=created_user_id,
        username=created_username,
        request=request,
        details={"created_by": created_by}
    )


def log_user_deleted(deleted_user_id: int, deleted_username: str, deleted_by: str, request: Request):
    """Registra exclusão de usuário"""
    log_audit_event(
        AuditEvent.USER_DELETED,
        user_id=deleted_user_id,
        username=deleted_username,
        request=request,
        details={"deleted_by": deleted_by},
        severity="WARNING"
    )


def log_access_denied(user_id: Optional[int], username: Optional[str], request: Request, reason: str):
    """Registra tentativa de acesso negado"""
    log_audit_event(
        AuditEvent.ACCESS_DENIED,
        user_id=user_id,
        username=username,
        request=request,
        details={"reason": reason},
        success=False,
        severity="WARNING"
    )


def log_admin_action(user_id: int, username: str, request: Request, action: str, target: Optional[str] = None):
    """Registra ação administrativa"""
    log_audit_event(
        AuditEvent.ADMIN_ACTION,
        user_id=user_id,
        username=username,
        request=request,
        details={"action": action, "target": target}
    )


def log_security_alert(request: Request, alert_type: str, details: Dict[str, Any]):
    """Registra alerta de segurança"""
    log_audit_event(
        AuditEvent.SECURITY_ALERT,
        request=request,
        details={"alert_type": alert_type, **details},
        success=False,
        severity="CRITICAL"
    )


def log_rate_limit_exceeded(request: Request, limit_type: str):
    """Registra violação de rate limit"""
    log_audit_event(
        AuditEvent.RATE_LIMIT_EXCEEDED,
        request=request,
        details={"limit_type": limit_type},
        success=False,
        severity="WARNING"
    )
