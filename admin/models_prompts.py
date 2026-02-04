# admin/models_prompts.py
"""
Modelos para gerenciamento de prompts modulares com versionamento
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, JSON, ForeignKey, UniqueConstraint, Table
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now


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
    criado_em = Column(DateTime, default=get_utc_now)

    # Constraint de unicidade
    __table_args__ = (
        UniqueConstraint('modulo_id', 'tipo_peca', name='uq_modulo_tipo_peca'),
    )

    def __repr__(self):
        return f"<ModuloTipoPeca(modulo_id={self.modulo_id}, tipo_peca='{self.tipo_peca}', ativo={self.ativo})>"


class RegraDeterministicaTipoPeca(Base):
    """
    Regra determinística ESPECÍFICA por tipo de peça.

    Permite definir regras de ativação que só se aplicam quando o tipo de peça
    corresponde ao especificado. Complementa as regras GLOBAIS do PromptModulo.

    Lógica de ativação:
    - Um módulo é ativado se:
      - Qualquer regra GLOBAL for TRUE (do PromptModulo)
        OU
      - Qualquer regra ESPECÍFICA do tipo de peça atual for TRUE (desta tabela)

    Exemplo:
    - Módulo "argumento_prescrição" pode ter:
      - Regra GLOBAL: sempre que valor_causa > 100000
      - Regra para CONTESTAÇÃO: quando prazo_contestacao < 30 dias
      - Regra para APELAÇÃO: quando sentenca_desfavoravel = true
    """

    __tablename__ = "regra_deterministica_tipo_peca"

    id = Column(Integer, primary_key=True, index=True)
    modulo_id = Column(Integer, ForeignKey("prompt_modulos.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo_peca = Column(String(50), nullable=False, index=True)  # Ex: 'contestacao', 'apelacao', 'contrarrazoes'

    # Regra determinística (AST JSON)
    regra_deterministica = Column(JSON, nullable=False)  # AST JSON da regra
    regra_texto_original = Column(Text, nullable=True)  # Texto original em linguagem natural

    # Status
    ativo = Column(Boolean, default=True)

    # Auditoria
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relacionamento
    modulo = relationship("PromptModulo", backref="regras_tipo_peca")

    # Constraint de unicidade: um módulo só pode ter UMA regra por tipo de peça
    __table_args__ = (
        UniqueConstraint('modulo_id', 'tipo_peca', name='uq_regra_modulo_tipo_peca'),
    )

    def __repr__(self):
        return f"<RegraDeterministicaTipoPeca(modulo_id={self.modulo_id}, tipo_peca='{self.tipo_peca}', ativo={self.ativo})>"


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

    # Regra determinística PRIMÁRIA (quando modo_ativacao = 'deterministic')
    # A regra primária é avaliada primeiro e prevalece quando a variável existe
    regra_deterministica = Column(JSON, nullable=True)  # AST JSON da regra gerada pela IA
    regra_texto_original = Column(Text, nullable=True)  # Texto original em linguagem natural

    # Regra determinística SECUNDÁRIA (fallback)
    # Só é avaliada quando a variável da regra primária NÃO EXISTE (documento não identificado)
    # NUNCA sobrepõe a primária - se a primária existe (mesmo false/null), a secundária é ignorada
    regra_deterministica_secundaria = Column(JSON, nullable=True)  # AST JSON da regra secundária
    regra_secundaria_texto_original = Column(Text, nullable=True)  # Texto original da secundária
    fallback_habilitado = Column(Boolean, default=False)  # Se deve avaliar regra secundária

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
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)
    
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

    # Regra secundária (histórico)
    regra_deterministica_secundaria = Column(JSON, nullable=True)
    regra_secundaria_texto_original = Column(Text, nullable=True)
    fallback_habilitado = Column(Boolean, nullable=True)
    
    # Auditoria
    alterado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    alterado_em = Column(DateTime, default=get_utc_now)
    motivo = Column(Text, nullable=True)
    diff_resumo = Column(Text, nullable=True)  # Resumo das alterações
    
    # Relacionamento
    modulo = relationship("PromptModulo", back_populates="historico")
    
    def __repr__(self):
        return f"<PromptModuloHistorico(modulo_id={self.modulo_id}, v{self.versao})>"
