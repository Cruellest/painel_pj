# admin/models_prompts.py
"""
Modelos para gerenciamento de prompts modulares com versionamento
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint, Table
from sqlalchemy.orm import relationship
from database.connection import Base


# Tabela de associação muitos-para-muitos entre PromptModulo e PromptSubcategoria
prompt_modulo_subcategorias = Table(
    "prompt_modulo_subcategorias",
    Base.metadata,
    Column("modulo_id", Integer, ForeignKey("prompt_modulos.id"), primary_key=True),
    Column("subcategoria_id", Integer, ForeignKey("prompt_subcategorias.id"), primary_key=True),
)


class ModuloTipoPeca(Base):
    """
    Associação entre módulos de conteúdo e tipos de peça.
    Define quais módulos de conteúdo estão disponíveis para cada tipo de peça.
    """
    
    __tablename__ = "prompt_modulo_tipo_peca"
    
    id = Column(Integer, primary_key=True, index=True)
    modulo_id = Column(Integer, ForeignKey("prompt_modulos.id"), nullable=False, index=True)
    tipo_peca = Column(String(50), nullable=False, index=True)  # Ex: 'contestacao', 'recurso_apelacao'
    ativo = Column(Boolean, default=True)
    criado_em = Column(DateTime, default=datetime.utcnow)
    
    # Constraint de unicidade
    __table_args__ = (
        UniqueConstraint('modulo_id', 'tipo_peca', name='uq_modulo_tipo_peca'),
    )
    
    def __repr__(self):
        return f"<ModuloTipoPeca(modulo_id={self.modulo_id}, tipo_peca='{self.tipo_peca}', ativo={self.ativo})>"


class PromptModulo(Base):
    """Módulo de prompt editável (base, peça ou conteúdo)"""
    
    __tablename__ = "prompt_modulos"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Classificação
    tipo = Column(String(20), nullable=False, index=True)  # 'base', 'peca', 'conteudo'
    categoria = Column(String(50), nullable=True, index=True)  # Para conteúdo: 'medicamento', 'laudo', etc.
    subcategoria = Column(String(50), nullable=True)  # 'nao_incorporado_sus', 'experimental', etc.
    group_id = Column(Integer, ForeignKey("prompt_groups.id"), nullable=True, index=True)
    subgroup_id = Column(Integer, ForeignKey("prompt_subgroups.id"), nullable=True, index=True)
    
    # Identificação
    nome = Column(String(100), nullable=False)
    titulo = Column(String(200), nullable=False)
    
    # Conteúdo
    condicao_ativacao = Column(Text, nullable=True)  # Situação em que o prompt deve ser ativado (para o Agente 2 - Detector)
    conteudo = Column(Text, nullable=False)  # O prompt em si (markdown) - enviado ao Agente 3 (Gerador)

    # Modo de ativação (llm = modo atual, deterministic = regra AST)
    modo_ativacao = Column(String(20), nullable=True, default='llm')  # 'llm' | 'deterministic'

    # Regra determinística (quando modo_ativacao = 'deterministic')
    regra_deterministica = Column(JSON, nullable=True)  # AST JSON da regra gerada pela IA
    regra_texto_original = Column(Text, nullable=True)  # Texto original em linguagem natural

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
    group = relationship("PromptGroup")
    subgroup = relationship("PromptSubgroup")
    subcategorias = relationship("PromptSubcategoria", secondary=prompt_modulo_subcategorias, backref="modulos")
    
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
    group_id = Column(Integer, ForeignKey("prompt_groups.id"), nullable=True, index=True)
    subgroup_id = Column(Integer, ForeignKey("prompt_subgroups.id"), nullable=True, index=True)
    
    # Dados da versão
    versao = Column(Integer, nullable=False)
    condicao_ativacao = Column(Text, nullable=True)  # Histórico da condição de ativação
    conteudo = Column(Text, nullable=False)
    palavras_chave = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)

    # Modo de ativação e regra determinística (histórico)
    modo_ativacao = Column(String(20), nullable=True)
    regra_deterministica = Column(JSON, nullable=True)
    regra_texto_original = Column(Text, nullable=True)
    
    # Auditoria
    alterado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    alterado_em = Column(DateTime, default=datetime.utcnow)
    motivo = Column(Text, nullable=True)
    diff_resumo = Column(Text, nullable=True)  # Resumo das alterações
    
    # Relacionamento
    modulo = relationship("PromptModulo", back_populates="historico")
    
    def __repr__(self):
        return f"<PromptModuloHistorico(modulo_id={self.modulo_id}, v{self.versao})>"
