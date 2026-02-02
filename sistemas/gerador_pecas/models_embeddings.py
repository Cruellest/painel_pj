# sistemas/gerador_pecas/models_embeddings.py
"""
Modelo para armazenamento de embeddings vetoriais dos módulos de conteúdo.

Suporta:
- pgvector quando disponível (produção)
- Fallback JSON para ambientes sem pgvector (desenvolvimento local)
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean, Index, event
from sqlalchemy.orm import relationship
from database.connection import Base, engine
from utils.timezone import get_utc_now
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

# Dimensão dos embeddings do Google gemini-embedding-001
# Usa Matryoshka (outputDimensionality) para manter 768 dims por compatibilidade
# Modelo suporta 128-3072 dims, mas 768 é suficiente para nosso caso de uso
EMBEDDING_DIMENSION = 768


def check_pgvector_available() -> bool:
    """Verifica se a extensão pgvector está disponível no banco."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'"))
            return result.fetchone() is not None
    except Exception as e:
        logger.warning(f"Erro ao verificar pgvector: {e}")
        return False


def setup_pgvector():
    """Tenta criar a extensão pgvector se disponível."""
    try:
        with engine.connect() as conn:
            # Verifica se está disponível
            result = conn.execute(text(
                "SELECT name FROM pg_available_extensions WHERE name = 'vector'"
            ))
            if result.fetchone():
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
                logger.info("✓ Extensão pgvector criada/verificada com sucesso")
                return True
            else:
                logger.warning("⚠ Extensão pgvector não disponível neste PostgreSQL")
                return False
    except Exception as e:
        logger.warning(f"⚠ Não foi possível criar pgvector: {e}")
        return False


# Tenta detectar pgvector na inicialização
PGVECTOR_AVAILABLE = False


class ModuloEmbedding(Base):
    """
    Armazena embeddings vetoriais dos módulos de conteúdo.

    Os embeddings são gerados a partir do texto combinado:
    - Título
    - Categoria/Subcategoria
    - Condição de ativação
    - Conteúdo (truncado)

    Isso permite busca semântica quando o usuário pede argumentos.
    """

    __tablename__ = "modulo_embeddings"

    id = Column(Integer, primary_key=True, index=True)

    # Referência ao módulo original
    modulo_id = Column(
        Integer,
        ForeignKey("prompt_modulos.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )

    # Texto usado para gerar o embedding (para debug/regeneração)
    texto_embedding = Column(Text, nullable=False)

    # Embedding como JSON (fallback universal)
    # Formato: [0.123, -0.456, ...]
    embedding_json = Column(JSON, nullable=True)

    # Hash do texto para detectar mudanças
    texto_hash = Column(String(64), nullable=False, index=True)

    # Modelo usado para gerar o embedding
    modelo_embedding = Column(String(100), default="text-embedding-004")

    # Dimensão do embedding (para validação)
    dimensao = Column(Integer, default=EMBEDDING_DIMENSION)

    # Status
    ativo = Column(Boolean, default=True)

    # Auditoria
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Nota: Removido relationship para evitar problemas de importação circular
    # Use join manual: db.query(ModuloEmbedding).join(PromptModulo, ...)

    def __repr__(self):
        return f"<ModuloEmbedding(modulo_id={self.modulo_id}, dim={self.dimensao})>"


# Índices
Index("ix_modulo_embeddings_ativo", ModuloEmbedding.ativo)


def add_vector_column_if_pgvector():
    """
    Adiciona coluna vetorial se pgvector estiver disponível.
    Chamado após a criação da tabela.
    """
    global PGVECTOR_AVAILABLE

    try:
        with engine.connect() as conn:
            # Verifica se pgvector está instalado
            result = conn.execute(text("SELECT * FROM pg_extension WHERE extname = 'vector'"))
            if not result.fetchone():
                logger.info("pgvector não instalado - usando fallback JSON")
                return False

            # Verifica se a coluna vetorial já existe
            result = conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'modulo_embeddings' AND column_name = 'embedding_vector'
            """))

            if not result.fetchone():
                # Adiciona coluna vetorial
                conn.execute(text(f"""
                    ALTER TABLE modulo_embeddings
                    ADD COLUMN IF NOT EXISTS embedding_vector vector({EMBEDDING_DIMENSION})
                """))

                # Cria índice HNSW para busca aproximada rápida
                conn.execute(text("""
                    CREATE INDEX IF NOT EXISTS ix_modulo_embeddings_vector
                    ON modulo_embeddings
                    USING hnsw (embedding_vector vector_cosine_ops)
                """))

                conn.commit()
                logger.info(f"✓ Coluna embedding_vector({EMBEDDING_DIMENSION}) e índice HNSW criados")

            PGVECTOR_AVAILABLE = True
            return True

    except Exception as e:
        logger.warning(f"⚠ Não foi possível adicionar coluna vetorial: {e}")
        return False


def init_embeddings_table():
    """
    Inicializa a tabela de embeddings.
    Chamado no startup da aplicação.
    """
    global PGVECTOR_AVAILABLE

    # Tenta setup do pgvector
    setup_pgvector()

    # Cria tabela se não existir
    ModuloEmbedding.__table__.create(engine, checkfirst=True)

    # Adiciona coluna vetorial se pgvector disponível
    PGVECTOR_AVAILABLE = add_vector_column_if_pgvector()

    logger.info(f"Tabela modulo_embeddings inicializada (pgvector: {PGVECTOR_AVAILABLE})")

    return PGVECTOR_AVAILABLE
