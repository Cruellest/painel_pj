"""add classificador recovery fields (ADR-0010)

Revision ID: f12d176fae5f
Revises: 898ae5c6ae52
Create Date: 2026-01-30 14:00:00.000000

Conforme ADR-0010: Sistema de Recuperação de Execuções Travadas
Adiciona campos para detecção de travamento e retomada de execuções.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f12d176fae5f'
down_revision: Union[str, None] = '898ae5c6ae52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Adiciona campos de heartbeat e recuperação ao Classificador de Documentos.

    Conforme ADR-0010:
    - ultimo_heartbeat: Atualizado a cada documento processado
    - ultimo_codigo_processado: Código do último documento
    - tentativas_retry: Quantas vezes foi retomada
    - max_retries: Limite de retomadas (default=3)
    - rota_origem: Rota que iniciou a execução

    Para resultados:
    - erro_stack: Stack trace para debug
    - tentativas: Contador de tentativas do documento
    - ultimo_erro_em: Timestamp do último erro
    """

    # Adiciona colunas na tabela execucoes_classificacao
    op.add_column('execucoes_classificacao',
        sa.Column('ultimo_heartbeat', sa.DateTime(), nullable=True,
                  comment='Timestamp do último heartbeat (atualizado a cada documento)'))

    op.add_column('execucoes_classificacao',
        sa.Column('ultimo_codigo_processado', sa.String(100), nullable=True,
                  comment='Código do último documento processado'))

    op.add_column('execucoes_classificacao',
        sa.Column('tentativas_retry', sa.Integer(), nullable=True, server_default='0',
                  comment='Número de vezes que a execução foi retomada'))

    op.add_column('execucoes_classificacao',
        sa.Column('max_retries', sa.Integer(), nullable=True, server_default='3',
                  comment='Limite máximo de retomadas permitidas'))

    op.add_column('execucoes_classificacao',
        sa.Column('rota_origem', sa.String(200), nullable=True, server_default='/classificador/',
                  comment='Rota que iniciou a execução'))

    # Adiciona colunas na tabela resultados_classificacao
    op.add_column('resultados_classificacao',
        sa.Column('erro_stack', sa.Text(), nullable=True,
                  comment='Stack trace do erro para debug'))

    op.add_column('resultados_classificacao',
        sa.Column('tentativas', sa.Integer(), nullable=True, server_default='0',
                  comment='Número de tentativas de processamento'))

    op.add_column('resultados_classificacao',
        sa.Column('ultimo_erro_em', sa.DateTime(), nullable=True,
                  comment='Timestamp do último erro'))

    # Cria índice para buscar execuções em andamento com heartbeat antigo (para watchdog)
    op.create_index(
        'ix_execucoes_classificacao_status_heartbeat',
        'execucoes_classificacao',
        ['status', 'ultimo_heartbeat'],
        unique=False
    )


def downgrade() -> None:
    """Remove campos de recuperação."""

    # Remove índice
    op.drop_index('ix_execucoes_classificacao_status_heartbeat', table_name='execucoes_classificacao')

    # Remove colunas de resultados_classificacao
    op.drop_column('resultados_classificacao', 'ultimo_erro_em')
    op.drop_column('resultados_classificacao', 'tentativas')
    op.drop_column('resultados_classificacao', 'erro_stack')

    # Remove colunas de execucoes_classificacao
    op.drop_column('execucoes_classificacao', 'rota_origem')
    op.drop_column('execucoes_classificacao', 'max_retries')
    op.drop_column('execucoes_classificacao', 'tentativas_retry')
    op.drop_column('execucoes_classificacao', 'ultimo_codigo_processado')
    op.drop_column('execucoes_classificacao', 'ultimo_heartbeat')
