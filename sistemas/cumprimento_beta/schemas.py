# sistemas/cumprimento_beta/schemas.py
"""
Schemas Pydantic para validação de requisições e respostas
do módulo Cumprimento de Sentença Beta
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
import re


# ==========================================
# Requests
# ==========================================

class IniciarSessaoRequest(BaseModel):
    """Requisição para iniciar uma nova sessão"""
    numero_processo: str = Field(..., min_length=15, max_length=50, description="Número do processo CNJ")

    @field_validator('numero_processo')
    @classmethod
    def validar_cnj(cls, v: str) -> str:
        """Valida e limpa o número CNJ"""
        # Remove caracteres não-dígitos para validação
        digitos = re.sub(r'\D', '', v)

        # CNJ deve ter 20 dígitos
        if len(digitos) != 20:
            raise ValueError("Número CNJ deve ter 20 dígitos")

        return v


class MensagemChatRequest(BaseModel):
    """Requisição para enviar mensagem no chatbot"""
    conteudo: str = Field(..., min_length=1, max_length=10000, description="Conteúdo da mensagem")


class GerarPecaRequest(BaseModel):
    """Requisição para gerar peça final"""
    tipo_peca: str = Field(..., min_length=1, max_length=100, description="Tipo da peça a gerar")
    instrucoes_adicionais: Optional[str] = Field(None, max_length=5000, description="Instruções extras")


# ==========================================
# Responses
# ==========================================

class IniciarSessaoResponse(BaseModel):
    """Resposta ao iniciar uma sessão"""
    sessao_id: int
    numero_processo: str
    numero_processo_formatado: Optional[str] = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentoResumoResponse(BaseModel):
    """Resumo de um documento da sessão"""
    id: int
    documento_id_tjms: str
    codigo_documento: int
    descricao_documento: Optional[str] = None
    data_documento: Optional[datetime] = None
    status_relevancia: str
    motivo_irrelevancia: Optional[str] = None
    tem_json: bool = False

    model_config = {"from_attributes": True}


class JSONResumoResponse(BaseModel):
    """JSON de resumo de um documento"""
    id: int
    documento_id: int
    json_conteudo: Dict[str, Any]
    categoria_nome: Optional[str] = None
    modelo_usado: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConsolidacaoResponse(BaseModel):
    """Resposta da consolidação"""
    id: int
    sessao_id: int
    resumo_consolidado: str
    sugestoes_pecas: Optional[List[Dict[str, Any]]] = None
    dados_processo: Optional[Dict[str, Any]] = None
    total_jsons_consolidados: int
    modelo_usado: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MensagemChatResponse(BaseModel):
    """Resposta de uma mensagem do chat"""
    id: int
    role: str
    conteudo: str
    modelo_usado: Optional[str] = None
    usou_busca_vetorial: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoricoConversaResponse(BaseModel):
    """Histórico completo de conversas"""
    sessao_id: int
    mensagens: List[MensagemChatResponse]
    total: int


class PecaGeradaResponse(BaseModel):
    """Resposta de uma peça gerada"""
    id: int
    sessao_id: int
    tipo_peca: str
    titulo: Optional[str] = None
    conteudo_markdown: str
    download_url: Optional[str] = None
    modelo_usado: str
    created_at: datetime

    model_config = {"from_attributes": True}


class StatusSessaoResponse(BaseModel):
    """Status completo de uma sessão"""
    id: int
    numero_processo: str
    numero_processo_formatado: Optional[str] = None
    status: str
    total_documentos: int
    documentos_processados: int
    documentos_relevantes: int
    documentos_irrelevantes: int
    documentos_ignorados: int
    erro_mensagem: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    finalizado_em: Optional[datetime] = None

    # Indicadores de progresso
    tem_consolidacao: bool = False
    total_conversas: int = 0
    total_pecas: int = 0

    model_config = {"from_attributes": True}


class ListaSessoesResponse(BaseModel):
    """Lista de sessões do usuário"""
    sessoes: List[StatusSessaoResponse]
    total: int
    pagina: int
    por_pagina: int


# ==========================================
# Streaming Events
# ==========================================

class StreamEventBase(BaseModel):
    """Base para eventos de streaming"""
    event: str
    data: Dict[str, Any]


class ProgressoProcessamentoEvent(BaseModel):
    """Evento de progresso do processamento"""
    event: str = "progresso"
    etapa: str  # baixando_docs, avaliando_relevancia, extraindo_json
    documento_atual: Optional[int] = None
    total_documentos: Optional[int] = None
    percentual: Optional[float] = None
    mensagem: Optional[str] = None


class DocumentoProcessadoEvent(BaseModel):
    """Evento quando um documento é processado"""
    event: str = "documento_processado"
    documento_id: int
    status_relevancia: str
    descricao: Optional[str] = None


class ConsolidacaoChunkEvent(BaseModel):
    """Chunk da consolidação em streaming"""
    event: str = "consolidacao_chunk"
    chunk: str
    finalizado: bool = False


class ChatChunkEvent(BaseModel):
    """Chunk da resposta do chat em streaming"""
    event: str = "chat_chunk"
    chunk: str
    finalizado: bool = False
    mensagem_id: Optional[int] = None


class ErroEvent(BaseModel):
    """Evento de erro"""
    event: str = "erro"
    mensagem: str
    detalhes: Optional[str] = None
