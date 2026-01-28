"""add cumprimento beta tables

Revision ID: 898ae5c6ae52
Revises:
Create Date: 2026-01-27 16:22:47.560094

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '898ae5c6ae52'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Cria tabelas do módulo Cumprimento de Sentença Beta."""
    # Tabela principal: sessoes_cumprimento_beta
    op.create_table('sessoes_cumprimento_beta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('numero_processo', sa.String(length=30), nullable=False),
        sa.Column('numero_processo_formatado', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('total_documentos', sa.Integer(), nullable=True),
        sa.Column('documentos_processados', sa.Integer(), nullable=True),
        sa.Column('documentos_relevantes', sa.Integer(), nullable=True),
        sa.Column('documentos_irrelevantes', sa.Integer(), nullable=True),
        sa.Column('documentos_ignorados', sa.Integer(), nullable=True),
        sa.Column('erro_mensagem', sa.Text(), nullable=True),
        sa.Column('erro_detalhes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finalizado_em', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sessoes_beta_user_created', 'sessoes_cumprimento_beta', ['user_id', 'created_at'], unique=False)
    op.create_index('ix_sessoes_cumprimento_beta_created_at', 'sessoes_cumprimento_beta', ['created_at'], unique=False)
    op.create_index('ix_sessoes_cumprimento_beta_id', 'sessoes_cumprimento_beta', ['id'], unique=False)
    op.create_index('ix_sessoes_cumprimento_beta_numero_processo', 'sessoes_cumprimento_beta', ['numero_processo'], unique=False)
    op.create_index('ix_sessoes_cumprimento_beta_status', 'sessoes_cumprimento_beta', ['status'], unique=False)
    op.create_index('ix_sessoes_cumprimento_beta_user_id', 'sessoes_cumprimento_beta', ['user_id'], unique=False)

    # Tabela: consolidacoes_beta
    op.create_table('consolidacoes_beta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sessao_id', sa.Integer(), nullable=False),
        sa.Column('resumo_consolidado', sa.Text(), nullable=False),
        sa.Column('sugestoes_pecas', sa.JSON(), nullable=True),
        sa.Column('dados_processo', sa.JSON(), nullable=True),
        sa.Column('modelo_usado', sa.String(length=50), nullable=False),
        sa.Column('tokens_entrada', sa.Integer(), nullable=True),
        sa.Column('tokens_saida', sa.Integer(), nullable=True),
        sa.Column('tempo_processamento_ms', sa.Integer(), nullable=True),
        sa.Column('total_jsons_consolidados', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sessao_id'], ['sessoes_cumprimento_beta.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_consolidacoes_beta_id', 'consolidacoes_beta', ['id'], unique=False)
    op.create_index('ix_consolidacoes_beta_sessao_id', 'consolidacoes_beta', ['sessao_id'], unique=True)

    # Tabela: conversas_beta
    op.create_table('conversas_beta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sessao_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('conteudo', sa.Text(), nullable=False),
        sa.Column('modelo_usado', sa.String(length=50), nullable=True),
        sa.Column('tokens_entrada', sa.Integer(), nullable=True),
        sa.Column('tokens_saida', sa.Integer(), nullable=True),
        sa.Column('usou_busca_vetorial', sa.Boolean(), nullable=True),
        sa.Column('argumentos_encontrados', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sessao_id'], ['sessoes_cumprimento_beta.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_conversas_beta_created_at', 'conversas_beta', ['created_at'], unique=False)
    op.create_index('ix_conversas_beta_id', 'conversas_beta', ['id'], unique=False)
    op.create_index('ix_conversas_beta_sessao_created', 'conversas_beta', ['sessao_id', 'created_at'], unique=False)
    op.create_index('ix_conversas_beta_sessao_id', 'conversas_beta', ['sessao_id'], unique=False)

    # Tabela: documentos_beta
    op.create_table('documentos_beta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sessao_id', sa.Integer(), nullable=False),
        sa.Column('documento_id_tjms', sa.String(length=50), nullable=False),
        sa.Column('codigo_documento', sa.Integer(), nullable=False),
        sa.Column('descricao_documento', sa.String(length=500), nullable=True),
        sa.Column('data_documento', sa.DateTime(timezone=True), nullable=True),
        sa.Column('conteudo_texto', sa.Text(), nullable=True),
        sa.Column('tamanho_bytes', sa.Integer(), nullable=True),
        sa.Column('paginas', sa.Integer(), nullable=True),
        sa.Column('status_relevancia', sa.String(length=20), nullable=False),
        sa.Column('motivo_irrelevancia', sa.Text(), nullable=True),
        sa.Column('modelo_avaliacao', sa.String(length=50), nullable=True),
        sa.Column('tokens_avaliacao', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('avaliado_em', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sessao_id'], ['sessoes_cumprimento_beta.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_docs_beta_sessao_status', 'documentos_beta', ['sessao_id', 'status_relevancia'], unique=False)
    op.create_index('ix_documentos_beta_codigo_documento', 'documentos_beta', ['codigo_documento'], unique=False)
    op.create_index('ix_documentos_beta_id', 'documentos_beta', ['id'], unique=False)
    op.create_index('ix_documentos_beta_sessao_id', 'documentos_beta', ['sessao_id'], unique=False)
    op.create_index('ix_documentos_beta_status_relevancia', 'documentos_beta', ['status_relevancia'], unique=False)

    # Tabela: jsons_resumo_beta
    op.create_table('jsons_resumo_beta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('documento_id', sa.Integer(), nullable=False),
        sa.Column('json_conteudo', sa.JSON(), nullable=False),
        sa.Column('categoria_id', sa.Integer(), nullable=True),
        sa.Column('categoria_nome', sa.String(length=100), nullable=True),
        sa.Column('modelo_usado', sa.String(length=50), nullable=False),
        sa.Column('tokens_entrada', sa.Integer(), nullable=True),
        sa.Column('tokens_saida', sa.Integer(), nullable=True),
        sa.Column('tempo_processamento_ms', sa.Integer(), nullable=True),
        sa.Column('json_valido', sa.Boolean(), nullable=True),
        sa.Column('erro_validacao', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['documento_id'], ['documentos_beta.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jsons_resumo_beta_documento_id', 'jsons_resumo_beta', ['documento_id'], unique=True)
    op.create_index('ix_jsons_resumo_beta_id', 'jsons_resumo_beta', ['id'], unique=False)

    # Tabela: pecas_geradas_beta
    op.create_table('pecas_geradas_beta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sessao_id', sa.Integer(), nullable=False),
        sa.Column('conversa_id', sa.Integer(), nullable=True),
        sa.Column('tipo_peca', sa.String(length=100), nullable=False),
        sa.Column('titulo', sa.String(length=500), nullable=True),
        sa.Column('conteudo_markdown', sa.Text(), nullable=False),
        sa.Column('conteudo_docx_path', sa.String(length=500), nullable=True),
        sa.Column('instrucoes_usuario', sa.Text(), nullable=True),
        sa.Column('modelo_usado', sa.String(length=50), nullable=False),
        sa.Column('tokens_entrada', sa.Integer(), nullable=True),
        sa.Column('tokens_saida', sa.Integer(), nullable=True),
        sa.Column('tempo_geracao_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['conversa_id'], ['conversas_beta.id'], ),
        sa.ForeignKeyConstraint(['sessao_id'], ['sessoes_cumprimento_beta.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_pecas_geradas_beta_created_at', 'pecas_geradas_beta', ['created_at'], unique=False)
    op.create_index('ix_pecas_geradas_beta_id', 'pecas_geradas_beta', ['id'], unique=False)
    op.create_index('ix_pecas_geradas_beta_sessao_id', 'pecas_geradas_beta', ['sessao_id'], unique=False)


def downgrade() -> None:
    """Remove tabelas do módulo Cumprimento de Sentença Beta."""
    op.drop_index('ix_pecas_geradas_beta_sessao_id', table_name='pecas_geradas_beta')
    op.drop_index('ix_pecas_geradas_beta_id', table_name='pecas_geradas_beta')
    op.drop_index('ix_pecas_geradas_beta_created_at', table_name='pecas_geradas_beta')
    op.drop_table('pecas_geradas_beta')

    op.drop_index('ix_jsons_resumo_beta_id', table_name='jsons_resumo_beta')
    op.drop_index('ix_jsons_resumo_beta_documento_id', table_name='jsons_resumo_beta')
    op.drop_table('jsons_resumo_beta')

    op.drop_index('ix_documentos_beta_status_relevancia', table_name='documentos_beta')
    op.drop_index('ix_documentos_beta_sessao_id', table_name='documentos_beta')
    op.drop_index('ix_documentos_beta_id', table_name='documentos_beta')
    op.drop_index('ix_documentos_beta_codigo_documento', table_name='documentos_beta')
    op.drop_index('ix_docs_beta_sessao_status', table_name='documentos_beta')
    op.drop_table('documentos_beta')

    op.drop_index('ix_conversas_beta_sessao_id', table_name='conversas_beta')
    op.drop_index('ix_conversas_beta_sessao_created', table_name='conversas_beta')
    op.drop_index('ix_conversas_beta_id', table_name='conversas_beta')
    op.drop_index('ix_conversas_beta_created_at', table_name='conversas_beta')
    op.drop_table('conversas_beta')

    op.drop_index('ix_consolidacoes_beta_sessao_id', table_name='consolidacoes_beta')
    op.drop_index('ix_consolidacoes_beta_id', table_name='consolidacoes_beta')
    op.drop_table('consolidacoes_beta')

    op.drop_index('ix_sessoes_cumprimento_beta_user_id', table_name='sessoes_cumprimento_beta')
    op.drop_index('ix_sessoes_cumprimento_beta_status', table_name='sessoes_cumprimento_beta')
    op.drop_index('ix_sessoes_cumprimento_beta_numero_processo', table_name='sessoes_cumprimento_beta')
    op.drop_index('ix_sessoes_cumprimento_beta_id', table_name='sessoes_cumprimento_beta')
    op.drop_index('ix_sessoes_cumprimento_beta_created_at', table_name='sessoes_cumprimento_beta')
    op.drop_index('ix_sessoes_beta_user_created', table_name='sessoes_cumprimento_beta')
    op.drop_table('sessoes_cumprimento_beta')
