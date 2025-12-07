# sistemas/gerador_pecas/models_resumo_json.py
"""
Modelos para categorias de formato de resumo JSON.

Permite definir diferentes formatos de saída JSON para resumos de documentos,
baseados no tipo de documento (código do TJ-MS).
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from database.connection import Base


class CategoriaResumoJSON(Base):
    """
    Define uma categoria de formato de resumo JSON.
    
    Cada categoria:
    - Tem um nome identificador
    - Define quais códigos de documento do TJ-MS pertencem a ela
    - Define o formato JSON esperado para os resumos
    
    Exemplo:
    - Categoria "peticoes" com códigos [500, 510, 9500] e formato:
      {"tipo": "string", "partes": {"autor": "string", "reu": "string"}, "pedidos": ["string"]}
    """
    __tablename__ = "categorias_resumo_json"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Identificação
    nome = Column(String(100), nullable=False, unique=True, index=True)
    titulo = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)
    
    # Códigos de documento TJ-MS que pertencem a esta categoria
    # Formato: lista de inteiros [500, 510, 9500]
    codigos_documento = Column(JSON, nullable=False, default=list)
    
    # Formato JSON esperado - estrutura de exemplo
    # Armazena o schema/exemplo que a IA deve seguir
    formato_json = Column(Text, nullable=False)
    
    # Prompt adicional para instruir a IA sobre este formato específico
    # Instruções extras sobre como preencher os campos
    instrucoes_extracao = Column(Text, nullable=True)
    
    # Se é a categoria residual (fallback para docs não categorizados)
    is_residual = Column(Boolean, default=False, index=True)
    
    # Status
    ativo = Column(Boolean, default=True, index=True)
    ordem = Column(Integer, default=0)
    
    # Auditoria
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<CategoriaResumoJSON(id={self.id}, nome='{self.nome}', residual={self.is_residual})>"


class CategoriaResumoJSONHistorico(Base):
    """Histórico de versões de uma categoria de resumo JSON"""
    
    __tablename__ = "categorias_resumo_json_historico"
    
    id = Column(Integer, primary_key=True, index=True)
    categoria_id = Column(Integer, ForeignKey("categorias_resumo_json.id"), nullable=False, index=True)
    
    # Dados da versão
    versao = Column(Integer, nullable=False)
    codigos_documento = Column(JSON, nullable=True)
    formato_json = Column(Text, nullable=False)
    instrucoes_extracao = Column(Text, nullable=True)
    
    # Auditoria
    alterado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    alterado_em = Column(DateTime, default=datetime.utcnow)
    motivo = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<CategoriaResumoJSONHistorico(categoria_id={self.categoria_id}, v{self.versao})>"
