# sistemas/gerador_pecas/models.py
"""
Modelos do sistema de Geração de Peças Jurídicas
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from database.connection import Base


class GeracaoPeca(Base):
    """Armazena gerações de peças jurídicas realizadas"""
    __tablename__ = "geracoes_pecas"

    id = Column(Integer, primary_key=True, index=True)
    numero_cnj = Column(String(30), nullable=False, index=True)
    numero_cnj_formatado = Column(String(30), nullable=True)
    tipo_peca = Column(String(50), nullable=True)  # contestacao, recurso, contrarrazoes, parecer
    
    # Dados do processo (JSON do TJ-MS)
    dados_processo = Column(JSON, nullable=True)
    
    # Lista de documentos com descrição identificada pela IA (JSON)
    # Formato: [{"id": "...", "ids": [...], "descricao": "...", "descricao_ia": "...", "data_juntada": "...", ...}]
    documentos_processados = Column(JSON, nullable=True)
    
    # Conteúdo gerado pela IA em Markdown
    conteudo_gerado = Column(Text, nullable=True)
    
    # Prompt completo enviado à IA (para debug/auditoria)
    prompt_enviado = Column(Text, nullable=True)
    
    # Resumo consolidado do processo (output do Agente 1)
    resumo_consolidado = Column(Text, nullable=True)
    
    # Histórico de conversas do chat de edição (JSON array)
    historico_chat = Column(JSON, nullable=True)
    
    # Caminho do arquivo DOCX gerado
    arquivo_path = Column(String(500), nullable=True)
    
    # Modelo de IA usado
    modelo_usado = Column(String(100), nullable=True)
    
    # Tempo de processamento (segundos)
    tempo_processamento = Column(Integer, nullable=True)
    
    # Usuário que gerou
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Timestamps
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamento com feedback
    feedback = relationship("FeedbackPeca", back_populates="geracao", uselist=False)

    def __repr__(self):
        return f"<GeracaoPeca(id={self.id}, cnj='{self.numero_cnj}', tipo='{self.tipo_peca}')>"


class FeedbackPeca(Base):
    """Armazena feedback do usuário sobre a peça gerada"""
    __tablename__ = "feedbacks_pecas"

    id = Column(Integer, primary_key=True, index=True)
    geracao_id = Column(Integer, ForeignKey("geracoes_pecas.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Avaliação: 'correto', 'parcial', 'incorreto', 'erro_ia'
    avaliacao = Column(String(20), nullable=False)
    
    # Nota de 1 a 5 estrelas
    nota = Column(Integer, nullable=True)
    
    # Comentário opcional do usuário
    comentario = Column(Text, nullable=True)
    
    # Campos específicos que tiveram problemas (opcional)
    campos_incorretos = Column(JSON, nullable=True)
    
    criado_em = Column(DateTime, default=datetime.utcnow)
    
    # Relacionamentos
    geracao = relationship("GeracaoPeca", back_populates="feedback")

    def __repr__(self):
        return f"<FeedbackPeca(id={self.id}, avaliacao='{self.avaliacao}')>"
