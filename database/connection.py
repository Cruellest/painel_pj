# database/connection.py
"""
Configuração da conexão com o banco de dados usando SQLAlchemy 2.0

PERFORMANCE: Este módulo configura o pool de conexões de forma otimizada
para diferentes ambientes (desenvolvimento com SQLite, produção com PostgreSQL).
"""

import os
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool, NullPool, StaticPool
from typing import Generator

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# ==================================================
# CONFIGURAÇÃO DO ENGINE
# ==================================================

# PERFORMANCE: Detecta ambiente para ajustar pool size
IS_PRODUCTION = os.getenv("RAILWAY_ENVIRONMENT") == "production" or os.getenv("ENV") == "production"

if DATABASE_URL.startswith("sqlite"):
    # SQLite - Usa StaticPool para melhor performance em dev
    # NullPool recriaria conexão a cada request (lento)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
        poolclass=StaticPool,  # PERFORMANCE: Reutiliza única conexão em SQLite
    )

    # PERFORMANCE: Habilita WAL mode para SQLite (melhor concorrência)
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.close()

else:
    # PostgreSQL - Configuração otimizada
    # PERFORMANCE: Detecta se é localhost para otimizações mais agressivas
    IS_LOCALHOST = "localhost" in DATABASE_URL or "127.0.0.1" in DATABASE_URL

    if IS_LOCALHOST and not IS_PRODUCTION:
        # LOCALHOST DEV: Pool minimalista e rápido
        engine = create_engine(
            DATABASE_URL,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_timeout=5,
            pool_recycle=3600,
            pool_pre_ping=False,  # PERFORMANCE: Economiza 1 query por conexão
            connect_args={
                "options": "-c timezone=America/Campo_Grande",
                "connect_timeout": 5,
            },
        )
        logger.info("Database pool configurado para LOCALHOST (otimizado)")
    else:
        # PRODUÇÃO/REMOTO: Configuração robusta
        POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20" if IS_PRODUCTION else "10"))
        MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "15" if IS_PRODUCTION else "5"))
        POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "10"))
        POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # 30 min

        engine = create_engine(
            DATABASE_URL,
            echo=False,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_timeout=POOL_TIMEOUT,
            pool_recycle=POOL_RECYCLE,
            pool_pre_ping=True,  # RELIABILITY: Verifica conexão antes de usar
            connect_args={
                "options": "-c timezone=America/Campo_Grande",
            },
        )
        logger.info(
            f"Database pool configurado: size={POOL_SIZE}, overflow={MAX_OVERFLOW}, "
            f"timeout={POOL_TIMEOUT}s, recycle={POOL_RECYCLE}s"
        )


# ==================================================
# SESSION FACTORY
# ==================================================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,  # PERFORMANCE: Evita recarregar objetos após commit
)

# Base para os models
Base = declarative_base()


# ==================================================
# DEPENDENCIES
# ==================================================

def get_db() -> Generator:
    """
    Dependency que fornece uma sessão do banco de dados.

    Uso:
        @router.get("/rota")
        def rota(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """
    Context manager para uso fora de FastAPI (scripts, tasks, etc).

    Uso:
        with get_db_context() as db:
            db.query(Model).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
