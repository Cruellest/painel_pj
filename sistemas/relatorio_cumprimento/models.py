# sistemas/relatorio_cumprimento/models.py
"""
Modelos de dados para o Sistema de Relatório de Cumprimento de Sentença

Define as estruturas de dados usadas pelo sistema:
- DadosProcesso: informações básicas do processo
- DocumentoClassificado: documento baixado e classificado
- ResultadoAnalise: resultado da análise pela IA
- GeracaoRelatorioCumprimento: modelo SQLAlchemy para persistência

Autor: LAB/PGE-MS
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Dict, Optional, Any
from enum import Enum

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.orm import relationship
from database.connection import Base
from utils.timezone import get_utc_now


# ============================================
# Enums
# ============================================

class CategoriaDocumento(str, Enum):
    """Categorias de documentos para classificação"""
    PETICAO_INICIAL_CUMPRIMENTO = "peticao_inicial_cumprimento"
    SENTENCA = "sentenca"
    ACORDAO = "acordao"
    DECISAO = "decisao"  # Decisões interlocutórias (cumprimento de decisão)
    CERTIDAO_TRANSITO = "certidao_transito"
    # Documentos de Agravo de Instrumento
    DECISAO_AGRAVO = "decisao_agravo"  # Decisões do agravo (monocráticas, liminares, etc.)
    ACORDAO_AGRAVO = "acordao_agravo"  # Acórdãos do agravo
    OUTRO = "outro"


class StatusProcessamento(str, Enum):
    """Status do processamento"""
    INICIADO = "iniciado"
    BAIXANDO_DOCUMENTOS = "baixando_documentos"
    ANALISANDO = "analisando"
    GERANDO_RELATORIO = "gerando_relatorio"
    CONCLUIDO = "concluido"
    ERRO = "erro"


# ============================================
# Modelo SQLAlchemy para Persistência
# ============================================

class GeracaoRelatorioCumprimento(Base):
    """Armazena gerações de relatórios de cumprimento de sentença"""
    __tablename__ = "geracoes_relatorio_cumprimento"

    id = Column(Integer, primary_key=True, index=True)

    # Número do processo de cumprimento (entrada do usuário)
    numero_cumprimento = Column(String(30), nullable=False, index=True)
    numero_cumprimento_formatado = Column(String(30), nullable=True)

    # Número do processo principal (conhecimento) identificado
    numero_principal = Column(String(30), nullable=True)
    numero_principal_formatado = Column(String(30), nullable=True)

    # Dados do processo de cumprimento (JSON do TJ-MS)
    dados_processo_cumprimento = Column(JSON, nullable=True)

    # Dados do processo principal (JSON do TJ-MS)
    dados_processo_principal = Column(JSON, nullable=True)

    # Dados básicos extraídos (partes, valor da causa, etc.)
    dados_basicos = Column(JSON, nullable=True)

    # Lista de documentos baixados e classificados (JSON)
    documentos_baixados = Column(JSON, nullable=True)

    # Informação sobre trânsito em julgado
    transito_julgado_localizado = Column(Boolean, default=False)
    data_transito_julgado = Column(String(20), nullable=True)

    # Conteúdo gerado pela IA em Markdown
    conteudo_gerado = Column(Text, nullable=True)

    # Histórico de conversas do chat de edição (JSON array)
    historico_chat = Column(JSON, nullable=True)

    # Caminho do arquivo DOCX gerado
    arquivo_docx_path = Column(String(500), nullable=True)

    # Caminho do arquivo PDF gerado
    arquivo_pdf_path = Column(String(500), nullable=True)

    # Modelo de IA usado
    modelo_usado = Column(String(100), nullable=True)

    # Temperatura usada
    temperatura_usada = Column(String(10), nullable=True)

    # Thinking level usado
    thinking_level_usado = Column(String(20), nullable=True)

    # Tempo de processamento (segundos)
    tempo_processamento = Column(Integer, nullable=True)

    # Status do processamento
    status = Column(String(30), default=StatusProcessamento.INICIADO.value)

    # Mensagem de erro (se houver)
    erro_mensagem = Column(Text, nullable=True)

    # Usuário que gerou
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Timestamps
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relacionamentos
    feedback = relationship("FeedbackRelatorioCumprimento", back_populates="geracao", uselist=False)
    logs_ia = relationship("LogChamadaIARelatorioCumprimento", back_populates="geracao", order_by="LogChamadaIARelatorioCumprimento.criado_em")

    def __repr__(self):
        return f"<GeracaoRelatorioCumprimento(id={self.id}, cumprimento='{self.numero_cumprimento}')>"


class LogChamadaIARelatorioCumprimento(Base):
    """
    Log detalhado de cada chamada de IA durante o processamento.
    Permite debug e auditoria de todas as interações com o modelo.
    """
    __tablename__ = "logs_chamada_ia_relatorio_cumprimento"

    id = Column(Integer, primary_key=True, index=True)
    geracao_id = Column(Integer, ForeignKey("geracoes_relatorio_cumprimento.id"), nullable=True, index=True)

    # Identificação da etapa
    etapa = Column(String(50), nullable=False)  # "analise_documentos", "geracao_relatorio", "edicao"
    descricao = Column(String(200), nullable=True)  # Descrição legível da etapa

    # Entrada
    prompt_enviado = Column(Text, nullable=True)  # Prompt completo enviado à IA
    documentos_enviados = Column(JSON, nullable=True)  # Lista de documentos enviados

    # Saída
    resposta_ia = Column(Text, nullable=True)  # Resposta bruta da IA
    resposta_parseada = Column(JSON, nullable=True)  # Resposta parseada como JSON

    # Metadados
    modelo_usado = Column(String(100), nullable=True)
    temperatura_usada = Column(String(10), nullable=True)
    thinking_level_usado = Column(String(20), nullable=True)
    tokens_entrada = Column(Integer, nullable=True)
    tokens_saida = Column(Integer, nullable=True)
    tempo_ms = Column(Integer, nullable=True)  # Tempo de resposta em ms
    sucesso = Column(Boolean, default=True)
    erro = Column(Text, nullable=True)

    # Timestamp
    criado_em = Column(DateTime, default=get_utc_now)

    # Relacionamento
    geracao = relationship("GeracaoRelatorioCumprimento", back_populates="logs_ia")

    def __repr__(self):
        return f"<LogChamadaIARelatorioCumprimento(id={self.id}, etapa='{self.etapa}', sucesso={self.sucesso})>"


class FeedbackRelatorioCumprimento(Base):
    """Armazena feedback do usuário sobre o relatório gerado"""
    __tablename__ = "feedbacks_relatorio_cumprimento"

    id = Column(Integer, primary_key=True, index=True)
    geracao_id = Column(Integer, ForeignKey("geracoes_relatorio_cumprimento.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Avaliação: 'correto', 'parcial', 'incorreto', 'erro_ia'
    avaliacao = Column(String(20), nullable=False)

    # Nota de 1 a 5 estrelas
    nota = Column(Integer, nullable=True)

    # Comentário opcional do usuário
    comentario = Column(Text, nullable=True)

    # Campos específicos que tiveram problemas (opcional)
    campos_incorretos = Column(JSON, nullable=True)

    criado_em = Column(DateTime, default=get_utc_now)

    # Relacionamentos
    geracao = relationship("GeracaoRelatorioCumprimento", back_populates="feedback")

    def __repr__(self):
        return f"<FeedbackRelatorioCumprimento(id={self.id}, avaliacao='{self.avaliacao}')>"


# ============================================
# Dataclasses para Processamento
# ============================================

@dataclass
class DocumentoClassificado:
    """Documento baixado e classificado por categoria"""
    id_documento: str
    categoria: CategoriaDocumento
    nome_original: str
    nome_padronizado: str
    tipo_documento: Optional[str] = None  # Código do tipo no TJ-MS
    data_documento: Optional[date] = None
    descricao: Optional[str] = None
    processo_origem: Optional[str] = None  # "cumprimento" ou "principal"
    conteudo_texto: Optional[str] = None  # Texto extraído do documento
    path_local: Optional[str] = None  # Caminho local do arquivo

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "id_documento": self.id_documento,
            "categoria": self.categoria.value,
            "nome_original": self.nome_original,
            "nome_padronizado": self.nome_padronizado,
            "nome": self.nome_padronizado,  # Alias para compatibilidade com frontend
            "tipo_documento": self.tipo_documento,
            "data_documento": self.data_documento.strftime("%d/%m/%Y") if self.data_documento else None,
            "descricao": self.descricao,
            "processo_origem": self.processo_origem,
            "path_local": self.path_local
        }


@dataclass
class DadosProcesso:
    """Dados básicos extraídos do processo"""
    numero_processo: str
    numero_processo_formatado: Optional[str] = None
    autor: Optional[str] = None
    cpf_cnpj_autor: Optional[str] = None
    reu: str = "Estado de Mato Grosso do Sul"
    advogado_autor: Optional[str] = None
    oab_advogado: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    classe_processual: Optional[str] = None
    assunto: Optional[str] = None
    data_ajuizamento: Optional[date] = None
    valor_causa: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "numero_processo": self.numero_processo,
            "numero_processo_formatado": self.numero_processo_formatado,
            "autor": self.autor,
            "cpf_cnpj_autor": self.cpf_cnpj_autor,
            "reu": self.reu,
            "advogado_autor": self.advogado_autor,
            "oab_advogado": self.oab_advogado,
            "comarca": self.comarca,
            "vara": self.vara,
            "classe_processual": self.classe_processual,
            "assunto": self.assunto,
            "data_ajuizamento": self.data_ajuizamento.strftime("%d/%m/%Y") if self.data_ajuizamento else None,
            "valor_causa": self.valor_causa
        }


@dataclass
class InfoTransitoJulgado:
    """Informações sobre trânsito em julgado"""
    localizado: bool = False
    data_transito: Optional[date] = None
    fonte: Optional[str] = None  # "certidao", "movimento", "documento"
    id_documento: Optional[str] = None
    observacao: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "localizado": self.localizado,
            "data_transito": self.data_transito.strftime("%d/%m/%Y") if self.data_transito else None,
            "fonte": self.fonte,
            "id_documento": self.id_documento,
            "observacao": self.observacao
        }


@dataclass
class ResultadoColeta:
    """Resultado da coleta de documentos"""
    dados_cumprimento: DadosProcesso
    dados_principal: Optional[DadosProcesso] = None
    documentos: List[DocumentoClassificado] = field(default_factory=list)
    transito_julgado: Optional[InfoTransitoJulgado] = None
    erro: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "dados_cumprimento": self.dados_cumprimento.to_dict(),
            "dados_principal": self.dados_principal.to_dict() if self.dados_principal else None,
            "documentos": [d.to_dict() for d in self.documentos],
            "transito_julgado": self.transito_julgado.to_dict() if self.transito_julgado else None,
            "erro": self.erro
        }


@dataclass
class ResultadoRelatorio:
    """Resultado final da geração do relatório"""
    conteudo_markdown: str
    dados_basicos: Dict[str, Any]
    documentos_utilizados: List[DocumentoClassificado]
    transito_julgado: Optional[InfoTransitoJulgado] = None
    tempo_processamento_segundos: Optional[int] = None
    modelo_usado: Optional[str] = None
    erro: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "conteudo_markdown": self.conteudo_markdown,
            "dados_basicos": self.dados_basicos,
            "documentos_utilizados": [d.to_dict() for d in self.documentos_utilizados],
            "transito_julgado": self.transito_julgado.to_dict() if self.transito_julgado else None,
            "tempo_processamento_segundos": self.tempo_processamento_segundos,
            "modelo_usado": self.modelo_usado,
            "erro": self.erro
        }


# ============================================
# Dataclasses para Agravo de Instrumento
# ============================================

@dataclass
class AgravoCandidato:
    """
    Candidato a Agravo de Instrumento detectado no XML do processo de origem.

    Representa uma menção potencial a agravo que precisa ser validada
    comparando as partes do processo.
    """
    numero_cnj: str  # Número CNJ extraído (ex: 1400494-59.2026.8.12.0000)
    texto_original: str  # Texto completo onde foi encontrado
    fonte: str  # "movimento" ou "documento"
    data_movimento: Optional[date] = None  # Data do movimento onde foi encontrado

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "numero_cnj": self.numero_cnj,
            "texto_original": self.texto_original,
            "fonte": self.fonte,
            "data_movimento": self.data_movimento.strftime("%d/%m/%Y") if self.data_movimento else None
        }


@dataclass
class ParteProcesso:
    """Representa uma parte do processo (autor ou réu)"""
    nome: str
    nome_normalizado: str  # Nome após normalização
    polo: str  # "AT" (ativo) ou "PA" (passivo)
    documento: Optional[str] = None  # CPF/CNPJ

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "nome": self.nome,
            "nome_normalizado": self.nome_normalizado,
            "polo": self.polo,
            "documento": self.documento
        }


@dataclass
class AgravoValidado:
    """
    Agravo de Instrumento validado (confirmado por comparação de partes).

    Contém informações do agravo e seus documentos relevantes.
    """
    numero_cnj: str
    numero_formatado: str
    partes_polo_ativo: List[ParteProcesso] = field(default_factory=list)
    partes_polo_passivo: List[ParteProcesso] = field(default_factory=list)
    ids_decisoes: List[str] = field(default_factory=list)  # IDs de decisões
    ids_acordaos: List[str] = field(default_factory=list)  # IDs de acórdãos
    data_validacao: Optional[date] = None
    score_similaridade: float = 0.0  # Score da comparação de partes (0 a 1)

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "numero_cnj": self.numero_cnj,
            "numero_formatado": self.numero_formatado,
            "partes_polo_ativo": [p.to_dict() for p in self.partes_polo_ativo],
            "partes_polo_passivo": [p.to_dict() for p in self.partes_polo_passivo],
            "ids_decisoes": self.ids_decisoes,
            "ids_acordaos": self.ids_acordaos,
            "data_validacao": self.data_validacao.strftime("%d/%m/%Y") if self.data_validacao else None,
            "score_similaridade": self.score_similaridade
        }


@dataclass
class ResultadoDeteccaoAgravo:
    """
    Resultado completo da detecção de Agravo de Instrumento.

    Contém tanto os candidatos detectados quanto os validados.
    """
    candidatos_detectados: List[AgravoCandidato] = field(default_factory=list)
    agravos_validados: List[AgravoValidado] = field(default_factory=list)
    agravos_rejeitados: List[Dict[str, Any]] = field(default_factory=list)  # {candidato, motivo}
    erro: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "candidatos_detectados": [c.to_dict() for c in self.candidatos_detectados],
            "agravos_validados": [a.to_dict() for a in self.agravos_validados],
            "agravos_rejeitados": self.agravos_rejeitados,
            "erro": self.erro
        }
