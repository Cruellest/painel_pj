"""add gerador_pecas curadoria columns

Revision ID: a7c3b8d2e1f0
Revises: f12d176fae5f
Create Date: 2026-02-02 15:00:00.000000

Adiciona colunas para rastreamento do modo semi-automático (curadoria):
- modo_ativacao_agente2: Indica o modo usado (fast_path, misto, llm, semi_automatico)
- modulos_ativados_det: Quantidade de módulos ativados por regras determinísticas
- modulos_ativados_llm: Quantidade de módulos ativados por LLM (ou manuais no semi_automatico)
- curadoria_metadata: Metadados completos da curadoria (JSON)

Conforme ADR-0011: Modo Semi-Automático para Gerador de Peças Jurídicas
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = 'a7c3b8d2e1f0'
down_revision: Union[str, None] = 'f12d176fae5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Verifica se uma coluna já existe na tabela (idempotência)."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = :table_name
            AND column_name = :column_name
        )
        """
    ), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def upgrade() -> None:
    """
    Adiciona colunas de curadoria/modo semi-automático ao Gerador de Peças.

    Colunas:
    - modo_ativacao_agente2: Modo usado pelo Agente 2 (detector de módulos)
      Valores: 'fast_path', 'misto', 'llm', 'semi_automatico'
    - modulos_ativados_det: Quantidade ativada por regras determinísticas
    - modulos_ativados_llm: Quantidade ativada por LLM (ou manuais no semi_automatico)
    - curadoria_metadata: JSON com metadados completos da curadoria

    A migração é idempotente - verifica se cada coluna já existe antes de criar.
    """

    # 1. modo_ativacao_agente2
    if not column_exists('geracoes_pecas', 'modo_ativacao_agente2'):
        op.add_column('geracoes_pecas',
            sa.Column('modo_ativacao_agente2', sa.String(20), nullable=True,
                      comment='Modo de ativação do Agente 2: fast_path, misto, llm, semi_automatico'))

    # 2. modulos_ativados_det
    if not column_exists('geracoes_pecas', 'modulos_ativados_det'):
        op.add_column('geracoes_pecas',
            sa.Column('modulos_ativados_det', sa.Integer(), nullable=True,
                      comment='Quantidade de módulos ativados por regras determinísticas'))

    # 3. modulos_ativados_llm
    if not column_exists('geracoes_pecas', 'modulos_ativados_llm'):
        op.add_column('geracoes_pecas',
            sa.Column('modulos_ativados_llm', sa.Integer(), nullable=True,
                      comment='Quantidade de módulos ativados por LLM (ou manuais no semi_automatico)'))

    # 4. curadoria_metadata (JSONB para melhor performance em PostgreSQL)
    if not column_exists('geracoes_pecas', 'curadoria_metadata'):
        op.add_column('geracoes_pecas',
            sa.Column('curadoria_metadata', JSONB(), nullable=True,
                      comment='Metadados da curadoria: preview_ids, curados_ids, manuais_ids, excluidos_ids, etc'))

    # Cria índice para buscar por modo de ativação
    try:
        op.create_index(
            'ix_geracoes_pecas_modo_ativacao',
            'geracoes_pecas',
            ['modo_ativacao_agente2'],
            unique=False
        )
    except Exception:
        # Índice pode já existir
        pass


def downgrade() -> None:
    """Remove colunas de curadoria."""

    # Remove índice
    try:
        op.drop_index('ix_geracoes_pecas_modo_ativacao', table_name='geracoes_pecas')
    except Exception:
        pass

    # Remove colunas (na ordem inversa)
    if column_exists('geracoes_pecas', 'curadoria_metadata'):
        op.drop_column('geracoes_pecas', 'curadoria_metadata')

    if column_exists('geracoes_pecas', 'modulos_ativados_llm'):
        op.drop_column('geracoes_pecas', 'modulos_ativados_llm')

    if column_exists('geracoes_pecas', 'modulos_ativados_det'):
        op.drop_column('geracoes_pecas', 'modulos_ativados_det')

    if column_exists('geracoes_pecas', 'modo_ativacao_agente2'):
        op.drop_column('geracoes_pecas', 'modo_ativacao_agente2')
