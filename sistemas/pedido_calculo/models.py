# sistemas/pedido_calculo/models.py
"""
Modelos de dados para o sistema de Pedido de Cálculo

Define as estruturas de dados usadas pelo sistema:
- DadosBasicos: informações extraídas do XML
- DocumentoParaDownload: documentos identificados para análise
- InformacoesExtraidas: dados extraídos dos PDFs
- PedidoCalculo: resultado final gerado
- GeracaoPedidoCalculo: modelo SQLAlchemy para persistência

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
# Modelo SQLAlchemy para Persistência
# ============================================

class GeracaoPedidoCalculo(Base):
    """Armazena gerações de pedidos de cálculo realizadas"""
    __tablename__ = "geracoes_pedido_calculo"

    id = Column(Integer, primary_key=True, index=True)
    numero_cnj = Column(String(30), nullable=False, index=True)
    numero_cnj_formatado = Column(String(30), nullable=True)

    # Dados do processo (JSON do TJ-MS)
    dados_processo = Column(JSON, nullable=True)

    # Dados extraídos pelos agentes
    dados_agente1 = Column(JSON, nullable=True)  # Resultado do Agente 1
    dados_agente2 = Column(JSON, nullable=True)  # Resultado do Agente 2

    # Lista de documentos baixados (JSON)
    documentos_baixados = Column(JSON, nullable=True)

    # Conteúdo gerado pela IA em Markdown
    conteudo_gerado = Column(Text, nullable=True)

    # Histórico de conversas do chat de edição (JSON array)
    historico_chat = Column(JSON, nullable=True)

    # Caminho do arquivo DOCX gerado
    arquivo_path = Column(String(500), nullable=True)

    # Modelo de IA usado
    modelo_usado = Column(String(100), nullable=True)

    # Tempo de processamento (segundos)
    tempo_processamento = Column(Integer, nullable=True)

    # Usuário que gerou
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Timestamps
    criado_em = Column(DateTime, default=get_utc_now)
    atualizado_em = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relacionamentos
    feedback = relationship("FeedbackPedidoCalculo", back_populates="geracao", uselist=False)
    logs_ia = relationship("LogChamadaIA", back_populates="geracao", order_by="LogChamadaIA.criado_em")

    def __repr__(self):
        return f"<GeracaoPedidoCalculo(id={self.id}, cnj='{self.numero_cnj}')>"


class LogChamadaIA(Base):
    """
    Log detalhado de cada chamada de IA durante o processamento.
    Permite debug e auditoria de todas as interações com o modelo.
    """
    __tablename__ = "logs_chamada_ia_pedido_calculo"

    id = Column(Integer, primary_key=True, index=True)
    geracao_id = Column(Integer, ForeignKey("geracoes_pedido_calculo.id"), nullable=True, index=True)

    # Identificação da etapa
    etapa = Column(String(50), nullable=False)  # "analise_xml", "analise_certidao", "extracao_docs", "geracao_pedido"
    descricao = Column(String(200), nullable=True)  # Descrição legível da etapa

    # Entrada
    prompt_enviado = Column(Text, nullable=True)  # Prompt completo enviado à IA
    documento_id = Column(String(100), nullable=True)  # ID do documento sendo analisado (se aplicável)
    documento_texto = Column(Text, nullable=True)  # Texto do documento (para debug)

    # Saída
    resposta_ia = Column(Text, nullable=True)  # Resposta bruta da IA
    resposta_parseada = Column(JSON, nullable=True)  # Resposta parseada como JSON

    # Metadados
    modelo_usado = Column(String(100), nullable=True)
    tokens_entrada = Column(Integer, nullable=True)
    tokens_saida = Column(Integer, nullable=True)
    tempo_ms = Column(Integer, nullable=True)  # Tempo de resposta em ms
    sucesso = Column(Boolean, default=True)
    erro = Column(Text, nullable=True)

    # Timestamp
    criado_em = Column(DateTime, default=get_utc_now)

    # Relacionamento
    geracao = relationship("GeracaoPedidoCalculo", back_populates="logs_ia")

    def __repr__(self):
        return f"<LogChamadaIA(id={self.id}, etapa='{self.etapa}', sucesso={self.sucesso})>"


class FeedbackPedidoCalculo(Base):
    """Armazena feedback do usuário sobre o pedido gerado"""
    __tablename__ = "feedbacks_pedido_calculo"

    id = Column(Integer, primary_key=True, index=True)
    geracao_id = Column(Integer, ForeignKey("geracoes_pedido_calculo.id"), nullable=False)
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
    geracao = relationship("GeracaoPedidoCalculo", back_populates="feedback")

    def __repr__(self):
        return f"<FeedbackPedidoCalculo(id={self.id}, avaliacao='{self.avaliacao}')>"


# ============================================
# Dataclasses para Processamento
# ============================================


class TipoIntimacao(str, Enum):
    """Tipos de intimação/citação identificados no processo"""
    CITACAO = "citacao"
    INTIMACAO_IMPUGNACAO = "intimacao_impugnacao"
    INTIMACAO_SENTENCA = "intimacao_sentenca"
    OUTRO = "outro"


@dataclass
class CertidaoCandidata:
    """Certidão candidata para análise pela IA"""
    id_documento: str
    tipo_documento: str  # "9508" ou "13"
    data_documento: Optional[date] = None
    descricao: Optional[str] = None


@dataclass
class CertidaoCitacaoIntimacao:
    """Certidão de citação ou intimação com data de recebimento"""
    tipo: TipoIntimacao
    data_expedicao: Optional[date] = None
    id_certidao_9508: Optional[str] = None  # ID da certidão (9508 ou 13)
    data_certidao: Optional[date] = None
    data_recebimento: Optional[date] = None  # Data real de recebimento pela PGE (extraída do texto)
    termo_inicial_prazo: Optional[date] = None  # Primeiro dia útil posterior (art. 224 CPC)
    tipo_certidao: Optional[str] = None  # "sistema" (9508) ou "cartorio" (13 - decurso prazo)
    identificado_por_ia: bool = False  # Se foi identificado pela IA


@dataclass
class DocumentoCumprimento:
    """Documento do pedido de cumprimento de sentença"""
    id: str
    descricao: str
    tipo_documento: Optional[str] = None


@dataclass
class DadosBasicos:
    """Dados básicos extraídos diretamente do XML do processo"""
    numero_processo: str
    autor: str
    cpf_autor: Optional[str] = None  # CPF ou CNPJ da parte autora (formatado)
    reu: str = "Estado de Mato Grosso do Sul"
    comarca: Optional[str] = None
    vara: Optional[str] = None
    data_ajuizamento: Optional[date] = None
    valor_causa: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "numero_processo": self.numero_processo,
            "autor": self.autor,
            "cpf_autor": self.cpf_autor,
            "reu": self.reu,
            "comarca": self.comarca,
            "vara": self.vara,
            "data_ajuizamento": self.data_ajuizamento.strftime("%d/%m/%Y") if self.data_ajuizamento else None,
            "valor_causa": self.valor_causa
        }


@dataclass
class DocumentosParaDownload:
    """Documentos identificados pelo Agente 1 para download"""
    sentencas: List[str] = field(default_factory=list)
    acordaos: List[str] = field(default_factory=list)
    decisoes: List[str] = field(default_factory=list)  # Decisões interlocutórias (cumprimento de decisão)
    certidoes_citacao_intimacao: List[CertidaoCitacaoIntimacao] = field(default_factory=list)
    certidoes_candidatas: List[CertidaoCandidata] = field(default_factory=list)  # Para análise pela IA
    certidao_heuristica: Optional[CertidaoCitacaoIntimacao] = None  # Sugestão da heurística (IA tem prioridade)
    pedido_cumprimento: Dict[str, Any] = field(default_factory=dict)
    data_movimento_cumprimento: Optional[date] = None  # Data do movimento de intimação p/ cumprimento
    certidao_transito: Optional[str] = None  # ID da certidão de trânsito em julgado
    # Campos para cumprimentos autônomos
    is_cumprimento_autonomo: bool = False  # Se é um processo de cumprimento separado
    numero_processo_origem: Optional[str] = None  # Número CNJ do processo de origem
    id_peticao_inicial: Optional[str] = None  # ID da primeira petição (para extrair nº origem com IA)
    certidoes_origem: List[CertidaoCitacaoIntimacao] = field(default_factory=list)  # Certidões do processo de origem

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "sentencas": self.sentencas,
            "acordaos": self.acordaos,
            "decisoes": self.decisoes,
            "certidoes_citacao_intimacao": [
                {
                    "tipo": c.tipo.value,
                    "data_expedicao": c.data_expedicao.strftime("%d/%m/%Y") if c.data_expedicao else None,
                    "id_certidao_9508": c.id_certidao_9508,
                    "data_certidao": c.data_certidao.strftime("%d/%m/%Y") if c.data_certidao else None,
                    "data_recebimento": c.data_recebimento.strftime("%d/%m/%Y") if c.data_recebimento else None,
                    "termo_inicial_prazo": c.termo_inicial_prazo.strftime("%d/%m/%Y") if c.termo_inicial_prazo else None,
                    "tipo_certidao": c.tipo_certidao,
                    "identificado_por_ia": c.identificado_por_ia
                }
                for c in self.certidoes_citacao_intimacao
            ],
            "certidoes_candidatas": [
                {
                    "id_documento": c.id_documento,
                    "tipo_documento": c.tipo_documento,
                    "data_documento": c.data_documento.strftime("%d/%m/%Y") if c.data_documento else None,
                    "descricao": c.descricao
                }
                for c in self.certidoes_candidatas
            ],
            "pedido_cumprimento": self.pedido_cumprimento,
            "data_movimento_cumprimento": self.data_movimento_cumprimento.strftime("%d/%m/%Y") if self.data_movimento_cumprimento else None,
            "certidao_transito": self.certidao_transito,
            "is_cumprimento_autonomo": self.is_cumprimento_autonomo,
            "numero_processo_origem": self.numero_processo_origem,
            "id_peticao_inicial": self.id_peticao_inicial
        }


@dataclass
class MovimentosRelevantes:
    """Movimentos processuais relevantes identificados"""
    citacao_expedida: Optional[date] = None
    transito_julgado: Optional[date] = None
    intimacao_impugnacao_expedida: Optional[date] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "citacao_expedida": self.citacao_expedida.strftime("%d/%m/%Y") if self.citacao_expedida else None,
            "transito_julgado": self.transito_julgado.strftime("%d/%m/%Y") if self.transito_julgado else None,
            "intimacao_impugnacao_expedida": self.intimacao_impugnacao_expedida.strftime("%d/%m/%Y") if self.intimacao_impugnacao_expedida else None
        }


@dataclass
class ResultadoAgente1:
    """Resultado da análise do XML pelo Agente 1"""
    dados_basicos: DadosBasicos
    documentos_para_download: DocumentosParaDownload
    movimentos_relevantes: MovimentosRelevantes
    erro: Optional[str] = None
    # Dados do processo de origem (preenchido quando é cumprimento autônomo)
    dados_processo_origem: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário JSON-serializável"""
        return {
            "dados_basicos": self.dados_basicos.to_dict(),
            "documentos_para_download": self.documentos_para_download.to_dict(),
            "movimentos_relevantes": self.movimentos_relevantes.to_dict(),
            "erro": self.erro,
            "dados_processo_origem": self.dados_processo_origem
        }


@dataclass
class PeriodoCondenacao:
    """Período da condenação"""
    inicio: Optional[str] = None  # MM/AAAA
    fim: Optional[str] = None  # MM/AAAA


@dataclass
class CorrecaoMonetaria:
    """Critérios de correção monetária"""
    indice: Optional[str] = None  # Ex: "IPCA-E até 08/12/2021, após SELIC"
    termo_inicial: Optional[str] = None
    termo_final: Optional[str] = None
    observacao: Optional[str] = None


@dataclass
class JurosMoratorios:
    """Critérios de juros moratórios"""
    taxa: Optional[str] = None
    termo_inicial: Optional[str] = None
    termo_final: Optional[str] = None
    observacao: Optional[str] = None


@dataclass
class DatasProcessuais:
    """Datas processuais relevantes"""
    citacao_recebimento: Optional[date] = None
    transito_julgado: Optional[date] = None
    intimacao_impugnacao_recebimento: Optional[date] = None


@dataclass
class CalculoExequente:
    """Dados do cálculo apresentado pelo exequente"""
    valor_total: Optional[str] = None
    data_base: Optional[str] = None
    metodologia: Optional[str] = None


@dataclass
class ResultadoAgente2:
    """Resultado da extração de informações dos PDFs pelo Agente 2"""
    objeto_condenacao: Optional[str] = None
    valor_solicitado_parte: Optional[str] = None
    periodo_condenacao: Optional[PeriodoCondenacao] = None
    correcao_monetaria: Optional[CorrecaoMonetaria] = None
    juros_moratorios: Optional[JurosMoratorios] = None
    datas: Optional[DatasProcessuais] = None
    criterios_calculo: List[str] = field(default_factory=list)
    calculo_exequente: Optional[CalculoExequente] = None
    erro: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "objeto_condenacao": self.objeto_condenacao,
            "valor_solicitado_parte": self.valor_solicitado_parte,
            "periodo_condenacao": {
                "inicio": self.periodo_condenacao.inicio if self.periodo_condenacao else None,
                "fim": self.periodo_condenacao.fim if self.periodo_condenacao else None
            },
            "correcao_monetaria": {
                "indice": self.correcao_monetaria.indice if self.correcao_monetaria else None,
                "termo_inicial": self.correcao_monetaria.termo_inicial if self.correcao_monetaria else None,
                "termo_final": self.correcao_monetaria.termo_final if self.correcao_monetaria else None,
                "observacao": self.correcao_monetaria.observacao if self.correcao_monetaria else None
            },
            "juros_moratorios": {
                "taxa": self.juros_moratorios.taxa if self.juros_moratorios else None,
                "termo_inicial": self.juros_moratorios.termo_inicial if self.juros_moratorios else None,
                "termo_final": self.juros_moratorios.termo_final if self.juros_moratorios else None,
                "observacao": self.juros_moratorios.observacao if self.juros_moratorios else None
            },
            "datas": {
                "citacao_recebimento": self.datas.citacao_recebimento.strftime("%d/%m/%Y") if self.datas and self.datas.citacao_recebimento else None,
                "transito_julgado": self.datas.transito_julgado.strftime("%d/%m/%Y") if self.datas and self.datas.transito_julgado else None,
                "intimacao_impugnacao_recebimento": self.datas.intimacao_impugnacao_recebimento.strftime("%d/%m/%Y") if self.datas and self.datas.intimacao_impugnacao_recebimento else None
            },
            "criterios_calculo": self.criterios_calculo,
            "calculo_exequente": {
                "valor_total": self.calculo_exequente.valor_total if self.calculo_exequente else None,
                "data_base": self.calculo_exequente.data_base if self.calculo_exequente else None
            },
            "erro": self.erro
        }


@dataclass
class PedidoCalculo:
    """Pedido de cálculo gerado pelo Agente 3"""
    # Dados básicos do processo
    autor: str
    cpf_autor: Optional[str]  # CPF ou CNPJ da parte autora (formatado)
    reu: str
    numero_processo: str
    comarca: Optional[str]
    vara: Optional[str]
    pgenet_numero: Optional[str] = None  # Preenchido manualmente ou via integração
    
    # Objeto e valor
    objeto_condenacao: Optional[str] = None
    valor_solicitado_parte: Optional[str] = None
    
    # Prazos
    prazo_termo_inicial: Optional[date] = None
    prazo_termo_final: Optional[date] = None
    
    # Datas
    data_citacao: Optional[date] = None
    data_ajuizamento: Optional[date] = None
    transito_julgado: Optional[date] = None
    prazo_calculo: Optional[str] = None
    
    # Critérios de cálculo
    correcao_monetaria: Optional[CorrecaoMonetaria] = None
    juros_moratorios: Optional[JurosMoratorios] = None
    periodo_condenacao: Optional[PeriodoCondenacao] = None
    criterios_calculo: List[str] = field(default_factory=list)
    
    # Responsáveis
    procurador_responsavel: Optional[str] = None
    assessor_responsavel: Optional[str] = None
    data_geracao: date = field(default_factory=date.today)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário"""
        return {
            "autor": self.autor,
            "cpf_autor": self.cpf_autor,
            "reu": self.reu,
            "numero_processo": self.numero_processo,
            "comarca": self.comarca,
            "vara": self.vara,
            "pgenet_numero": self.pgenet_numero,
            "objeto_condenacao": self.objeto_condenacao,
            "valor_solicitado_parte": self.valor_solicitado_parte,
            "prazo_termo_inicial": self.prazo_termo_inicial.strftime("%d/%m/%Y") if self.prazo_termo_inicial else None,
            "prazo_termo_final": self.prazo_termo_final.strftime("%d/%m/%Y") if self.prazo_termo_final else None,
            "data_citacao": self.data_citacao.strftime("%d/%m/%Y") if self.data_citacao else None,
            "data_ajuizamento": self.data_ajuizamento.strftime("%d/%m/%Y") if self.data_ajuizamento else None,
            "transito_julgado": self.transito_julgado.strftime("%d/%m/%Y") if self.transito_julgado else None,
            "prazo_calculo": self.prazo_calculo,
            "correcao_monetaria": {
                "indice": self.correcao_monetaria.indice if self.correcao_monetaria else None,
                "termo_inicial": self.correcao_monetaria.termo_inicial if self.correcao_monetaria else None,
                "termo_final": self.correcao_monetaria.termo_final if self.correcao_monetaria else None,
                "observacao": self.correcao_monetaria.observacao if self.correcao_monetaria else None
            },
            "juros_moratorios": {
                "taxa": self.juros_moratorios.taxa if self.juros_moratorios else None,
                "termo_inicial": self.juros_moratorios.termo_inicial if self.juros_moratorios else None,
                "termo_final": self.juros_moratorios.termo_final if self.juros_moratorios else None,
                "observacao": self.juros_moratorios.observacao if self.juros_moratorios else None
            },
            "periodo_condenacao": {
                "inicio": self.periodo_condenacao.inicio if self.periodo_condenacao else None,
                "fim": self.periodo_condenacao.fim if self.periodo_condenacao else None
            },
            "criterios_calculo": self.criterios_calculo,
            "procurador_responsavel": self.procurador_responsavel,
            "assessor_responsavel": self.assessor_responsavel,
            "data_geracao": self.data_geracao.strftime("%d/%m/%Y") if self.data_geracao else None
        }
