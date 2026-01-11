# sistemas/prestacao_contas/models.py
"""
Modelos SQLAlchemy para o sistema de Prestação de Contas
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from datetime import datetime

from database.connection import Base


class GeracaoAnalise(Base):
    """Registro de cada análise de prestação de contas"""
    __tablename__ = "geracoes_prestacao_contas"

    id = Column(Integer, primary_key=True, index=True)
    numero_cnj = Column(String(30), nullable=False, index=True)
    numero_cnj_formatado = Column(String(30), nullable=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # =====================================================
    # DADOS COLETADOS
    # =====================================================

    # Extrato da subconta
    extrato_subconta_pdf = Column(String(500), nullable=True)  # Caminho do PDF (legado)
    extrato_subconta_pdf_base64 = Column(Text, nullable=True)  # PDF em base64
    extrato_subconta_texto = Column(Text, nullable=True)  # Texto extraído

    # Petição inicial
    peticao_inicial_id = Column(String(50), nullable=True)
    peticao_inicial_texto = Column(Text, nullable=True)

    # Petição de prestação de contas
    peticao_prestacao_id = Column(String(50), nullable=True)
    peticao_prestacao_data = Column(DateTime, nullable=True)
    peticao_prestacao_texto = Column(Text, nullable=True)

    # Documentos anexos (notas fiscais, comprovantes)
    documentos_anexos = Column(JSON, nullable=True)  # [{id, tipo, data, texto}]

    # Petições relevantes identificadas (contexto adicional)
    peticoes_relevantes = Column(JSON, nullable=True)  # [{id, tipo, resumo}]

    # Dados do XML do processo
    dados_processo_xml = Column(JSON, nullable=True)

    # =====================================================
    # DEBUG - PROMPTS E RESPOSTAS
    # =====================================================

    prompt_identificacao = Column(Text, nullable=True)  # Prompt usado para identificar prestação
    prompt_analise = Column(Text, nullable=True)  # Prompt enviado ao agente final
    resposta_ia_bruta = Column(Text, nullable=True)  # Resposta bruta da IA

    # =====================================================
    # RESULTADO
    # =====================================================

    parecer = Column(String(20), nullable=True)  # 'favoravel', 'desfavoravel', 'duvida'
    fundamentacao = Column(Text, nullable=True)  # Markdown do parecer
    irregularidades = Column(JSON, nullable=True)  # Lista de irregularidades (se desfavorável)
    perguntas_usuario = Column(JSON, nullable=True)  # Perguntas em caso de dúvida
    respostas_usuario = Column(JSON, nullable=True)  # Respostas do usuário às perguntas

    # Dados extraídos pela IA
    valor_bloqueado = Column(Float, nullable=True)
    valor_utilizado = Column(Float, nullable=True)
    valor_devolvido = Column(Float, nullable=True)
    medicamento_pedido = Column(String(500), nullable=True)
    medicamento_comprado = Column(String(500), nullable=True)

    # =====================================================
    # METADADOS
    # =====================================================

    modelo_usado = Column(String(100), nullable=True)
    tempo_processamento_ms = Column(Integer, nullable=True)
    status = Column(String(20), default="processando")  # 'processando', 'concluido', 'erro'
    erro = Column(Text, nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)
    atualizado_em = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relacionamentos
    logs_ia = relationship("LogChamadaIAPrestacao", back_populates="geracao", cascade="all, delete-orphan")
    feedbacks = relationship("FeedbackPrestacao", back_populates="geracao", cascade="all, delete-orphan")


class LogChamadaIAPrestacao(Base):
    """Log detalhado de cada chamada de IA"""
    __tablename__ = "logs_chamada_ia_prestacao"

    id = Column(Integer, primary_key=True, index=True)
    geracao_id = Column(Integer, ForeignKey("geracoes_prestacao_contas.id"), nullable=False)

    etapa = Column(String(50), nullable=False)  # 'identificacao_peticao', 'analise_final', etc
    descricao = Column(Text, nullable=True)

    prompt_enviado = Column(Text, nullable=True)
    documento_id = Column(String(50), nullable=True)
    documento_texto = Column(Text, nullable=True)

    resposta_ia = Column(Text, nullable=True)
    resposta_parseada = Column(JSON, nullable=True)

    modelo_usado = Column(String(100), nullable=True)
    tokens_entrada = Column(Integer, nullable=True)
    tokens_saida = Column(Integer, nullable=True)
    tempo_ms = Column(Integer, nullable=True)

    sucesso = Column(Boolean, default=True)
    erro = Column(Text, nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)

    # Relacionamento
    geracao = relationship("GeracaoAnalise", back_populates="logs_ia")


class FeedbackPrestacao(Base):
    """Feedback do usuário sobre análise"""
    __tablename__ = "feedbacks_prestacao_contas"

    id = Column(Integer, primary_key=True, index=True)
    geracao_id = Column(Integer, ForeignKey("geracoes_prestacao_contas.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    avaliacao = Column(String(20), nullable=False)  # 'correto', 'parcial', 'incorreto', 'erro_ia'
    nota = Column(Integer, nullable=True)  # 1-5
    comentario = Column(Text, nullable=True)

    # Campos específicos para feedback detalhado
    parecer_correto = Column(Boolean, nullable=True)
    valores_corretos = Column(Boolean, nullable=True)
    medicamento_correto = Column(Boolean, nullable=True)

    criado_em = Column(DateTime, default=datetime.utcnow)

    # Relacionamento
    geracao = relationship("GeracaoAnalise", back_populates="feedbacks")
