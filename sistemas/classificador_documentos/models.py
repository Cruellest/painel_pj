# sistemas/classificador_documentos/models.py
"""
Modelos de dados para o Sistema de Classificação de Documentos

Define as estruturas de dados usadas pelo sistema:
- ProjetoClassificacao: projeto de classificação de documentos
- CodigoDocumentoProjeto: códigos de documentos vinculados a um projeto
- ExecucaoClassificacao: execução de classificação de um projeto
- ResultadoClassificacao: resultado individual de classificação

Autor: LAB/PGE-MS
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean, Float
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now


# ============================================
# Enums
# ============================================

class StatusExecucao(str, Enum):
    """Status de uma execução de classificação"""
    PENDENTE = "pendente"
    EM_ANDAMENTO = "em_andamento"
    PAUSADO = "pausado"
    TRAVADO = "travado"  # Detectado automaticamente pelo watchdog
    CANCELADO = "cancelado"  # Cancelado manualmente pelo usuário
    CONCLUIDO = "concluido"
    ERRO = "erro"


class StatusArquivo(str, Enum):
    """Status de um arquivo dentro de uma execução"""
    PENDENTE = "pendente"
    PROCESSANDO = "processando"
    CONCLUIDO = "concluido"
    ERRO = "erro"
    PULADO = "pulado"  # Pulado durante retomada (já processado com sucesso antes)


class FonteDocumento(str, Enum):
    """Fonte do documento para classificação"""
    UPLOAD = "upload"  # Upload manual pelo usuário
    TJMS = "tjms"      # Baixado do TJ-MS via API


class NivelConfianca(str, Enum):
    """Níveis de confiança da classificação"""
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


# ============================================
# Modelos SQLAlchemy para Persistência
# ============================================

class ProjetoClassificacao(Base):
    """
    Projeto de classificação de documentos.

    Um projeto agrupa múltiplas execuções de classificação com
    configurações específicas (prompt, modelo, códigos de documentos).
    """
    __tablename__ = "projetos_classificacao"

    id = Column(Integer, primary_key=True, index=True)

    # Identificação
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)

    # Configurações de classificação
    prompt_id = Column(Integer, ForeignKey("prompts_classificacao.id"), nullable=True)
    modelo = Column(String(100), default="google/gemini-2.5-flash-lite")

    # Configurações de processamento
    modo_processamento = Column(String(20), default="chunk")  # "chunk" ou "completo"
    posicao_chunk = Column(String(10), default="fim")  # "inicio" ou "fim"
    tamanho_chunk = Column(Integer, default=512)  # tokens
    max_concurrent = Column(Integer, default=3)  # chamadas paralelas

    # Metadados
    ativo = Column(Boolean, default=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Timestamps
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relacionamentos
    codigos = relationship("CodigoDocumentoProjeto", back_populates="projeto", cascade="all, delete-orphan")
    execucoes = relationship("ExecucaoClassificacao", back_populates="projeto", cascade="all, delete-orphan")
    prompt = relationship("PromptClassificacao", back_populates="projetos")

    def __repr__(self):
        return f"<ProjetoClassificacao(id={self.id}, nome='{self.nome}')>"


class CodigoDocumentoProjeto(Base):
    """
    Código de documento vinculado a um projeto (Lote).

    Pode ser:
    - Código do TJ-MS (para download automático)
    - Arquivo local (upload pelo usuário)
    - Identificador de documento manualmente associado

    Conforme docs/REDESIGN_CLASSIFICADOR_v2.md secao 3.2:
    - Nao armazena PDF inteiro, apenas referencia e cache de texto
    """
    __tablename__ = "codigos_documento_projeto"

    id = Column(Integer, primary_key=True, index=True)
    projeto_id = Column(Integer, ForeignKey("projetos_classificacao.id"), nullable=False)

    # Identificação do documento
    codigo = Column(String(100), nullable=False)  # Código do documento no TJ-MS ou identificador
    numero_processo = Column(String(30), nullable=True)  # Número CNJ do processo (se aplicável)
    descricao = Column(String(500), nullable=True)  # Descrição do documento

    # Campos para upload local (conforme docs/REDESIGN_CLASSIFICADOR_v2.md secao 3.2)
    arquivo_nome = Column(String(500), nullable=True)  # Nome original do arquivo
    arquivo_hash = Column(String(64), nullable=True)   # SHA256 para dedup
    texto_extraido = Column(Text, nullable=True)       # Cache do texto extraido

    # Tipo de documento TJ-MS (conforme docs/REDESIGN_CLASSIFICADOR_v2.md secao 4.2)
    tipo_documento = Column(String(10), nullable=True)  # tipoDocumento do TJ-MS (8, 15, 34, etc)

    # Metadados
    fonte = Column(String(20), default=FonteDocumento.TJMS.value)
    ativo = Column(Boolean, default=True)

    # Timestamps
    criado_em = Column(DateTime, default=get_utc_now)

    # Relacionamentos
    projeto = relationship("ProjetoClassificacao", back_populates="codigos")

    def __repr__(self):
        return f"<CodigoDocumentoProjeto(id={self.id}, codigo='{self.codigo}')>"


class ExecucaoClassificacao(Base):
    """
    Execução de classificação de um projeto.

    Cada execução processa os documentos do projeto e armazena
    os resultados. Permite reprocessamento e histórico.
    """
    __tablename__ = "execucoes_classificacao"

    id = Column(Integer, primary_key=True, index=True)
    projeto_id = Column(Integer, ForeignKey("projetos_classificacao.id"), nullable=False)

    # Status e progresso
    status = Column(String(20), default=StatusExecucao.PENDENTE.value)
    total_arquivos = Column(Integer, default=0)
    arquivos_processados = Column(Integer, default=0)
    arquivos_sucesso = Column(Integer, default=0)
    arquivos_erro = Column(Integer, default=0)

    # Configurações usadas nesta execução (snapshot)
    modelo_usado = Column(String(100), nullable=True)
    prompt_usado = Column(Text, nullable=True)  # Texto do prompt no momento da execução
    config_usada = Column(JSON, nullable=True)  # {modo, posicao_chunk, tamanho_chunk, etc}

    # Metadados
    erro_mensagem = Column(Text, nullable=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Campos para detecção de travamento e recuperação (ADR-0010)
    ultimo_heartbeat = Column(DateTime, nullable=True)  # Atualizado a cada documento processado
    ultimo_codigo_processado = Column(String(100), nullable=True)  # Código do último documento processado
    tentativas_retry = Column(Integer, default=0)  # Quantas vezes a execução foi retomada
    max_retries = Column(Integer, default=3)  # Limite de retomadas
    rota_origem = Column(String(200), default="/classificador/")  # Rota que iniciou a execução

    # Timestamps
    iniciado_em = Column(DateTime, nullable=True)
    finalizado_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=get_utc_now)

    # Relacionamentos
    projeto = relationship("ProjetoClassificacao", back_populates="execucoes")
    resultados = relationship("ResultadoClassificacao", back_populates="execucao", cascade="all, delete-orphan")

    @property
    def esta_travada(self) -> bool:
        """Verifica se a execução está travada (sem heartbeat por mais de 5 minutos)"""
        if self.status != StatusExecucao.EM_ANDAMENTO.value:
            return False
        if not self.ultimo_heartbeat:
            return False
        from datetime import timedelta
        return (get_utc_now() - self.ultimo_heartbeat) > timedelta(minutes=5)

    @property
    def pode_retomar(self) -> bool:
        """Verifica se a execução pode ser retomada"""
        return (
            self.status in [StatusExecucao.TRAVADO.value, StatusExecucao.ERRO.value] and
            self.tentativas_retry < self.max_retries
        )

    @property
    def progresso_percentual(self) -> float:
        if self.total_arquivos == 0:
            return 0.0
        return (self.arquivos_processados / self.total_arquivos) * 100

    def __repr__(self):
        return f"<ExecucaoClassificacao(id={self.id}, status='{self.status}')>"


class ResultadoClassificacao(Base):
    """
    Resultado individual de classificação de um documento.

    Armazena apenas metadados e resultado, NÃO armazena o PDF ou texto completo.
    O texto normalizado usado para classificação é armazenado para auditoria.
    """
    __tablename__ = "resultados_classificacao"

    id = Column(Integer, primary_key=True, index=True)
    execucao_id = Column(Integer, ForeignKey("execucoes_classificacao.id"), nullable=False)

    # Identificação do documento
    codigo_documento = Column(String(100), nullable=False)  # Código do documento
    numero_processo = Column(String(30), nullable=True)  # Número CNJ
    nome_arquivo = Column(String(500), nullable=True)  # Nome original do arquivo

    # Status de processamento
    status = Column(String(20), default=StatusArquivo.PENDENTE.value)
    fonte = Column(String(20), default=FonteDocumento.TJMS.value)

    # Metadados de extração (NÃO armazena o texto completo)
    texto_extraido_via = Column(String(20), nullable=True)  # "pdf" ou "ocr"
    tokens_extraidos = Column(Integer, nullable=True)  # Quantidade de tokens
    chunk_usado = Column(Text, nullable=True)  # Apenas o chunk enviado para IA (para auditoria)

    # Resultado da classificação
    categoria = Column(String(100), nullable=True)
    subcategoria = Column(String(100), nullable=True)
    confianca = Column(String(20), nullable=True)  # alta, media, baixa
    justificativa = Column(Text, nullable=True)
    resultado_json = Column(JSON, nullable=True)  # Resposta completa da IA

    # Metadados de erro (ADR-0010: campos expandidos para recuperação)
    erro_mensagem = Column(Text, nullable=True)
    erro_stack = Column(Text, nullable=True)  # Stack trace para debug
    tentativas = Column(Integer, default=0)  # Contador de tentativas
    ultimo_erro_em = Column(DateTime, nullable=True)  # Timestamp do último erro

    # Timestamps
    processado_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=get_utc_now)

    # Relacionamentos
    execucao = relationship("ExecucaoClassificacao", back_populates="resultados")

    @property
    def pode_reprocessar(self) -> bool:
        """Verifica se o documento pode ser reprocessado"""
        MAX_TENTATIVAS = 3
        return self.status == StatusArquivo.ERRO.value and self.tentativas < MAX_TENTATIVAS

    def __repr__(self):
        return f"<ResultadoClassificacao(id={self.id}, codigo='{self.codigo_documento}', status='{self.status}')>"


class PromptClassificacao(Base):
    """
    Prompt para classificação de documentos.

    Prompts são reutilizáveis entre projetos e podem ser
    versionados através de histórico de edições.
    """
    __tablename__ = "prompts_classificacao"

    id = Column(Integer, primary_key=True, index=True)

    # Identificação
    nome = Column(String(200), nullable=False, unique=True)
    descricao = Column(Text, nullable=True)

    # Conteúdo
    conteudo = Column(Text, nullable=False)

    # Códigos de tipos de documento do TJ-MS que este prompt classifica
    # Armazenado como string separada por vírgula: "8,15,34,500"
    codigos_documento = Column(String(500), nullable=True)

    # Metadados
    ativo = Column(Boolean, default=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Timestamps
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relacionamentos
    projetos = relationship("ProjetoClassificacao", back_populates="prompt")

    def __repr__(self):
        return f"<PromptClassificacao(id={self.id}, nome='{self.nome}')>"


class LogClassificacaoIA(Base):
    """
    Log detalhado de cada chamada de IA durante a classificação.
    Permite debug e auditoria de todas as interações com o modelo.
    """
    __tablename__ = "logs_classificacao_ia"

    id = Column(Integer, primary_key=True, index=True)
    resultado_id = Column(Integer, ForeignKey("resultados_classificacao.id"), nullable=True, index=True)
    execucao_id = Column(Integer, ForeignKey("execucoes_classificacao.id"), nullable=True, index=True)

    # Identificação
    codigo_documento = Column(String(100), nullable=True)

    # Entrada
    prompt_enviado = Column(Text, nullable=True)
    chunk_enviado = Column(Text, nullable=True)

    # Saída
    resposta_bruta = Column(Text, nullable=True)
    resposta_parseada = Column(JSON, nullable=True)

    # Metadados
    modelo_usado = Column(String(100), nullable=True)
    tokens_entrada = Column(Integer, nullable=True)
    tokens_saida = Column(Integer, nullable=True)
    tempo_ms = Column(Integer, nullable=True)
    sucesso = Column(Boolean, default=True)
    erro = Column(Text, nullable=True)

    # Timestamp
    criado_em = Column(DateTime, default=get_utc_now)

    def __repr__(self):
        return f"<LogClassificacaoIA(id={self.id}, sucesso={self.sucesso})>"


# ============================================
# Dataclasses para Processamento (em memória)
# ============================================

@dataclass
class DocumentoParaClassificar:
    """Documento preparado para classificação"""
    codigo: str
    numero_processo: Optional[str] = None
    nome_arquivo: Optional[str] = None
    fonte: FonteDocumento = FonteDocumento.TJMS
    texto_extraido: Optional[str] = None
    texto_via_ocr: bool = False
    tokens_total: int = 0
    erro: Optional[str] = None


@dataclass
class ResultadoClassificacaoDTO:
    """DTO para resultado de classificação"""
    codigo_documento: str
    numero_processo: Optional[str] = None
    nome_arquivo: Optional[str] = None
    categoria: Optional[str] = None
    subcategoria: Optional[str] = None
    confianca: Optional[str] = None
    justificativa: Optional[str] = None
    sucesso: bool = False
    erro: Optional[str] = None
    texto_via: Optional[str] = None
    tokens_usados: int = 0
    chunk_usado: Optional[str] = None
    resultado_completo: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "codigo_documento": self.codigo_documento,
            "numero_processo": self.numero_processo,
            "nome_arquivo": self.nome_arquivo,
            "categoria": self.categoria,
            "subcategoria": self.subcategoria,
            "confianca": self.confianca,
            "justificativa": self.justificativa,
            "sucesso": self.sucesso,
            "erro": self.erro,
            "texto_via": self.texto_via,
            "tokens_usados": self.tokens_usados
        }
