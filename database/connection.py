# database/connection.py
"""
Configuração da conexão com o banco de dados usando SQLAlchemy 2.0
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool, NullPool
from typing import Generator

from config import DATABASE_URL

# Configuração do engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},  # Necessário para SQLite
        echo=False
    )
else:
    # PostgreSQL - configuração otimizada para produção
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,  # Recicla conexões a cada 30 min
        pool_pre_ping=True  # Verifica conexão antes de usar
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base para os models
Base = declarative_base()


def get_db() -> Generator:
    """
    Dependency que fornece uma sessão do banco de dados.
    Uso: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
