# utils/alerting.py
"""
Sistema de Alertas Automaticos.

Envia notificacoes quando problemas sao detectados:
- Erros criticos
- Health check degradado
- Circuit breaker aberto
- Jobs BERT travados

Suporta:
- Slack (webhook)
- Email (SMTP)
- Console/Log (desenvolvimento)

USO:
    from utils.alerting import alert_manager, AlertLevel

    # Alerta simples
    await alert_manager.send(
        level=AlertLevel.ERROR,
        title="Database Connection Failed",
        message="Nao foi possivel conectar ao PostgreSQL",
        context={"host": "db.local", "port": 5432}
    )

    # Alerta com metrica
    alert_manager.check_threshold(
        metric_name="error_rate",
        current_value=0.15,
        threshold=0.10,
        message="Taxa de erro acima do limite"
    )

Autor: LAB/PGE-MS
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import httpx

# Tenta usar logging estruturado
try:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


# ============================================
# CONFIGURATION
# ============================================

class AlertLevel(str, Enum):
    """Niveis de alerta."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AlertConfig:
    """Configuracao do sistema de alertas."""
    # Slack
    slack_webhook_url: Optional[str] = None
    slack_channel: Optional[str] = None

    # Email
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_to: Optional[List[str]] = None

    # Geral
    environment: str = "development"
    app_name: str = "Portal PGE-MS"
    enabled: bool = True

    # Rate limiting (evita flood de alertas)
    cooldown_minutes: int = 5  # Mesmo alerta so dispara a cada X minutos

    @classmethod
    def from_env(cls) -> "AlertConfig":
        """Carrega configuracao das variaveis de ambiente."""
        smtp_to = os.getenv("ALERT_SMTP_TO", "")
        return cls(
            slack_webhook_url=os.getenv("ALERT_SLACK_WEBHOOK"),
            slack_channel=os.getenv("ALERT_SLACK_CHANNEL", "#alertas"),
            smtp_host=os.getenv("ALERT_SMTP_HOST"),
            smtp_port=int(os.getenv("ALERT_SMTP_PORT", "587")),
            smtp_user=os.getenv("ALERT_SMTP_USER"),
            smtp_password=os.getenv("ALERT_SMTP_PASSWORD"),
            smtp_from=os.getenv("ALERT_SMTP_FROM"),
            smtp_to=smtp_to.split(",") if smtp_to else None,
            environment=os.getenv("ENVIRONMENT", "development"),
            app_name=os.getenv("APP_NAME", "Portal PGE-MS"),
            enabled=os.getenv("ALERTS_ENABLED", "true").lower() == "true",
            cooldown_minutes=int(os.getenv("ALERT_COOLDOWN_MINUTES", "5")),
        )


# ============================================
# ALERT MESSAGE
# ============================================

@dataclass
class Alert:
    """Representa um alerta."""
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    context: Dict[str, Any] = field(default_factory=dict)
    alert_id: Optional[str] = None

    def __post_init__(self):
        if not self.alert_id:
            # ID unico baseado em titulo + nivel
            self.alert_id = f"{self.level.value}:{self.title}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "title": self.title,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() + "Z",
            "context": self.context,
        }

    def to_slack_blocks(self, config: AlertConfig) -> List[Dict]:
        """Formata alerta para Slack Block Kit."""
        emoji_map = {
            AlertLevel.INFO: ":information_source:",
            AlertLevel.WARNING: ":warning:",
            AlertLevel.ERROR: ":x:",
            AlertLevel.CRITICAL: ":rotating_light:",
        }

        color_map = {
            AlertLevel.INFO: "#36a64f",
            AlertLevel.WARNING: "#ffcc00",
            AlertLevel.ERROR: "#ff6600",
            AlertLevel.CRITICAL: "#ff0000",
        }

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji_map.get(self.level, '')} {self.title}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": self.message
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Ambiente:* {config.environment} | *Horario:* {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
                    }
                ]
            }
        ]

        # Adiciona contexto se presente
        if self.context:
            context_text = "\n".join([f"*{k}:* {v}" for k, v in self.context.items()])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Detalhes:*\n{context_text}"
                }
            })

        return blocks


# ============================================
# ALERT MANAGER
# ============================================

class AlertManager:
    """Gerenciador central de alertas."""

    def __init__(self, config: Optional[AlertConfig] = None):
        self.config = config or AlertConfig.from_env()
        self._cooldown_cache: Dict[str, datetime] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Obtem cliente HTTP (singleton)."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    def _check_cooldown(self, alert_id: str) -> bool:
        """Verifica se alerta esta em cooldown."""
        if alert_id in self._cooldown_cache:
            last_sent = self._cooldown_cache[alert_id]
            cooldown = timedelta(minutes=self.config.cooldown_minutes)
            if datetime.utcnow() - last_sent < cooldown:
                logger.debug(f"Alerta '{alert_id}' em cooldown, ignorando")
                return True
        return False

    def _update_cooldown(self, alert_id: str) -> None:
        """Atualiza timestamp de cooldown."""
        self._cooldown_cache[alert_id] = datetime.utcnow()

        # Limpa cache antigo
        cutoff = datetime.utcnow() - timedelta(hours=1)
        self._cooldown_cache = {
            k: v for k, v in self._cooldown_cache.items()
            if v > cutoff
        }

    async def send(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        force: bool = False
    ) -> bool:
        """
        Envia um alerta.

        Args:
            level: Nivel do alerta
            title: Titulo curto
            message: Mensagem detalhada
            context: Contexto adicional (dict)
            force: Se True, ignora cooldown

        Returns:
            True se alerta foi enviado
        """
        if not self.config.enabled:
            logger.debug("Alertas desabilitados")
            return False

        alert = Alert(
            level=level,
            title=title,
            message=message,
            context=context or {}
        )

        # Verifica cooldown
        if not force and self._check_cooldown(alert.alert_id):
            return False

        # Log local sempre
        log_method = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.ERROR: logger.error,
            AlertLevel.CRITICAL: logger.critical,
        }.get(level, logger.info)

        log_method(f"[ALERT] {title}: {message}")

        # Envia para destinos configurados
        sent = False

        if self.config.slack_webhook_url:
            try:
                await self._send_slack(alert)
                sent = True
            except Exception as e:
                logger.error(f"Falha ao enviar alerta Slack: {e}")

        # Email (implementacao simplificada)
        if self.config.smtp_host and self.config.smtp_to:
            try:
                await self._send_email(alert)
                sent = True
            except Exception as e:
                logger.error(f"Falha ao enviar alerta Email: {e}")

        if sent:
            self._update_cooldown(alert.alert_id)

        return sent

    async def _send_slack(self, alert: Alert) -> None:
        """Envia alerta para Slack."""
        client = await self._get_client()

        payload = {
            "channel": self.config.slack_channel,
            "username": self.config.app_name,
            "blocks": alert.to_slack_blocks(self.config),
        }

        response = await client.post(
            self.config.slack_webhook_url,
            json=payload
        )
        response.raise_for_status()

    async def _send_email(self, alert: Alert) -> None:
        """Envia alerta por email (via aiosmtplib se disponivel)."""
        try:
            import aiosmtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["Subject"] = f"[{alert.level.value.upper()}] {alert.title}"
            msg["From"] = self.config.smtp_from
            msg["To"] = ", ".join(self.config.smtp_to)

            body = f"""
{alert.title}
{'=' * 40}

{alert.message}

Nivel: {alert.level.value}
Horario: {alert.timestamp.isoformat()}
Ambiente: {self.config.environment}

Contexto:
{json.dumps(alert.context, indent=2, ensure_ascii=False)}
"""
            msg.set_content(body)

            await aiosmtplib.send(
                msg,
                hostname=self.config.smtp_host,
                port=self.config.smtp_port,
                username=self.config.smtp_user,
                password=self.config.smtp_password,
                use_tls=True
            )
        except ImportError:
            logger.warning("aiosmtplib nao instalado, email nao enviado")

    async def check_threshold(
        self,
        metric_name: str,
        current_value: float,
        threshold: float,
        message: str,
        level: AlertLevel = AlertLevel.WARNING,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Verifica se metrica ultrapassou threshold e envia alerta.

        Returns:
            True se alerta foi enviado
        """
        if current_value > threshold:
            ctx = context or {}
            ctx.update({
                "metrica": metric_name,
                "valor_atual": current_value,
                "threshold": threshold,
            })

            return await self.send(
                level=level,
                title=f"Threshold ultrapassado: {metric_name}",
                message=message,
                context=ctx
            )
        return False

    async def close(self) -> None:
        """Fecha cliente HTTP."""
        if self._http_client:
            await self._http_client.aclose()


# ============================================
# SINGLETON
# ============================================

# Instancia global
alert_manager = AlertManager()


# ============================================
# HELPER FUNCTIONS
# ============================================

async def alert_error(title: str, message: str, **context) -> bool:
    """Atalho para alertas de erro."""
    return await alert_manager.send(
        level=AlertLevel.ERROR,
        title=title,
        message=message,
        context=context
    )


async def alert_critical(title: str, message: str, **context) -> bool:
    """Atalho para alertas criticos."""
    return await alert_manager.send(
        level=AlertLevel.CRITICAL,
        title=title,
        message=message,
        context=context,
        force=True  # Criticos sempre enviam
    )


async def alert_warning(title: str, message: str, **context) -> bool:
    """Atalho para alertas de warning."""
    return await alert_manager.send(
        level=AlertLevel.WARNING,
        title=title,
        message=message,
        context=context
    )


# ============================================
# INTEGRATION HELPERS
# ============================================

async def alert_on_circuit_open(service_name: str, failure_count: int) -> None:
    """Alerta quando circuit breaker abre."""
    await alert_manager.send(
        level=AlertLevel.ERROR,
        title=f"Circuit Breaker Aberto: {service_name}",
        message=f"O servico {service_name} foi marcado como indisponivel apos {failure_count} falhas consecutivas.",
        context={
            "servico": service_name,
            "falhas": failure_count,
            "acao": "Requests serao bloqueados temporariamente"
        }
    )


async def alert_on_health_degraded(components: List[str]) -> None:
    """Alerta quando health check degrada."""
    await alert_manager.send(
        level=AlertLevel.WARNING,
        title="Health Check Degradado",
        message=f"Componentes com problemas: {', '.join(components)}",
        context={
            "componentes": components,
            "acao": "Verificar status dos servicos"
        }
    )


async def alert_on_high_error_rate(rate: float, threshold: float) -> None:
    """Alerta quando taxa de erro esta alta."""
    await alert_manager.check_threshold(
        metric_name="error_rate",
        current_value=rate,
        threshold=threshold,
        message=f"Taxa de erro atual: {rate:.1%} (limite: {threshold:.1%})",
        level=AlertLevel.ERROR
    )


# ============================================
# EXPORTS
# ============================================

__all__ = [
    "AlertLevel",
    "AlertConfig",
    "Alert",
    "AlertManager",
    "alert_manager",
    "alert_error",
    "alert_critical",
    "alert_warning",
    "alert_on_circuit_open",
    "alert_on_health_degraded",
    "alert_on_high_error_rate",
]
