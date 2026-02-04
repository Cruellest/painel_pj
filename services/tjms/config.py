# services/tjms/config.py
"""
Configuracao centralizada para comunicacao com TJ-MS.

Todas as variaveis de ambiente relacionadas ao TJ-MS sao lidas aqui.
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TJMSConfig:
    """Configuracao centralizada para comunicacao com TJ-MS."""

    # URLs dos proxies
    proxy_local_url: str = ""      # Seu PC via ngrok (para Playwright/subconta)
    proxy_flyio_url: str = ""      # Fly.io (para SOAP - mais rapido)

    # Credenciais SOAP (MNI)
    soap_user: str = ""
    soap_pass: str = ""

    # Credenciais Web (Subconta - Playwright)
    web_user: str = ""
    web_pass: str = ""

    # Timeouts padrao
    soap_timeout: float = 60.0
    download_timeout: float = 180.0
    subconta_timeout: float = 180.0

    # Configuracoes de retry
    max_retries: int = 3
    retry_backoff: float = 0.5

    # Configuracoes de batch download
    default_batch_size: int = 5
    default_max_paralelo: int = 4

    @classmethod
    def from_env(cls) -> "TJMSConfig":
        """Carrega configuracao das variaveis de ambiente."""
        config = cls(
            proxy_local_url=os.getenv("TJMS_PROXY_LOCAL_URL", "").strip().rstrip("/"),
            proxy_flyio_url=os.getenv("TJMS_PROXY_URL", "").strip().rstrip("/"),
            soap_user=(
                os.getenv("MNI_USER", "") or
                os.getenv("TJ_USER", "") or
                os.getenv("TJ_WS_USER", "") or
                os.getenv("WS_USER", "")
            ),
            soap_pass=(
                os.getenv("MNI_PASS", "") or
                os.getenv("TJ_PASS", "") or
                os.getenv("TJ_WS_PASS", "") or
                os.getenv("WS_PASS", "")
            ),
            web_user=os.getenv("TJMS_USUARIO", ""),
            web_pass=os.getenv("TJMS_SENHA", ""),
            soap_timeout=float(os.getenv("TJMS_SOAP_TIMEOUT", "60")),
            download_timeout=float(os.getenv("TJMS_DOWNLOAD_TIMEOUT", "180")),
            subconta_timeout=float(os.getenv("TJMS_SUBCONTA_TIMEOUT", "180")),
            max_retries=int(os.getenv("TJMS_MAX_RETRIES", "3")),
            retry_backoff=float(os.getenv("TJMS_RETRY_BACKOFF", "0.5")),
            default_batch_size=int(os.getenv("TJMS_BATCH_SIZE", "5")),
            default_max_paralelo=int(os.getenv("TJMS_MAX_PARALELO", "4")),
        )

        # Log de configuracao (sem senhas)
        logger.info(
            f"TJMSConfig carregado: proxy_flyio={bool(config.proxy_flyio_url)}, "
            f"proxy_local={bool(config.proxy_local_url)}, "
            f"soap_user={bool(config.soap_user)}"
        )

        return config

    @property
    def soap_url(self) -> str:
        """URL do endpoint SOAP (usa Fly.io por padrao - mais rapido)."""
        if self.proxy_flyio_url:
            return f"{self.proxy_flyio_url}/soap"
        if self.proxy_local_url:
            return f"{self.proxy_local_url}/soap"
        # Fallback direto (provavelmente sera bloqueado em producao)
        logger.warning("Usando URL SOAP direta - pode ser bloqueado pelo TJ-MS")
        return "https://esaj.tjms.jus.br/mniws/servico-intercomunicacao-2.2.2/intercomunicacao"

    @property
    def subconta_endpoint(self) -> Optional[str]:
        """URL do endpoint /extrair-subconta (usa proxy local - Playwright)."""
        if self.proxy_local_url:
            return f"{self.proxy_local_url}/extrair-subconta"
        return None

    def validate(self) -> tuple[bool, list[str]]:
        """Valida se a configuracao esta completa."""
        errors = []

        if not self.soap_user:
            errors.append("Credencial SOAP (MNI_USER/TJ_WS_USER) nao configurada")
        if not self.soap_pass:
            errors.append("Credencial SOAP (MNI_PASS/TJ_WS_PASS) nao configurada")
        if not self.proxy_flyio_url and not self.proxy_local_url:
            errors.append("Nenhum proxy configurado (TJMS_PROXY_URL ou TJMS_PROXY_LOCAL_URL)")

        return len(errors) == 0, errors


# Instancia global (singleton)
_config: Optional[TJMSConfig] = None


def get_config() -> TJMSConfig:
    """Obtem configuracao global (singleton)."""
    global _config
    if _config is None:
        _config = TJMSConfig.from_env()
    return _config


def reload_config() -> TJMSConfig:
    """Recarrega configuracao das variaveis de ambiente."""
    global _config
    _config = TJMSConfig.from_env()
    return _config
