# sistemas/matriculas_confrontantes/models.py
"""
Modelos SQLAlchemy para o sistema Matrículas Confrontantes
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now


class ArquivoUpload(Base):
    """Registro de arquivos uploadados por usuário"""
    
    __tablename__ = "arquivos_upload"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String(255), unique=True, index=True, nullable=False)
    file_name = Column(String(255), nullable=False)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    criado_em = Column(DateTime, default=get_utc_now)

    def __repr__(self):
        return f"<ArquivoUpload(file_id='{self.file_id}', usuario_id={self.usuario_id})>"


class GrupoAnalise(Base):
    """Modelo para agrupar múltiplos arquivos em uma única análise"""
    
    __tablename__ = "grupos_analise"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(255), nullable=True)  # Nome opcional do grupo
    descricao = Column(Text, nullable=True)
    criado_em = Column(DateTime, default=get_utc_now)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Status do grupo: 'pendente', 'processando', 'concluido', 'erro'
    status = Column(String(20), default="pendente")
    
    # Resultado consolidado da análise do grupo
    resultado_json = Column(JSON, nullable=True)
    confianca = Column(Float, default=0.0)
    
    # Relacionamento com análises individuais
    analises = relationship("Analise", back_populates="grupo")

    def __repr__(self):
        return f"<GrupoAnalise(id={self.id}, status='{self.status}')>"


class Analise(Base):
    """Modelo para análises de documentos"""
    
    __tablename__ = "analises"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(String(255), unique=True, index=True, nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=True)
    matricula_principal = Column(String(50), nullable=True)
    resultado_json = Column(JSON, nullable=True)
    confianca = Column(Float, default=0.0)
    analisado_em = Column(DateTime, default=get_utc_now)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Referência ao grupo de análise (opcional - análise pode ser individual)
    grupo_id = Column(Integer, ForeignKey("grupos_analise.id"), nullable=True)
    grupo = relationship("GrupoAnalise", back_populates="analises")
    
    # Campos adicionais extraídos do resultado
    lote = Column(String(50), nullable=True)
    proprietario = Column(String(500), nullable=True)
    num_confrontantes = Column(Integer, default=0)
    
    # Relatório gerado pela IA (persistido para não precisar regenerar)
    relatorio_texto = Column(Text, nullable=True)
    
    # Modelo de IA usado na análise/relatório
    modelo_usado = Column(String(100), nullable=True)
    
    # Relacionamento com feedback
    feedback = relationship("FeedbackMatricula", back_populates="analise", uselist=False)

    def __repr__(self):
        return f"<Analise(id={self.id}, file_id='{self.file_id}', matricula='{self.matricula_principal}')>"


class FeedbackMatricula(Base):
    """Armazena feedback do usuário sobre a análise de matrículas"""
    __tablename__ = "feedbacks_matricula"

    id = Column(Integer, primary_key=True, index=True)
    analise_id = Column(Integer, ForeignKey("analises.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Avaliação: 'correto', 'parcial', 'incorreto', 'erro_ia'
    avaliacao = Column(String(20), nullable=False)
    
    # Comentário opcional do usuário
    comentario = Column(Text, nullable=True)
    
    # Campos específicos que estavam errados (opcional)
    campos_incorretos = Column(JSON, nullable=True)
    
    criado_em = Column(DateTime, default=get_utc_now)
    
    # Relacionamentos
    analise = relationship("Analise", back_populates="feedback")

    def __repr__(self):
        return f"<FeedbackMatricula(id={self.id}, avaliacao='{self.avaliacao}')>"


class Registro(Base):
    """Modelo para registros manuais"""
    
    __tablename__ = "registros"

    id = Column(Integer, primary_key=True, index=True)
    matricula = Column(String(50), nullable=False)
    data_operacao = Column(String(20), nullable=True)
    tipo = Column(String(50), default="Imovel")
    proprietario = Column(String(500), nullable=True)
    estado = Column(String(50), default="Pendente")
    confianca = Column(Float, default=0.0)
    expanded = Column(Boolean, default=False)
    children = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    def __repr__(self):
        return f"<Registro(id={self.id}, matricula='{self.matricula}')>"


class LogSistema(Base):
    """Modelo para logs do sistema"""
    
    __tablename__ = "logs_sistema"

    id = Column(Integer, primary_key=True, index=True)
    time = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False)  # 'info', 'success', 'warning', 'error'
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)
    sistema = Column(String(50), default="matriculas")

    def __repr__(self):
        return f"<LogSistema(id={self.id}, status='{self.status}', message='{self.message[:30]}...')>"
