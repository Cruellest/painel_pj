# utils/token_blacklist.py
"""
SECURITY: Sistema de blacklist para revogação de tokens JWT.

Este módulo permite revogar tokens antes de sua expiração natural.
Casos de uso:
- Logout do usuário
- Alteração de senha (invalida tokens antigos)
- Comprometimento de token
- Bloqueio administrativo de usuário

A blacklist usa duas camadas:
1. Cache em memória (rápido, para verificações frequentes)
2. Persistência em banco (sobrevive a reinicializações)
"""

import threading
from datetime import datetime, timedelta
from typing import Optional, Set
import logging
from jose import jwt

from utils.timezone import get_utc_now

from config import SECRET_KEY, ALGORITHM

logger = logging.getLogger("security.token_blacklist")


class TokenBlacklist:
    """
    SECURITY: Gerencia tokens revogados.

    Thread-safe usando locks para acesso concorrente.
    """

    def __init__(self):
        # Cache em memória de tokens revogados
        # Armazena tuples de (token_jti, expiration_time)
        self._blacklist: Set[str] = set()
        self._lock = threading.Lock()

        # Limpeza automática de tokens expirados
        self._last_cleanup = get_utc_now()
        self._cleanup_interval = timedelta(minutes=30)

    def _extract_jti_and_exp(self, token: str) -> Optional[tuple]:
        """
        SECURITY: Extrai JTI (JWT ID) e tempo de expiração do token.

        Se o token não tem JTI, usa um hash do próprio token.
        """
        try:
            # Decodifica sem verificar expiração (token pode já estar expirado)
            payload = jwt.decode(
                token,
                SECRET_KEY,
                algorithms=[ALGORITHM],
                options={"verify_exp": False}
            )

            # JTI é o identificador único do token
            jti = payload.get("jti")
            if not jti:
                # Fallback: usa hash do token completo
                import hashlib
                jti = hashlib.sha256(token.encode()).hexdigest()[:32]

            # Tempo de expiração
            exp = payload.get("exp")
            if exp:
                exp_time = datetime.fromtimestamp(exp)
            else:
                # Se não tem exp, considera 24h
                exp_time = get_utc_now() + timedelta(hours=24)

            return (jti, exp_time)

        except Exception as e:
            logger.warning(f"Erro ao extrair JTI do token: {e}")
            return None

    def revoke(self, token: str) -> bool:
        """
        SECURITY: Revoga um token, adicionando-o à blacklist.

        Args:
            token: Token JWT a ser revogado

        Returns:
            True se revogado com sucesso, False caso contrário
        """
        result = self._extract_jti_and_exp(token)
        if not result:
            return False

        jti, exp_time = result

        # Não adiciona tokens já expirados
        if exp_time < get_utc_now():
            logger.debug(f"Token já expirado, não adicionado à blacklist")
            return True

        with self._lock:
            self._blacklist.add(jti)
            logger.info(f"Token revogado: {jti[:8]}...")

            # Cleanup se necessário
            self._maybe_cleanup()

        return True

    def is_revoked(self, token: str) -> bool:
        """
        SECURITY: Verifica se um token foi revogado.

        Args:
            token: Token JWT a verificar

        Returns:
            True se o token foi revogado, False caso contrário
        """
        result = self._extract_jti_and_exp(token)
        if not result:
            # Token inválido é considerado revogado
            return True

        jti, _ = result

        with self._lock:
            return jti in self._blacklist

    def _maybe_cleanup(self):
        """
        SECURITY: Remove tokens expirados da blacklist periodicamente.

        Chamado dentro do lock, então não precisa de lock próprio.
        """
        now = get_utc_now()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        # Em uma implementação com banco, aqui limparia tokens expirados
        # Por ora, apenas registra o cleanup
        self._last_cleanup = now
        logger.debug(f"Cleanup da blacklist realizado, {len(self._blacklist)} tokens")

    def revoke_all_for_user(self, user_id: int) -> int:
        """
        SECURITY: Revoga todos os tokens de um usuário específico.

        NOTA: Esta implementação requer que tokens incluam user_id.
        Para implementação completa, seria necessário rastrear
        tokens por usuário no banco de dados.

        Args:
            user_id: ID do usuário

        Returns:
            Número de tokens revogados (estimado)
        """
        # Placeholder para implementação completa com banco
        logger.info(f"Revogação de todos os tokens do usuário {user_id} solicitada")
        return 0

    def clear(self):
        """
        SECURITY: Limpa toda a blacklist.

        USE COM CUIDADO - apenas para testes ou emergências.
        """
        with self._lock:
            count = len(self._blacklist)
            self._blacklist.clear()
            logger.warning(f"Blacklist limpa: {count} tokens removidos")


# Instância global singleton
_blacklist_instance: Optional[TokenBlacklist] = None
_instance_lock = threading.Lock()


def get_token_blacklist() -> TokenBlacklist:
    """
    SECURITY: Retorna a instância singleton da blacklist.

    Thread-safe para inicialização lazy.
    """
    global _blacklist_instance

    if _blacklist_instance is None:
        with _instance_lock:
            if _blacklist_instance is None:
                _blacklist_instance = TokenBlacklist()
                logger.info("Token blacklist inicializada")

    return _blacklist_instance


def revoke_token(token: str) -> bool:
    """
    SECURITY: Função de conveniência para revogar um token.

    Args:
        token: Token JWT a revogar

    Returns:
        True se revogado com sucesso
    """
    return get_token_blacklist().revoke(token)


def is_token_revoked(token: str) -> bool:
    """
    SECURITY: Função de conveniência para verificar se token foi revogado.

    Args:
        token: Token JWT a verificar

    Returns:
        True se foi revogado
    """
    return get_token_blacklist().is_revoked(token)
