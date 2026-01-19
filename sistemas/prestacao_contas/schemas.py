# sistemas/prestacao_contas/schemas.py
"""
Schemas Pydantic para o sistema de Prestação de Contas
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


# =====================================================
# REQUESTS
# =====================================================

class AnalisarProcessoRequest(BaseModel):
    """Request para análise completa de um processo"""
    numero_cnj: str = Field(..., description="Número CNJ do processo")
    sobrescrever_existente: bool = Field(default=False, description="Se True, refaz análise mesmo se já existir")


class BaixarSubcontaRequest(BaseModel):
    """Request para baixar extrato da subconta"""
    numero_cnj: str


class BuscarProcessoRequest(BaseModel):
    """Request para buscar XML do processo"""
    numero_cnj: str


class ResponderDuvidaRequest(BaseModel):
    """Request para responder dúvida da IA"""
    geracao_id: int
    respostas: Dict[str, str] = Field(..., description="Dict com pergunta -> resposta")


class FeedbackRequest(BaseModel):
    """Request para submeter feedback"""
    geracao_id: int
    avaliacao: Literal["correto", "parcial", "incorreto", "erro_ia"]
    nota: Optional[int] = Field(None, ge=1, le=5)
    comentario: Optional[str] = None
    parecer_correto: Optional[bool] = None
    valores_corretos: Optional[bool] = None
    medicamento_correto: Optional[bool] = None


class ExportarParecerRequest(BaseModel):
    """Request para exportar parecer em DOCX"""
    geracao_id: int


# =====================================================
# RESPONSES
# =====================================================

class DocumentoAnexo(BaseModel):
    """Documento anexado à prestação de contas"""
    id: str
    tipo: Optional[str] = None
    codigo_tipo: Optional[str] = None
    data: Optional[datetime] = None
    texto: Optional[str] = None


class ResultadoSubconta(BaseModel):
    """Resultado da extração do extrato da subconta"""
    sucesso: bool
    pdf_path: Optional[str] = None
    texto_extraido: Optional[str] = None
    erro: Optional[str] = None


class ResultadoXML(BaseModel):
    """Resultado da consulta ao XML do processo"""
    sucesso: bool
    dados_basicos: Optional[Dict[str, Any]] = None
    documentos: Optional[List[Dict[str, Any]]] = None
    erro: Optional[str] = None


class ResultadoIdentificacao(BaseModel):
    """Resultado da identificação da petição de prestação de contas"""
    encontrada: bool
    peticao_id: Optional[str] = None
    peticao_data: Optional[datetime] = None
    peticao_texto: Optional[str] = None
    metodo_identificacao: Optional[str] = None  # 'regex' ou 'llm'
    confianca: Optional[float] = None
    documentos_mesmo_dia: Optional[List[DocumentoAnexo]] = None
    peticao_inicial_texto: Optional[str] = None
    erro: Optional[str] = None


class ResultadoAnalise(BaseModel):
    """Resultado da análise de prestação de contas"""
    parecer: Literal["favoravel", "desfavoravel", "duvida"]
    fundamentacao: str  # Markdown

    # Valores extraídos
    valor_bloqueado: Optional[float] = None
    valor_utilizado: Optional[float] = None
    valor_devolvido: Optional[float] = None
    medicamento_pedido: Optional[str] = None
    medicamento_comprado: Optional[str] = None

    # Se desfavorável
    irregularidades: Optional[List[str]] = None

    # Se dúvida
    perguntas: Optional[List[str]] = None
    contexto_duvida: Optional[str] = None


class GeracaoResponse(BaseModel):
    """Response com dados de uma geração/análise"""
    id: int
    numero_cnj: str
    numero_cnj_formatado: Optional[str] = None
    status: str
    parecer: Optional[str] = None
    fundamentacao: Optional[str] = None
    irregularidades: Optional[List[str]] = None
    perguntas_usuario: Optional[List[str]] = None

    # Valores
    valor_bloqueado: Optional[float] = None
    valor_utilizado: Optional[float] = None
    valor_devolvido: Optional[float] = None
    medicamento_pedido: Optional[str] = None
    medicamento_comprado: Optional[str] = None

    # Metadados
    modelo_usado: Optional[str] = None
    tempo_processamento_ms: Optional[int] = None
    erro: Optional[str] = None
    criado_em: datetime

    # Estado para retomada (quando aguardando documentos)
    documentos_faltantes: Optional[List[str]] = None  # ['extrato_subconta', 'notas_fiscais']
    mensagem_erro_usuario: Optional[str] = None  # Mensagem amigável sobre o que falta
    estado_expira_em: Optional[datetime] = None  # Quando expira o estado salvo
    estado_expirado: Optional[bool] = None  # True se já expirou (calculado)
    permite_anexar: Optional[bool] = None  # True se pode anexar documentos

    class Config:
        from_attributes = True


class GeracaoDetalhadaResponse(GeracaoResponse):
    """Response detalhada com todos os dados de debug"""
    extrato_subconta_texto: Optional[str] = None
    extrato_subconta_pdf_base64: Optional[str] = None  # PDF em base64 (se disponível)
    peticao_inicial_id: Optional[str] = None
    peticao_inicial_texto: Optional[str] = None
    peticao_prestacao_id: Optional[str] = None
    peticao_prestacao_texto: Optional[str] = None
    documentos_anexos: Optional[List[Dict[str, Any]]] = None
    peticoes_relevantes: Optional[List[Dict[str, Any]]] = None
    dados_processo_xml: Optional[Dict[str, Any]] = None
    prompt_identificacao: Optional[str] = None
    prompt_analise: Optional[str] = None
    resposta_ia_bruta: Optional[str] = None
    respostas_usuario: Optional[Dict[str, str]] = None


class LogChamadaIAResponse(BaseModel):
    """Response com dados de um log de chamada de IA"""
    id: int
    etapa: str
    descricao: Optional[str] = None
    prompt_enviado: Optional[str] = None
    documento_id: Optional[str] = None
    resposta_ia: Optional[str] = None
    resposta_parseada: Optional[Dict[str, Any]] = None
    modelo_usado: Optional[str] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    tempo_ms: Optional[int] = None
    sucesso: bool
    erro: Optional[str] = None
    criado_em: datetime

    class Config:
        from_attributes = True


class HistoricoResponse(BaseModel):
    """Response com lista de gerações do histórico"""
    total: int
    geracoes: List[GeracaoResponse]


class FeedbackResponse(BaseModel):
    """Response após submissão de feedback"""
    sucesso: bool
    mensagem: str
    feedback_id: Optional[int] = None


# =====================================================
# EVENTOS SSE (Server-Sent Events)
# =====================================================

class EventoSSE(BaseModel):
    """Evento para streaming SSE"""
    tipo: Literal["inicio", "etapa", "progresso", "info", "aviso", "erro", "sucesso", "resultado", "fim", "solicitar_documentos"]
    etapa: Optional[int] = None  # 1-5
    etapa_nome: Optional[str] = None
    mensagem: Optional[str] = None
    dados: Optional[Dict[str, Any]] = None
    progresso: Optional[int] = None  # 0-100
