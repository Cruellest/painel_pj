# sistemas/gerador_pecas/models_extraction.py
"""
Modelos para o sistema de extração baseado em IA.

Este módulo implementa:
- Perguntas de extração em linguagem natural (modo IA)
- Modelos de extração gerados por IA ou manuais
- Variáveis normalizadas do sistema
- Rastreamento de uso de variáveis em prompts
"""

from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    JSON, ForeignKey, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now
import enum


class ExtractionQuestionType(str, enum.Enum):
    """Tipos de dados sugeridos para perguntas de extração"""
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    CHOICE = "choice"  # Múltipla escolha
    LIST = "list"  # Lista de itens
    CURRENCY = "currency"  # Valor monetário


class DependencyOperator(str, enum.Enum):
    """Operadores para dependências entre perguntas"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN_LIST = "in_list"
    NOT_IN_LIST = "not_in_list"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"


class ExtractionQuestion(Base):
    """
    Pergunta de extração em linguagem natural (modo IA).

    Cada pergunta:
    - Pertence a uma categoria de documento (grupo)
    - É escrita em linguagem natural pelo usuário
    - Pode ter sugestões opcionais de nome de variável, tipo e opções
    - Pode ter uma dependência condicional de outra variável
    - Gera uma variável técnica quando processada pela IA
    """
    __tablename__ = "extraction_questions"

    id = Column(Integer, primary_key=True, index=True)

    # Categoria de documento (FK para categorias_resumo_json)
    categoria_id = Column(
        Integer,
        ForeignKey("categorias_resumo_json.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Pergunta em linguagem natural (OBRIGATÓRIO)
    pergunta = Column(Text, nullable=False)

    # Sugestões do usuário (TODOS OPCIONAIS)
    nome_variavel_sugerido = Column(String(100), nullable=True)
    tipo_sugerido = Column(String(50), nullable=True)  # ExtractionQuestionType
    opcoes_sugeridas = Column(JSON, nullable=True)  # Lista de opções para múltipla escolha

    # Descrição adicional para ajudar a IA
    descricao = Column(Text, nullable=True)

    # === DEPENDÊNCIAS CONDICIONAIS ===
    # Variável da qual esta pergunta depende (slug)
    depends_on_variable = Column(String(100), nullable=True, index=True)

    # Operador da dependência (equals, not_equals, in_list, exists, etc.)
    dependency_operator = Column(String(20), nullable=True)

    # Valor da condição (suporta diversos tipos via JSON)
    dependency_value = Column(JSON, nullable=True)

    # Configuração completa da dependência (para casos complexos)
    # Formato: {"conditions": [...], "logic": "and"|"or"}
    dependency_config = Column(JSON, nullable=True)

    # Se a dependência foi inferida por IA (vs definida manualmente)
    dependency_inferred = Column(Boolean, default=False)

    # Status e ordem
    ativo = Column(Boolean, default=True, index=True)
    ordem = Column(Integer, default=0)

    # Auditoria
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Nota: Removido relationship para evitar problemas de importação circular
    # Use join manual se precisar acessar a categoria

    @property
    def is_conditional(self) -> bool:
        """Retorna True se a pergunta tem dependência condicional."""
        return bool(self.depends_on_variable or self.dependency_config)

    @property
    def dependency_summary(self) -> Optional[str]:
        """Retorna resumo legível da dependência."""
        if not self.is_conditional:
            return None

        if self.depends_on_variable:
            op = self.dependency_operator or "equals"
            val = self.dependency_value
            if val is True:
                return f"{self.depends_on_variable} = Sim"
            elif val is False:
                return f"{self.depends_on_variable} = Não"
            else:
                return f"{self.depends_on_variable} {op} {val}"

        return "Configuração complexa"

    def __repr__(self):
        dep = " [CONDICIONAL]" if self.is_conditional else ""
        return f"<ExtractionQuestion(id={self.id}, pergunta='{self.pergunta[:50]}...'{dep})>"


class ExtractionModelMode(str, enum.Enum):
    """Modo de criação do modelo de extração"""
    AI_GENERATED = "ai_generated"
    MANUAL = "manual"


class ExtractionModel(Base):
    """
    Modelo de extração JSON para uma categoria de documento.

    Pode ser:
    - ai_generated: Gerado automaticamente pela IA a partir das perguntas
    - manual: Criado manualmente (modo legado)
    """
    __tablename__ = "extraction_models"

    id = Column(Integer, primary_key=True, index=True)

    # Categoria de documento (FK para categorias_resumo_json)
    categoria_id = Column(
        Integer,
        ForeignKey("categorias_resumo_json.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Modo de criação
    modo = Column(String(20), nullable=False, default="manual")  # ai_generated | manual

    # Schema JSON gerado/definido
    schema_json = Column(JSON, nullable=False)

    # Mapeamento de perguntas para variáveis (apenas para ai_generated)
    # Formato: {"question_id": {"slug": "...", "tipo": "...", ...}}
    mapeamento_variaveis = Column(JSON, nullable=True)

    # Versionamento
    versao = Column(Integer, default=1)
    ativo = Column(Boolean, default=True, index=True)

    # Auditoria
    criado_por = Column(Integer, ForeignKey("users.id"), nullable=True)
    criado_em = Column(DateTime, default=get_utc_now)

    # Nota: Removido relationship para evitar problemas de importação circular

    __table_args__ = (
        UniqueConstraint('categoria_id', 'versao', name='uq_extraction_model_categoria_versao'),
    )

    def __repr__(self):
        return f"<ExtractionModel(id={self.id}, categoria_id={self.categoria_id}, modo='{self.modo}', v{self.versao})>"


class ExtractionVariable(Base):
    """
    Variável normalizada do sistema.

    Representa uma variável técnica extraída de documentos:
    - Pode ser criada a partir de uma pergunta de extração (modo IA)
    - Pode ser criada manualmente
    - É usada em regras determinísticas de ativação de prompts
    - Pode ser condicional (só aplicável quando outra variável satisfaz condição)
    """
    __tablename__ = "extraction_variables"

    id = Column(Integer, primary_key=True, index=True)

    # Identificação técnica (único no sistema)
    slug = Column(String(100), nullable=False, unique=True, index=True)

    # Identificação humana
    label = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)

    # Tipo final da variável
    tipo = Column(String(50), nullable=False)  # text, number, date, boolean, choice, list, currency

    # Categoria de documento de origem
    categoria_id = Column(
        Integer,
        ForeignKey("categorias_resumo_json.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Opções (para tipo choice/list)
    opcoes = Column(JSON, nullable=True)

    # Pergunta de origem (se criada via modo IA)
    source_question_id = Column(
        Integer,
        ForeignKey("extraction_questions.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # === DEPENDÊNCIAS CONDICIONAIS ===
    # Se esta variável é condicional (só aplicável em certas condições)
    is_conditional = Column(Boolean, default=False, index=True)

    # Variável da qual depende (slug)
    depends_on_variable = Column(String(100), nullable=True, index=True)

    # Configuração da dependência (igual ao ExtractionQuestion)
    dependency_config = Column(JSON, nullable=True)

    # === FONTE DE VERDADE INDIVIDUAL ===
    # Código específico para filtrar documentos (override do grupo)
    fonte_verdade_codigo = Column(String(20), nullable=True)

    # Tipo lógico de documento que é fonte de verdade para esta variável
    # NOTA: O matching é feito SEMANTICAMENTE pela LLM durante a extração.
    # Ex: "parecer do NAT" deve casar com "parecer do NATJUS"
    fonte_verdade_tipo = Column(String(100), nullable=True)

    # Se usa fonte de verdade específica (diferente do grupo)
    fonte_verdade_override = Column(Boolean, default=False)

    # Status
    ativo = Column(Boolean, default=True, index=True)

    # Auditoria
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relacionamentos (removido CategoriaResumoJSON para evitar problemas de importação circular)
    source_question = relationship("ExtractionQuestion", backref="variavel_gerada")
    prompt_usages = relationship("PromptVariableUsage", back_populates="variable", cascade="all, delete-orphan")

    @property
    def dependency_chain(self) -> List[str]:
        """Retorna a cadeia de dependências (para visualização)."""
        if not self.depends_on_variable:
            return []
        return [self.depends_on_variable]

    def __repr__(self):
        cond = " [CONDICIONAL]" if self.is_conditional else ""
        return f"<ExtractionVariable(id={self.id}, slug='{self.slug}', tipo='{self.tipo}'{cond})>"


class PromptActivationMode(str, enum.Enum):
    """Modo de ativação de prompt de conteúdo"""
    LLM = "llm"  # Avaliado por LLM (modo atual)
    DETERMINISTIC = "deterministic"  # Avaliado por regra determinística


class PromptVariableUsage(Base):
    """
    Rastreia o uso de variáveis em prompts.

    Atualizado automaticamente quando:
    - Uma regra determinística é criada/alterada
    - Uma regra é removida
    """
    __tablename__ = "prompt_variable_usage"

    id = Column(Integer, primary_key=True, index=True)

    # Prompt que usa a variável
    prompt_id = Column(
        Integer,
        ForeignKey("prompt_modulos.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Variável usada (referência por slug para flexibilidade)
    variable_slug = Column(String(100), nullable=False, index=True)

    # FK opcional para a variável (permite rastreamento mesmo se slug mudar)
    variable_id = Column(
        Integer,
        ForeignKey("extraction_variables.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Auditoria
    criado_em = Column(DateTime, default=get_utc_now)

    # Relacionamentos
    prompt = relationship("PromptModulo", backref="variable_usages")
    variable = relationship("ExtractionVariable", back_populates="prompt_usages")

    __table_args__ = (
        UniqueConstraint('prompt_id', 'variable_slug', name='uq_prompt_variable_usage'),
    )

    def __repr__(self):
        return f"<PromptVariableUsage(prompt_id={self.prompt_id}, variable_slug='{self.variable_slug}')>"


class PromptActivationLog(Base):
    """
    Log de ativação de prompts para auditoria.

    Registra cada vez que um prompt é avaliado (LLM ou determinístico).
    """
    __tablename__ = "prompt_activation_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Prompt avaliado
    prompt_id = Column(
        Integer,
        ForeignKey("prompt_modulos.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Modo de ativação usado (valores padronizados curtos)
    # Valores: 'llm', 'deterministic', 'deterministic_global', 'deterministic_tipo_peca', 'mixed'
    modo_ativacao = Column(Text, nullable=False)

    # Detalhes do modo (tipo de peça, regra específica, etc.) - campo separado para flexibilidade
    modo_ativacao_detalhe = Column(Text, nullable=True)

    # Resultado da avaliação
    resultado = Column(Boolean, nullable=False)  # True = ativado, False = não ativado

    # Variáveis usadas na avaliação (snapshot)
    variaveis_usadas = Column(JSON, nullable=True)

    # Contexto (resumo dos documentos, etc)
    contexto = Column(JSON, nullable=True)

    # Para modo LLM: justificativa da IA
    justificativa_ia = Column(Text, nullable=True)

    # Referência ao processo/geração
    geracao_id = Column(Integer, nullable=True, index=True)
    numero_processo = Column(String(30), nullable=True, index=True)

    # Timestamp
    timestamp = Column(DateTime, default=get_utc_now, index=True)

    # Relacionamentos
    prompt = relationship("PromptModulo", backref="activation_logs")

    def __repr__(self):
        return f"<PromptActivationLog(prompt_id={self.prompt_id}, modo='{self.modo_ativacao}', resultado={self.resultado})>"
