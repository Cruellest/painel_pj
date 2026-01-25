# utils/brute_force.py
"""
SECURITY: Proteção contra ataques de força bruta.

Implementa:
- Tracking de tentativas de login falhas por IP e username
- Delays progressivos após falhas
- Bloqueio temporário após muitas tentativas
- Integração com audit log

USO:
    from utils.brute_force import BruteForceProtection, check_brute_force

    # No endpoint de login
    protection = check_brute_force(username, ip_address)
    if protection.is_blocked:
        raise HTTPException(
            status_code=429,
            detail=f"Muitas tentativas. Aguarde {protection.retry_after} segundos."
        )

    # Após login falho
    protection.record_failure()

    # Após login bem sucedido
    protection.record_success()

Autor: LAB/PGE-MS
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional, Tuple

# Tenta usar logging estruturado
try:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class AttemptRecord:
    """Registro de tentativas de login."""
    failures: int = 0
    last_failure: Optional[float] = None
    blocked_until: Optional[float] = None
    total_failures: int = 0  # Histórico total


@dataclass
class BruteForceConfig:
    """
    Configuração de proteção contra brute force.

    Attributes:
        max_attempts: Tentativas antes de bloquear (default: 5)
        block_duration: Duração do bloqueio em segundos (default: 300 = 5min)
        progressive_delay: Se True, aumenta delay a cada falha (default: True)
        base_delay: Delay base em segundos (default: 1)
        max_delay: Delay máximo em segundos (default: 30)
        cleanup_interval: Intervalo para limpar registros antigos (default: 3600)
        record_ttl: Tempo para manter registros em segundos (default: 86400 = 24h)
    """
    max_attempts: int = 5
    block_duration: float = 300.0  # 5 minutos
    progressive_delay: bool = True
    base_delay: float = 1.0
    max_delay: float = 30.0
    cleanup_interval: float = 3600.0  # 1 hora
    record_ttl: float = 86400.0  # 24 horas


@dataclass
class BruteForceStatus:
    """Status de proteção para uma requisição."""
    is_blocked: bool = False
    retry_after: Optional[float] = None
    attempts_remaining: int = 0
    delay_required: float = 0.0
    message: Optional[str] = None


class BruteForceProtection:
    """
    Proteção contra ataques de força bruta.

    Rastreia tentativas por:
    - IP: Bloqueia IPs que fazem muitas tentativas
    - Username: Bloqueia usuários específicos
    - Combinação IP+Username: Proteção mais granular
    """

    def __init__(self, config: BruteForceConfig = None):
        self._config = config or BruteForceConfig()
        self._ip_attempts: Dict[str, AttemptRecord] = {}
        self._user_attempts: Dict[str, AttemptRecord] = {}
        self._lock = Lock()
        self._last_cleanup = time.time()

    def check(
        self,
        ip_address: str,
        username: str = None
    ) -> BruteForceStatus:
        """
        Verifica se a requisição deve ser bloqueada.

        Args:
            ip_address: IP do cliente
            username: Nome de usuário (opcional, para proteção por usuário)

        Returns:
            BruteForceStatus com informações sobre bloqueio
        """
        with self._lock:
            self._maybe_cleanup()

            now = time.time()

            # Verifica bloqueio por IP
            ip_record = self._ip_attempts.get(ip_address)
            if ip_record and ip_record.blocked_until:
                if now < ip_record.blocked_until:
                    retry_after = ip_record.blocked_until - now
                    return BruteForceStatus(
                        is_blocked=True,
                        retry_after=retry_after,
                        message=f"IP bloqueado por muitas tentativas. Aguarde {int(retry_after)} segundos."
                    )
                else:
                    # Bloqueio expirou, reseta
                    ip_record.blocked_until = None
                    ip_record.failures = 0

            # Verifica bloqueio por usuário
            if username:
                user_record = self._user_attempts.get(username)
                if user_record and user_record.blocked_until:
                    if now < user_record.blocked_until:
                        retry_after = user_record.blocked_until - now
                        return BruteForceStatus(
                            is_blocked=True,
                            retry_after=retry_after,
                            message=f"Conta bloqueada por muitas tentativas. Aguarde {int(retry_after)} segundos."
                        )
                    else:
                        user_record.blocked_until = None
                        user_record.failures = 0

            # Calcula delay progressivo baseado em falhas recentes
            delay = 0.0
            if self._config.progressive_delay:
                failures = 0
                if ip_record:
                    failures = max(failures, ip_record.failures)
                if username and username in self._user_attempts:
                    failures = max(failures, self._user_attempts[username].failures)

                if failures > 0:
                    delay = min(
                        self._config.base_delay * (2 ** (failures - 1)),
                        self._config.max_delay
                    )

            # Calcula tentativas restantes
            ip_failures = ip_record.failures if ip_record else 0
            attempts_remaining = max(0, self._config.max_attempts - ip_failures)

            return BruteForceStatus(
                is_blocked=False,
                attempts_remaining=attempts_remaining,
                delay_required=delay
            )

    def record_failure(
        self,
        ip_address: str,
        username: str = None,
        reason: str = None
    ):
        """
        Registra uma tentativa de login falha.

        Args:
            ip_address: IP do cliente
            username: Nome de usuário
            reason: Motivo da falha (para logging)
        """
        with self._lock:
            now = time.time()

            # Atualiza registro do IP
            if ip_address not in self._ip_attempts:
                self._ip_attempts[ip_address] = AttemptRecord()

            ip_record = self._ip_attempts[ip_address]
            ip_record.failures += 1
            ip_record.total_failures += 1
            ip_record.last_failure = now

            # Verifica se deve bloquear IP
            if ip_record.failures >= self._config.max_attempts:
                ip_record.blocked_until = now + self._config.block_duration
                logger.warning(
                    f"[BruteForce] IP {ip_address} bloqueado por {self._config.block_duration}s "
                    f"após {ip_record.failures} tentativas",
                    ip=ip_address,
                    failures=ip_record.failures,
                    block_duration=self._config.block_duration
                )

            # Atualiza registro do usuário
            if username:
                if username not in self._user_attempts:
                    self._user_attempts[username] = AttemptRecord()

                user_record = self._user_attempts[username]
                user_record.failures += 1
                user_record.total_failures += 1
                user_record.last_failure = now

                # Verifica se deve bloquear usuário
                if user_record.failures >= self._config.max_attempts:
                    user_record.blocked_until = now + self._config.block_duration
                    logger.warning(
                        f"[BruteForce] Usuário '{username}' bloqueado por {self._config.block_duration}s "
                        f"após {user_record.failures} tentativas",
                        username=username,
                        failures=user_record.failures,
                        block_duration=self._config.block_duration
                    )

    def record_success(
        self,
        ip_address: str,
        username: str = None
    ):
        """
        Registra um login bem sucedido.

        Reseta contadores de falha para IP e usuário.

        Args:
            ip_address: IP do cliente
            username: Nome de usuário
        """
        with self._lock:
            # Reseta falhas do IP (mantém histórico)
            if ip_address in self._ip_attempts:
                self._ip_attempts[ip_address].failures = 0
                self._ip_attempts[ip_address].blocked_until = None

            # Reseta falhas do usuário
            if username and username in self._user_attempts:
                self._user_attempts[username].failures = 0
                self._user_attempts[username].blocked_until = None

    def get_stats(self) -> dict:
        """Retorna estatísticas de proteção brute force."""
        with self._lock:
            now = time.time()
            blocked_ips = sum(
                1 for r in self._ip_attempts.values()
                if r.blocked_until and r.blocked_until > now
            )
            blocked_users = sum(
                1 for r in self._user_attempts.values()
                if r.blocked_until and r.blocked_until > now
            )

            return {
                "tracked_ips": len(self._ip_attempts),
                "tracked_users": len(self._user_attempts),
                "blocked_ips": blocked_ips,
                "blocked_users": blocked_users,
                "config": {
                    "max_attempts": self._config.max_attempts,
                    "block_duration": self._config.block_duration,
                }
            }

    def unblock_ip(self, ip_address: str) -> bool:
        """Desbloqueia um IP manualmente."""
        with self._lock:
            if ip_address in self._ip_attempts:
                self._ip_attempts[ip_address].failures = 0
                self._ip_attempts[ip_address].blocked_until = None
                logger.info(f"[BruteForce] IP {ip_address} desbloqueado manualmente")
                return True
            return False

    def unblock_user(self, username: str) -> bool:
        """Desbloqueia um usuário manualmente."""
        with self._lock:
            if username in self._user_attempts:
                self._user_attempts[username].failures = 0
                self._user_attempts[username].blocked_until = None
                logger.info(f"[BruteForce] Usuário '{username}' desbloqueado manualmente")
                return True
            return False

    def _maybe_cleanup(self):
        """Limpa registros antigos periodicamente."""
        now = time.time()
        if now - self._last_cleanup < self._config.cleanup_interval:
            return

        self._last_cleanup = now
        ttl_threshold = now - self._config.record_ttl

        # Limpa IPs antigos
        old_ips = [
            ip for ip, record in self._ip_attempts.items()
            if record.last_failure and record.last_failure < ttl_threshold
        ]
        for ip in old_ips:
            del self._ip_attempts[ip]

        # Limpa usuários antigos
        old_users = [
            user for user, record in self._user_attempts.items()
            if record.last_failure and record.last_failure < ttl_threshold
        ]
        for user in old_users:
            del self._user_attempts[user]

        if old_ips or old_users:
            logger.debug(
                f"[BruteForce] Cleanup: removidos {len(old_ips)} IPs e {len(old_users)} usuários"
            )


# Instância global singleton
_brute_force_protection: Optional[BruteForceProtection] = None


def get_brute_force_protection() -> BruteForceProtection:
    """Retorna instância singleton de proteção brute force."""
    global _brute_force_protection
    if _brute_force_protection is None:
        _brute_force_protection = BruteForceProtection()
    return _brute_force_protection


def check_brute_force(
    ip_address: str,
    username: str = None
) -> BruteForceStatus:
    """
    Função de conveniência para verificar proteção.

    Args:
        ip_address: IP do cliente
        username: Nome de usuário (opcional)

    Returns:
        BruteForceStatus
    """
    return get_brute_force_protection().check(ip_address, username)


def record_login_failure(
    ip_address: str,
    username: str = None,
    reason: str = None
):
    """
    Função de conveniência para registrar falha.

    Args:
        ip_address: IP do cliente
        username: Nome de usuário
        reason: Motivo da falha
    """
    get_brute_force_protection().record_failure(ip_address, username, reason)


def record_login_success(
    ip_address: str,
    username: str = None
):
    """
    Função de conveniência para registrar sucesso.

    Args:
        ip_address: IP do cliente
        username: Nome de usuário
    """
    get_brute_force_protection().record_success(ip_address, username)


__all__ = [
    # Classes
    "BruteForceProtection",
    "BruteForceConfig",
    "BruteForceStatus",
    "AttemptRecord",
    # Funções
    "get_brute_force_protection",
    "check_brute_force",
    "record_login_failure",
    "record_login_success",
]
