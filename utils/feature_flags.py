# utils/feature_flags.py
"""
Sistema simples de Feature Flags para o Portal PGE-MS.

Permite habilitar/desabilitar funcionalidades sem deploy:
- Via variáveis de ambiente
- Via banco de dados (PostgreSQL)
- Com cache para performance

USO:
    from utils.feature_flags import is_feature_enabled, get_feature_flags

    # Verifica se feature está habilitada
    if is_feature_enabled("novo_gerador_pecas"):
        # Usa nova implementação
        ...

    # Com fallback
    if is_feature_enabled("beta_feature", default=False):
        ...

    # Para usuários específicos
    if is_feature_enabled("admin_only", user_id=current_user.id):
        ...

Autor: LAB/PGE-MS
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional, Set

# Tenta usar logging estruturado
try:
    from utils.logging_config import get_logger
    logger = get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class FeatureFlag:
    """Definição de uma feature flag."""
    name: str
    enabled: bool = False
    description: str = ""
    # Restrições
    allowed_users: Optional[Set[int]] = None  # Se definido, só esses users podem usar
    allowed_roles: Optional[Set[str]] = None  # Se definido, só essas roles podem usar
    percentage: float = 100.0  # Percentual de rollout (0-100)
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    source: str = "code"  # "code", "env", "database"


class FeatureFlagStore:
    """
    Armazenamento e gerenciamento de feature flags.

    Fontes de flags (em ordem de prioridade):
    1. Variáveis de ambiente (FF_<NOME>=true/false)
    2. Banco de dados (tabela feature_flags)
    3. Defaults no código
    """

    def __init__(self, cache_ttl_seconds: int = 60):
        self._flags: Dict[str, FeatureFlag] = {}
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._last_db_load: Optional[datetime] = None
        self._lock = Lock()

        # Carrega flags do ambiente na inicialização
        self._load_from_env()

    def _load_from_env(self):
        """Carrega feature flags de variáveis de ambiente."""
        prefix = "FF_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                flag_name = key[len(prefix):].lower()
                enabled = value.lower() in ("true", "1", "yes", "on")

                self._flags[flag_name] = FeatureFlag(
                    name=flag_name,
                    enabled=enabled,
                    source="env"
                )
                logger.debug(f"[FeatureFlag] Loaded from env: {flag_name}={enabled}")

    def _load_from_db(self, force: bool = False):
        """
        Carrega feature flags do banco de dados.

        Usa cache para evitar queries frequentes.
        """
        now = datetime.utcnow()

        # Verifica cache
        if not force and self._last_db_load:
            if now - self._last_db_load < self._cache_ttl:
                return

        try:
            from database.connection import SessionLocal
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Verifica se tabela existe
                result = db.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'feature_flags'
                    )
                """)).scalar()

                if not result:
                    self._last_db_load = now
                    return

                # Carrega flags
                rows = db.execute(text("""
                    SELECT name, enabled, description, allowed_users,
                           allowed_roles, percentage, created_at, updated_at
                    FROM feature_flags
                    WHERE deleted_at IS NULL
                """)).fetchall()

                for row in rows:
                    flag_name = row[0]

                    # Env tem prioridade - não sobrescreve
                    if flag_name in self._flags and self._flags[flag_name].source == "env":
                        continue

                    allowed_users = set(row[3]) if row[3] else None
                    allowed_roles = set(row[4]) if row[4] else None

                    self._flags[flag_name] = FeatureFlag(
                        name=flag_name,
                        enabled=row[1],
                        description=row[2] or "",
                        allowed_users=allowed_users,
                        allowed_roles=allowed_roles,
                        percentage=row[5] or 100.0,
                        created_at=row[6],
                        updated_at=row[7],
                        source="database"
                    )

                self._last_db_load = now
                logger.debug(f"[FeatureFlag] Loaded {len(rows)} flags from database")

            finally:
                db.close()

        except Exception as e:
            logger.warning(f"[FeatureFlag] Failed to load from database: {e}")
            self._last_db_load = now  # Evita retry imediato

    def register(
        self,
        name: str,
        enabled: bool = False,
        description: str = "",
        allowed_users: List[int] = None,
        allowed_roles: List[str] = None,
        percentage: float = 100.0
    ):
        """
        Registra uma feature flag no código.

        Flags do ambiente e banco têm prioridade sobre registro no código.

        Args:
            name: Nome único da flag
            enabled: Estado padrão
            description: Descrição da funcionalidade
            allowed_users: Lista de user_ids permitidos
            allowed_roles: Lista de roles permitidas
            percentage: Percentual de rollout (0-100)
        """
        with self._lock:
            # Não sobrescreve se já existe de env ou db
            if name in self._flags and self._flags[name].source != "code":
                return

            self._flags[name] = FeatureFlag(
                name=name,
                enabled=enabled,
                description=description,
                allowed_users=set(allowed_users) if allowed_users else None,
                allowed_roles=set(allowed_roles) if allowed_roles else None,
                percentage=percentage,
                source="code"
            )

    def is_enabled(
        self,
        name: str,
        default: bool = False,
        user_id: int = None,
        user_role: str = None
    ) -> bool:
        """
        Verifica se uma feature flag está habilitada.

        Args:
            name: Nome da flag
            default: Valor padrão se flag não existe
            user_id: ID do usuário (para flags com restrição por usuário)
            user_role: Role do usuário (para flags com restrição por role)

        Returns:
            True se habilitada, False caso contrário
        """
        with self._lock:
            # Tenta carregar do banco periodicamente
            self._load_from_db()

            flag = self._flags.get(name)

            if flag is None:
                return default

            if not flag.enabled:
                return False

            # Verifica restrição por usuário
            if flag.allowed_users is not None:
                if user_id is None or user_id not in flag.allowed_users:
                    return False

            # Verifica restrição por role
            if flag.allowed_roles is not None:
                if user_role is None or user_role not in flag.allowed_roles:
                    return False

            # Verifica percentual de rollout
            if flag.percentage < 100.0 and user_id is not None:
                # Usa hash do user_id para determinismo
                hash_value = hash(f"{name}:{user_id}") % 100
                if hash_value >= flag.percentage:
                    return False

            return True

    def get_all(self) -> Dict[str, dict]:
        """Retorna todas as flags registradas."""
        with self._lock:
            self._load_from_db()

            return {
                name: {
                    "enabled": flag.enabled,
                    "description": flag.description,
                    "source": flag.source,
                    "percentage": flag.percentage,
                    "has_user_restriction": flag.allowed_users is not None,
                    "has_role_restriction": flag.allowed_roles is not None,
                }
                for name, flag in self._flags.items()
            }

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """
        Altera estado de uma flag em memória.

        NOTA: Para persistir, use a API do banco de dados.

        Args:
            name: Nome da flag
            enabled: Novo estado

        Returns:
            True se alterado, False se flag não existe
        """
        with self._lock:
            if name not in self._flags:
                return False

            self._flags[name].enabled = enabled
            self._flags[name].updated_at = datetime.utcnow()
            logger.info(f"[FeatureFlag] {name} set to {enabled}")
            return True

    def refresh(self):
        """Força recarga das flags do banco de dados."""
        with self._lock:
            self._load_from_db(force=True)


# Instância global singleton
_store: Optional[FeatureFlagStore] = None


def get_feature_flag_store() -> FeatureFlagStore:
    """Retorna o store singleton de feature flags."""
    global _store
    if _store is None:
        _store = FeatureFlagStore()
    return _store


def is_feature_enabled(
    name: str,
    default: bool = False,
    user_id: int = None,
    user_role: str = None
) -> bool:
    """
    Verifica se uma feature está habilitada.

    Args:
        name: Nome da feature flag
        default: Valor padrão se não definida
        user_id: ID do usuário para flags restritas
        user_role: Role do usuário para flags restritas

    Returns:
        True se habilitada

    Exemplo:
        if is_feature_enabled("novo_layout"):
            render_new_layout()
        else:
            render_old_layout()
    """
    return get_feature_flag_store().is_enabled(name, default, user_id, user_role)


def register_feature(
    name: str,
    enabled: bool = False,
    description: str = ""
):
    """
    Registra uma feature flag no código.

    Chame esta função no início da aplicação para definir flags padrão.

    Args:
        name: Nome único da flag
        enabled: Estado padrão
        description: Descrição da funcionalidade
    """
    get_feature_flag_store().register(name, enabled, description)


def get_feature_flags() -> Dict[str, dict]:
    """
    Retorna todas as feature flags.

    Útil para endpoint admin de visualização.
    """
    return get_feature_flag_store().get_all()


# ============================================
# FEATURE FLAGS PADRÃO DO SISTEMA
# ============================================

def setup_default_flags():
    """
    Configura feature flags padrão do sistema.

    Chame no startup da aplicação.
    """
    store = get_feature_flag_store()

    # Flags de funcionalidades
    store.register(
        "streaming_sse",
        enabled=True,
        description="Habilita streaming SSE para geração de peças"
    )

    store.register(
        "circuit_breaker",
        enabled=True,
        description="Habilita circuit breaker para APIs externas"
    )

    store.register(
        "structured_logging",
        enabled=True,
        description="Usa logs estruturados com structlog"
    )

    store.register(
        "brute_force_protection",
        enabled=True,
        description="Proteção contra brute force no login"
    )

    # Flags de beta/experimental
    store.register(
        "beta_gemini_3_pro",
        enabled=False,
        description="Usa Gemini 3 Pro para todas as gerações"
    )

    store.register(
        "experimental_embeddings",
        enabled=False,
        description="Usa novo sistema de embeddings vetoriais"
    )

    logger.info("[FeatureFlag] Default flags registered")


__all__ = [
    # Classes
    "FeatureFlag",
    "FeatureFlagStore",
    # Funções principais
    "is_feature_enabled",
    "register_feature",
    "get_feature_flags",
    "get_feature_flag_store",
    # Setup
    "setup_default_flags",
]
