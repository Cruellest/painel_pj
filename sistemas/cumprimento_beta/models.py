# sistemas/cumprimento_beta/models.py
"""
Modelos de dados do módulo Cumprimento de Sentença Beta

Modelos isolados para não afetar o gerador normal:
- SessaoCumprimentoBeta: Sessão principal do fluxo
- DocumentoBeta: Documento baixado com status de relevância
- JSONResumoBeta: JSON gerado pelo Agente 1
- ConsolidacaoBeta: Resumo consolidado do Agente 2
- ConversaBeta: Mensagens do chatbot
- PecaGeradaBeta: Peça final gerada
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    JSON, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now


class SessaoCumprimentoBeta(Base):
    """
    Sessão principal do fluxo de Cumprimento de Sentença Beta.

    Armazena o estado completo de uma execução do beta,
    desde a entrada do processo até a geração da peça final.
    """
    __tablename__ = "sessoes_cumprimento_beta"

    id = Column(Integer, primary_key=True, index=True)

    # Usuário que criou a sessão
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    user = relationship("User", foreign_keys=[user_id])

    # Dados do processo
    numero_processo = Column(String(30), nullable=False, index=True)  # CNJ limpo
    numero_processo_formatado = Column(String(50), nullable=True)  # CNJ formatado

    # Status do fluxo
    status = Column(String(30), nullable=False, default="iniciado", index=True)
    # Valores: iniciado, baixando_docs, avaliando_relevancia, extraindo_json,
    #          consolidando, chatbot, gerando_peca, finalizado, erro

    # Contadores para UI
    total_documentos = Column(Integer, default=0)
    documentos_processados = Column(Integer, default=0)
    documentos_relevantes = Column(Integer, default=0)
    documentos_irrelevantes = Column(Integer, default=0)
    documentos_ignorados = Column(Integer, default=0)

    # Erro (se status == erro)
    erro_mensagem = Column(Text, nullable=True)
    erro_detalhes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=get_utc_now, index=True)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now)
    finalizado_em = Column(DateTime(timezone=True), nullable=True)

    # Relacionamentos
    documentos = relationship("DocumentoBeta", back_populates="sessao", cascade="all, delete-orphan")
    consolidacao = relationship("ConsolidacaoBeta", back_populates="sessao", uselist=False, cascade="all, delete-orphan")
    conversas = relationship("ConversaBeta", back_populates="sessao", cascade="all, delete-orphan")
    pecas = relationship("PecaGeradaBeta", back_populates="sessao", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_sessoes_beta_user_created", "user_id", "created_at"),
    )

    def __repr__(self):
        return f"<SessaoCumprimentoBeta(id={self.id}, processo='{self.numero_processo}', status='{self.status}')>"


class DocumentoBeta(Base):
    """
    Documento baixado do TJ-MS para uma sessão do beta.

    Armazena o documento e seu status de relevância após
    avaliação pelo Agente 1.
    """
    __tablename__ = "documentos_beta"

    id = Column(Integer, primary_key=True, index=True)

    # Sessão pai
    sessao_id = Column(Integer, ForeignKey("sessoes_cumprimento_beta.id"), nullable=False, index=True)
    sessao = relationship("SessaoCumprimentoBeta", back_populates="documentos")

    # Identificação do documento no TJ-MS
    documento_id_tjms = Column(String(50), nullable=False)
    codigo_documento = Column(Integer, nullable=False, index=True)
    descricao_documento = Column(String(500), nullable=True)
    data_documento = Column(DateTime(timezone=True), nullable=True)

    # Conteúdo extraído
    conteudo_texto = Column(Text, nullable=True)
    tamanho_bytes = Column(Integer, default=0)
    paginas = Column(Integer, default=0)

    # Avaliação de relevância (Agente 1)
    status_relevancia = Column(String(20), nullable=False, default="pendente", index=True)
    # Valores: pendente, relevante, irrelevante, ignorado
    motivo_irrelevancia = Column(Text, nullable=True)

    # Modelo usado na avaliação
    modelo_avaliacao = Column(String(50), nullable=True)
    tokens_avaliacao = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=get_utc_now)
    avaliado_em = Column(DateTime(timezone=True), nullable=True)

    # Relacionamento com JSON gerado
    json_resumo = relationship("JSONResumoBeta", back_populates="documento", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_docs_beta_sessao_status", "sessao_id", "status_relevancia"),
    )

    def __repr__(self):
        return f"<DocumentoBeta(id={self.id}, codigo={self.codigo_documento}, status='{self.status_relevancia}')>"


class JSONResumoBeta(Base):
    """
    JSON de resumo gerado pelo Agente 1 para um documento relevante.

    Segue o schema configurado na categoria "Cumprimento de Sentença"
    em /admin/categorias-resumo-json.
    """
    __tablename__ = "jsons_resumo_beta"

    id = Column(Integer, primary_key=True, index=True)

    # Documento pai
    documento_id = Column(Integer, ForeignKey("documentos_beta.id"), nullable=False, unique=True, index=True)
    documento = relationship("DocumentoBeta", back_populates="json_resumo")

    # Conteúdo JSON
    json_conteudo = Column(JSON, nullable=False)

    # Categoria usada (para auditoria)
    categoria_id = Column(Integer, nullable=True)
    categoria_nome = Column(String(100), nullable=True)

    # Modelo e métricas
    modelo_usado = Column(String(50), nullable=False)
    tokens_entrada = Column(Integer, default=0)
    tokens_saida = Column(Integer, default=0)
    tempo_processamento_ms = Column(Integer, default=0)

    # Validação
    json_valido = Column(Boolean, default=True)
    erro_validacao = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    def __repr__(self):
        return f"<JSONResumoBeta(id={self.id}, documento_id={self.documento_id})>"


class ConsolidacaoBeta(Base):
    """
    Consolidação gerada pelo Agente 2.

    Contém o resumo consolidado de todos os documentos relevantes
    e as sugestões de peças para o usuário.
    """
    __tablename__ = "consolidacoes_beta"

    id = Column(Integer, primary_key=True, index=True)

    # Sessão pai
    sessao_id = Column(Integer, ForeignKey("sessoes_cumprimento_beta.id"), nullable=False, unique=True, index=True)
    sessao = relationship("SessaoCumprimentoBeta", back_populates="consolidacao")

    # Conteúdo
    resumo_consolidado = Column(Text, nullable=False)
    sugestoes_pecas = Column(JSON, nullable=True)  # Lista de sugestões

    # Dados do processo extraídos
    dados_processo = Column(JSON, nullable=True)  # Partes, valores, datas, etc.

    # Modelo e métricas
    modelo_usado = Column(String(50), nullable=False)
    tokens_entrada = Column(Integer, default=0)
    tokens_saida = Column(Integer, default=0)
    tempo_processamento_ms = Column(Integer, default=0)

    # Quantos JSONs foram usados
    total_jsons_consolidados = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=get_utc_now)

    def __repr__(self):
        return f"<ConsolidacaoBeta(id={self.id}, sessao_id={self.sessao_id})>"


class ConversaBeta(Base):
    """
    Mensagem do chatbot do beta.

    Armazena o histórico completo de conversas entre
    usuário e assistente para uma sessão.
    """
    __tablename__ = "conversas_beta"

    id = Column(Integer, primary_key=True, index=True)

    # Sessão pai
    sessao_id = Column(Integer, ForeignKey("sessoes_cumprimento_beta.id"), nullable=False, index=True)
    sessao = relationship("SessaoCumprimentoBeta", back_populates="conversas")

    # Mensagem
    role = Column(String(20), nullable=False)  # user, assistant, system
    conteudo = Column(Text, nullable=False)

    # Metadados (para assistant)
    modelo_usado = Column(String(50), nullable=True)
    tokens_entrada = Column(Integer, default=0)
    tokens_saida = Column(Integer, default=0)

    # Se usou busca vetorial
    usou_busca_vetorial = Column(Boolean, default=False)
    argumentos_encontrados = Column(JSON, nullable=True)  # IDs dos módulos encontrados

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=get_utc_now, index=True)

    __table_args__ = (
        Index("ix_conversas_beta_sessao_created", "sessao_id", "created_at"),
    )

    def __repr__(self):
        return f"<ConversaBeta(id={self.id}, role='{self.role}')>"


class PecaGeradaBeta(Base):
    """
    Peça jurídica gerada pelo beta.

    Pode haver múltiplas peças por sessão, caso o usuário
    solicite diferentes tipos ou versões.
    """
    __tablename__ = "pecas_geradas_beta"

    id = Column(Integer, primary_key=True, index=True)

    # Sessão pai
    sessao_id = Column(Integer, ForeignKey("sessoes_cumprimento_beta.id"), nullable=False, index=True)
    sessao = relationship("SessaoCumprimentoBeta", back_populates="pecas")

    # Conversa que originou a peça (opcional)
    conversa_id = Column(Integer, ForeignKey("conversas_beta.id"), nullable=True)

    # Tipo da peça
    tipo_peca = Column(String(100), nullable=False)
    titulo = Column(String(500), nullable=True)

    # Conteúdo
    conteudo_markdown = Column(Text, nullable=False)
    conteudo_docx_path = Column(String(500), nullable=True)  # Caminho do arquivo DOCX

    # Instruções usadas
    instrucoes_usuario = Column(Text, nullable=True)

    # Modelo e métricas
    modelo_usado = Column(String(50), nullable=False)
    tokens_entrada = Column(Integer, default=0)
    tokens_saida = Column(Integer, default=0)
    tempo_geracao_ms = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=get_utc_now, index=True)

    def __repr__(self):
        return f"<PecaGeradaBeta(id={self.id}, tipo='{self.tipo_peca}')>"
