# sistemas/gerador_pecas/models_teste_ativacao.py
"""
Modelos para o ambiente de teste de ativação de prompts modulares.

Permite criar cenários de teste com variáveis de extração e processo
para validar a lógica de ativação de módulos de prompts.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now, to_iso_utc


class CenarioTesteAtivacao(Base):
    """
    Cenário de teste para simulação de ativação de prompts modulares.

    Armazena:
    - Descrição textual da situação processual
    - Variáveis de extração (geradas via IA ou manualmente)
    - Variáveis de processo (valor_causa, polo passivo, etc.)
    - Tipo de peça e categorias selecionadas
    - Módulos esperados (para testes automatizados)
    """
    __tablename__ = "teste_ativacao_cenarios"

    id = Column(Integer, primary_key=True, index=True)

    # Usuário que criou o cenário
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Identificação do cenário
    nome = Column(String(200), nullable=False)
    descricao_situacao = Column(Text, nullable=True)  # Descrição textual do cenário

    # Variáveis geradas/configuradas
    variaveis_extracao = Column(JSON, nullable=True, default=dict)  # Variáveis extraídas de documentos
    variaveis_processo = Column(JSON, nullable=True, default=dict)  # Variáveis derivadas do processo

    # Configuração de peça
    tipo_peca = Column(String(50), nullable=True)  # contestacao, apelacao, etc.
    categorias_selecionadas = Column(JSON, nullable=True, default=list)  # IDs das categorias para filtrar

    # Para testes automatizados (opcional)
    modulos_esperados_ativados = Column(JSON, nullable=True, default=list)  # IDs dos módulos esperados

    # Timestamps
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Índices para consultas frequentes
    __table_args__ = (
        Index('ix_teste_ativacao_usuario', 'usuario_id'),
        Index('ix_teste_ativacao_tipo_peca', 'tipo_peca'),
    )

    def __repr__(self):
        return f"<CenarioTesteAtivacao(id={self.id}, nome='{self.nome}', tipo_peca='{self.tipo_peca}')>"

    def to_dict(self):
        """Converte para dicionário para API"""
        return {
            "id": self.id,
            "usuario_id": self.usuario_id,
            "nome": self.nome,
            "descricao_situacao": self.descricao_situacao,
            "variaveis_extracao": self.variaveis_extracao or {},
            "variaveis_processo": self.variaveis_processo or {},
            "tipo_peca": self.tipo_peca,
            "categorias_selecionadas": self.categorias_selecionadas or [],
            "modulos_esperados_ativados": self.modulos_esperados_ativados or [],
            "criado_em": to_iso_utc(self.criado_em),
            "atualizado_em": to_iso_utc(self.atualizado_em),
        }
