# admin/models.py
"""
Modelos de administração - Configurações de Prompts de IA
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from database.connection import Base


class PromptConfig(Base):
    """Configuração de prompts de IA por sistema"""
    
    __tablename__ = "prompt_configs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Identificação do prompt
    sistema = Column(String(50), nullable=False, index=True)  # 'matriculas', 'assistencia', etc.
    tipo = Column(String(50), nullable=False, index=True)  # 'system', 'analise', 'relatorio', etc.
    nome = Column(String(100), nullable=False)  # Nome amigável para exibição
    descricao = Column(String(500), nullable=True)  # Descrição do propósito do prompt
    
    # Conteúdo do prompt
    conteudo = Column(Text, nullable=False)
    
    # Metadados
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = Column(String(50), nullable=True)  # Username de quem atualizou
    
    def __repr__(self):
        return f"<PromptConfig(id={self.id}, sistema='{self.sistema}', tipo='{self.tipo}')>"


class ConfiguracaoIA(Base):
    """Configurações gerais de IA (modelos, temperaturas, etc.)"""
    
    __tablename__ = "configuracoes_ia"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Identificação
    sistema = Column(String(50), nullable=False, index=True)  # 'matriculas', 'assistencia', 'global'
    chave = Column(String(100), nullable=False, index=True)  # Nome da configuração
    valor = Column(Text, nullable=False)  # Valor da configuração
    tipo_valor = Column(String(20), default="string")  # 'string', 'number', 'boolean', 'json'
    descricao = Column(String(500), nullable=True)
    
    # Metadados
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<ConfiguracaoIA(sistema='{self.sistema}', chave='{self.chave}')>"
