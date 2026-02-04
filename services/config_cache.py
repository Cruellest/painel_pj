# services/config_cache.py
"""
Cache de configuracoes do sistema.

Cacheia consultas repetidas ao banco de dados para:
- ConfiguracaoIA (configuracoes do sistema)
- PromptModulo (modulos de prompts)
- Filtros de categorias

O cache tem TTL configuravel e invalidacao segura.

Uso:
    from services.config_cache import config_cache

    # Obter configuracao com cache
    modelo = config_cache.get_config("gerador_pecas", "modelo_geracao", db)

    # Limpar cache (apos alteracoes admin)
    config_cache.invalidate_all()

Autor: LAB/PGE-MS
"""

import time
import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Entrada do cache com TTL"""
    value: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class ConfigCache:
    """
    Cache thread-safe para configuracoes do sistema.

    Features:
    - TTL configuravel por tipo de dado
    - Invalidacao por chave ou total
    - Estatisticas de hit/miss
    - Limpeza automatica de entradas expiradas
    """

    # TTLs padrao (em segundos)
    DEFAULT_TTL = 300  # 5 minutos
    CONFIG_TTL = 60    # 1 minuto para ConfiguracaoIA
    PROMPT_TTL = 300   # 5 minutos para PromptModulo
    FILTER_TTL = 300   # 5 minutos para filtros de categorias

    def __init__(self, max_size: int = 500):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
        self._max_size = max_size
        self._stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0
        }

    def _make_key(self, *parts) -> str:
        """Cria chave de cache a partir de partes"""
        key_str = ":".join(str(p) for p in parts)
        return hashlib.md5(key_str.encode()).hexdigest()[:16]

    def get(self, key: str) -> Tuple[bool, Any]:
        """
        Busca valor no cache.

        Returns:
            Tuple[found: bool, value: Any]
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return False, None

            if entry.is_expired:
                del self._cache[key]
                self._stats["misses"] += 1
                return False, None

            self._stats["hits"] += 1
            return True, entry.value

    def set(self, key: str, value: Any, ttl: float = None):
        """
        Armazena valor no cache.

        Args:
            key: Chave do cache
            value: Valor a armazenar
            ttl: Tempo de vida em segundos (padrao: DEFAULT_TTL)
        """
        if ttl is None:
            ttl = self.DEFAULT_TTL

        with self._lock:
            # Limpa entradas antigas se necessario
            if len(self._cache) >= self._max_size:
                self._cleanup_expired()

            self._cache[key] = CacheEntry(
                value=value,
                expires_at=time.time() + ttl
            )

    def invalidate(self, key: str):
        """Remove uma entrada especifica do cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats["invalidations"] += 1

    def invalidate_prefix(self, prefix: str):
        """Remove todas as entradas que comecam com o prefixo"""
        with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]
                self._stats["invalidations"] += 1

    def invalidate_all(self):
        """Remove todas as entradas do cache"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats["invalidations"] += count
            logger.info(f"[ConfigCache] Cache limpo: {count} entradas removidas")

    def _cleanup_expired(self):
        """Remove entradas expiradas (chamado com lock)"""
        now = time.time()
        expired_keys = [k for k, v in self._cache.items() if v.expires_at < now]
        for key in expired_keys:
            del self._cache[key]

    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatisticas do cache"""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                self._stats["hits"] / total_requests * 100
                if total_requests > 0 else 0
            )
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": round(hit_rate, 1),
                "invalidations": self._stats["invalidations"]
            }

    # ============================
    # Metodos de conveniencia
    # ============================

    def get_config(
        self,
        sistema: str,
        chave: str,
        db,
        default: str = None
    ) -> Optional[str]:
        """
        Obtem ConfiguracaoIA com cache.

        Args:
            sistema: Nome do sistema (ex: "gerador_pecas")
            chave: Chave da configuracao (ex: "modelo_geracao")
            db: Sessao do banco de dados
            default: Valor padrao se nao encontrar

        Returns:
            Valor da configuracao ou default
        """
        cache_key = f"config:{sistema}:{chave}"
        found, value = self.get(cache_key)

        if found:
            return value if value is not None else default

        # Busca no banco
        from admin.models import ConfiguracaoIA
        config = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == sistema,
            ConfiguracaoIA.chave == chave
        ).first()

        valor = config.valor if config else None
        self.set(cache_key, valor, ttl=self.CONFIG_TTL)

        return valor if valor is not None else default

    def get_prompt_modulos(
        self,
        group_id: int,
        subcategoria_ids: List[int],
        db
    ) -> List:
        """
        Obtem PromptModulo ativos com cache.

        Args:
            group_id: ID do grupo de prompts
            subcategoria_ids: Lista de IDs de subcategorias
            db: Sessao do banco

        Returns:
            Lista de PromptModulo
        """
        # Cria chave baseada nos parametros
        sub_key = ",".join(map(str, sorted(subcategoria_ids))) if subcategoria_ids else "none"
        cache_key = f"modulos:{group_id}:{sub_key}"

        found, value = self.get(cache_key)
        if found:
            return value

        # Busca no banco
        from admin.models_prompt_modules import PromptModulo

        query = db.query(PromptModulo).filter(
            PromptModulo.group_id == group_id,
            PromptModulo.is_active == True
        )

        if subcategoria_ids:
            from admin.models_prompt_groups import PromptSubcategoria
            subcat_slugs = db.query(PromptSubcategoria.slug).filter(
                PromptSubcategoria.id.in_(subcategoria_ids)
            ).all()
            subcat_slugs = [s[0] for s in subcat_slugs]

            if subcat_slugs:
                from sqlalchemy import or_
                query = query.filter(
                    or_(
                        PromptModulo.subcategoria_slug == None,
                        PromptModulo.subcategoria_slug.in_(subcat_slugs)
                    )
                )

        modulos = query.order_by(PromptModulo.order).all()
        self.set(cache_key, modulos, ttl=self.PROMPT_TTL)

        return modulos

    def get_filtro_categorias(
        self,
        tipo_peca: str,
        db
    ) -> Tuple[set, set]:
        """
        Obtem codigos de categorias permitidas com cache.

        Args:
            tipo_peca: Tipo de peca (ex: "contestacao")
            db: Sessao do banco

        Returns:
            Tuple[codigos_permitidos: set, codigos_primeiro_doc: set]
        """
        cache_key = f"filtro:{tipo_peca}"

        found, value = self.get(cache_key)
        if found:
            return value

        # Busca no banco
        from sistemas.gerador_pecas.filtro_categorias import FiltroCategoriasDocumento
        filtro = FiltroCategoriasDocumento(db)

        if filtro.tem_configuracao():
            codigos = filtro.get_codigos_permitidos(tipo_peca)
            codigos_primeiro = filtro.get_codigos_primeiro_documento(tipo_peca)
        else:
            codigos = None
            codigos_primeiro = set()

        result = (codigos, codigos_primeiro)
        self.set(cache_key, result, ttl=self.FILTER_TTL)

        return result

    def get_auto_detection_enabled(self, db) -> bool:
        """
        Verifica se deteccao automatica de tipo de peca esta habilitada.
        """
        valor = self.get_config(
            "gerador_pecas",
            "enable_auto_piece_detection",
            db,
            default="false"
        )
        return valor.lower() == "true" if valor else False


# Instancia global do cache
config_cache = ConfigCache()


# Exports
__all__ = [
    "ConfigCache",
    "config_cache",
]
