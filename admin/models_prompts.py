# admin/models_prompts.py
"""
Modelos para gerenciamento de prompts modulares com versionamento
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database.connection import Base


class PromptModulo(Base):
    """Módulo de prompt editável (base, peça ou conteúdo)"""
    
    __tablename__ = "prompt_modulos"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Classificação
    tipo = Column(String(20), nullable=False, index=True)  # 'base', 'peca', 'conteudo'
    categoria = Column(String(50), nullable=True, index=True)  # Para conteúdo: 'medicamento', 'laudo', etc.
    subcategoria = Column(String(50), nullable=True)  # 'nao_incorporado_sus', 'experimental', etc.
    
    # Identificação
    nome = Column(String(100), nullable=False)
    titulo = Column(String(200), nullable=False)
    
    # Conteúdo
    condicao_ativacao = Column(Text, nullable=True)  # Situação em que o prompt deve ser ativado (para o Agente 2 - Detector)
    conteudo = Column(Text, nullable=False)  # O prompt em si (markdown) - enviado ao Agente 3 (Gerador)
    
    # Metadados
    palavras_chave = Column(JSON, nullable=True, default=list)  # Para detecção automática
    tags = Column(JSON, nullable=True, default=list)  # Organização/busca
    
    # Status
    ativo = Column(Boolean, default=True, index=True)
    ordem = Column(Integer, default=0)
    
    # Versionamento
    versao = Column(Integer, default=1)
    
    # Auditoria
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamentos
    historico = relationship("PromptModuloHistorico", back_populates="modulo", order_by="desc(PromptModuloHistorico.versao)")
    
    # Constraint de unicidade
    __table_args__ = (
        UniqueConstraint('tipo', 'categoria', 'subcategoria', 'nome', name='uq_prompt_modulo'),
    )
    
    def __repr__(self):
        return f"<PromptModulo(id={self.id}, tipo='{self.tipo}', nome='{self.nome}', v{self.versao})>"


class PromptModuloHistorico(Base):
    """Histórico de versões de um módulo de prompt"""
    
    __tablename__ = "prompt_modulos_historico"
    
    id = Column(Integer, primary_key=True, index=True)
    modulo_id = Column(Integer, ForeignKey("prompt_modulos.id"), nullable=False, index=True)
    
    # Dados da versão
    versao = Column(Integer, nullable=False)
    condicao_ativacao = Column(Text, nullable=True)  # Histórico da condição de ativação
    conteudo = Column(Text, nullable=False)
    palavras_chave = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    
    # Auditoria
    alterado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    alterado_em = Column(DateTime, default=datetime.utcnow)
    motivo = Column(Text, nullable=True)
    diff_resumo = Column(Text, nullable=True)  # Resumo das alterações
    
    # Relacionamento
    modulo = relationship("PromptModulo", back_populates="historico")
    
    def __repr__(self):
        return f"<PromptModuloHistorico(modulo_id={self.modulo_id}, v{self.versao})>"
