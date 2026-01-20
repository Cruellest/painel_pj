# sistemas/assistencia_judiciaria/models.py
"""
Modelos do sistema de Assistência Judiciária
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now


class ConsultaProcesso(Base):
    """Armazena consultas de processos realizadas"""
    __tablename__ = "consultas_processos"

    id = Column(Integer, primary_key=True, index=True)
    cnj = Column(String(30), nullable=False, index=True)
    cnj_formatado = Column(String(30), nullable=True)
    dados_json = Column(JSON, nullable=True)
    relatorio = Column(Text, nullable=True)
    modelo_usado = Column(String(100), nullable=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    consultado_em = Column(DateTime, default=get_utc_now)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)
    
    # Relacionamento com feedback
    feedback = relationship("FeedbackAnalise", back_populates="consulta", uselist=False)

    def __repr__(self):
        return f"<ConsultaProcesso(id={self.id}, cnj='{self.cnj}')>"


class FeedbackAnalise(Base):
    """Armazena feedback do usuário sobre a análise da IA"""
    __tablename__ = "feedbacks_analise"

    id = Column(Integer, primary_key=True, index=True)
    consulta_id = Column(Integer, ForeignKey("consultas_processos.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Avaliação: 'correto', 'parcial', 'incorreto', 'erro_ia'
    avaliacao = Column(String(20), nullable=False)
    
    # Comentário opcional do usuário
    comentario = Column(Text, nullable=True)
    
    # Campos específicos do relatório que estavam errados (opcional)
    campos_incorretos = Column(JSON, nullable=True)
    
    criado_em = Column(DateTime, default=get_utc_now)
    
    # Relacionamentos
    consulta = relationship("ConsultaProcesso", back_populates="feedback")

    def __repr__(self):
        return f"<FeedbackAnalise(id={self.id}, avaliacao='{self.avaliacao}')>"

