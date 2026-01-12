# utils/cache.py
# -*- coding: utf-8 -*-
"""
Sistema de cache em memória para o Portal PGE-MS

PERFORMANCE: Este módulo implementa caching para dados que raramente mudam
mas são consultados frequentemente, como prompts e configurações.

Uso:
    from utils.cache import config_cache, prompt_cache

    # Cache de configurações
    value = config_cache.get("sistema", "chave", lambda: fetch_from_db())

    # Invalidar cache
    config_cache.invalidate("sistema", "chave")
    config_cache.invalidate_all()
"""

import time
import logging
import threading
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TTLCache:
    """
    Cache em memória com TTL (Time-To-Live).

    Thread-safe e com suporte a invalidação parcial ou total.

    Attributes:
        default_ttl: Tempo de vida padrão dos itens em segundos
        max_size: Número máximo de itens no cache
    """

    def __init__(self, default_ttl: int = 3600, max_size: int = 1000):
        """
        Inicializa o cache.

        Args:
            default_ttl: TTL padrão em segundos (default: 1 hora)
            max_size: Tamanho máximo do cache (default: 1000 itens)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._hits = 0
        self._misses = 0

    def _make_key(self, *parts: str) -> str:
        """Gera chave única a partir das partes."""
        return ":".join(str(p) for p in parts)

    def get(
        self,
        *key_parts: str,
        loader: Optional[Callable[[], T]] = None,
        ttl: Optional[int] = None
    ) -> Optional[T]:
        """
        Obtém valor do cache ou carrega se não existir.

        Args:
            *key_parts: Partes da chave (ex: "sistema", "chave")
            loader: Função para carregar o valor se não estiver em cache
            ttl: TTL específico para este item (opcional)

        Returns:
            Valor do cache ou None se não encontrado e sem loader
        """
        key = self._make_key(*key_parts)

        with self._lock:
            # Verifica se existe e não expirou
            if key in self._cache:
                entry = self._cache[key]
                if entry["expires"] > time.time():
                    self._hits += 1
                    return entry["value"]
                else:
                    # Expirado - remove
                    del self._cache[key]

            self._misses += 1

            # Se tem loader, carrega o valor
            if loader is not None:
                try:
                    value = loader()
                    self.set(*key_parts, value=value, ttl=ttl)
                    return value
                except Exception as e:
                    logger.warning(f"Erro ao carregar cache para {key}: {e}")
                    return None

            return None

    def set(self, *key_parts: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        Define valor no cache.

        Args:
            *key_parts: Partes da chave
            value: Valor a armazenar
            ttl: TTL em segundos (usa default se não especificado)
        """
        key = self._make_key(*key_parts)
        expires = time.time() + (ttl or self.default_ttl)

        with self._lock:
            # PERFORMANCE: Limpa itens expirados se cache cheio
            if len(self._cache) >= self.max_size:
                self._cleanup_expired()

            # Se ainda cheio após limpeza, remove o mais antigo
            if len(self._cache) >= self.max_size:
                oldest_key = min(
                    self._cache.keys(),
                    key=lambda k: self._cache[k]["expires"]
                )
                del self._cache[oldest_key]

            self._cache[key] = {
                "value": value,
                "expires": expires,
                "created": time.time()
            }

    def invalidate(self, *key_parts: str) -> bool:
        """
        Invalida uma entrada específica do cache.

        Args:
            *key_parts: Partes da chave a invalidar

        Returns:
            True se a chave existia e foi removida
        """
        key = self._make_key(*key_parts)

        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache invalidado: {key}")
                return True
            return False

    def invalidate_prefix(self, *prefix_parts: str) -> int:
        """
        Invalida todas as entradas com um prefixo.

        Args:
            *prefix_parts: Partes do prefixo

        Returns:
            Número de entradas removidas
        """
        prefix = self._make_key(*prefix_parts)
        removed = 0

        with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]
                removed += 1

        if removed > 0:
            logger.debug(f"Cache invalidado por prefixo '{prefix}': {removed} itens")

        return removed

    def invalidate_all(self) -> int:
        """
        Limpa todo o cache.

        Returns:
            Número de entradas removidas
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache completamente invalidado: {count} itens")
            return count

    def _cleanup_expired(self) -> int:
        """Remove entradas expiradas. Deve ser chamado com lock."""
        now = time.time()
        expired_keys = [k for k, v in self._cache.items() if v["expires"] <= now]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    def stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do cache.

        Returns:
            Dicionário com estatísticas
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.1f}%",
                "default_ttl": self.default_ttl,
            }


# ==================================================
# INSTÂNCIAS GLOBAIS DE CACHE
# ==================================================

# Cache para configurações do sistema (TTL: 5 minutos)
# Configurações mudam pouco, então cache curto é suficiente
config_cache = TTLCache(default_ttl=300, max_size=500)

# Cache para prompts (TTL: 15 minutos)
# Prompts são mais estáveis, podem ter TTL maior
prompt_cache = TTLCache(default_ttl=900, max_size=200)

# Cache para resultados de consultas frequentes (TTL: 1 minuto)
# Para dados que mudam mais frequentemente
query_cache = TTLCache(default_ttl=60, max_size=100)


# ==================================================
# HELPERS PARA CONFIGURAÇÕES
# ==================================================

def get_cached_config(sistema: str, chave: str, loader: Callable[[], str]) -> Optional[str]:
    """
    Obtém configuração do cache ou carrega do banco.

    Args:
        sistema: Nome do sistema (ex: "gerador_pecas")
        chave: Chave da configuração
        loader: Função para carregar do banco

    Returns:
        Valor da configuração ou None
    """
    return config_cache.get(sistema, chave, loader=loader)


def invalidate_config_cache(sistema: Optional[str] = None) -> int:
    """
    Invalida cache de configurações.

    Args:
        sistema: Se especificado, invalida apenas deste sistema

    Returns:
        Número de entradas removidas
    """
    if sistema:
        return config_cache.invalidate_prefix(sistema)
    return config_cache.invalidate_all()


def get_cached_prompt(sistema: str, tipo: str, loader: Callable[[], str]) -> Optional[str]:
    """
    Obtém prompt do cache ou carrega do banco.

    Args:
        sistema: Nome do sistema
        tipo: Tipo do prompt
        loader: Função para carregar do banco

    Returns:
        Conteúdo do prompt ou None
    """
    return prompt_cache.get(sistema, tipo, loader=loader)


def invalidate_prompt_cache(sistema: Optional[str] = None) -> int:
    """
    Invalida cache de prompts.

    Args:
        sistema: Se especificado, invalida apenas deste sistema

    Returns:
        Número de entradas removidas
    """
    if sistema:
        return prompt_cache.invalidate_prefix(sistema)
    return prompt_cache.invalidate_all()
