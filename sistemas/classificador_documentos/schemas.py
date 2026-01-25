# sistemas/classificador_documentos/schemas.py
"""
Schemas Pydantic para validação de requests/responses do Sistema de Classificação

Autor: LAB/PGE-MS
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============================================
# Schemas de Prompt
# ============================================

class PromptCreate(BaseModel):
    """Request para criar um prompt"""
    nome: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = None
    conteudo: str = Field(..., min_length=10)
    codigos_documento: Optional[str] = Field(None, max_length=500, description="Códigos de tipos de documento TJ-MS separados por vírgula (ex: 8,15,34)")


class PromptUpdate(BaseModel):
    """Request para atualizar um prompt"""
    nome: Optional[str] = Field(None, min_length=1, max_length=200)
    descricao: Optional[str] = None
    conteudo: Optional[str] = Field(None, min_length=10)
    codigos_documento: Optional[str] = Field(None, max_length=500)
    ativo: Optional[bool] = None


class PromptResponse(BaseModel):
    """Response com dados de um prompt"""
    id: int
    nome: str
    descricao: Optional[str]
    conteudo: str
    codigos_documento: Optional[str]
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


# ============================================
# Schemas de Projeto
# ============================================

class ProjetoCreate(BaseModel):
    """Request para criar um projeto"""
    nome: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = None
    prompt_id: Optional[int] = None
    modelo: str = "google/gemini-2.5-flash-lite"
    modo_processamento: str = "chunk"
    posicao_chunk: str = "fim"
    tamanho_chunk: int = Field(512, ge=100, le=4000)
    max_concurrent: int = Field(3, ge=1, le=10)


class ProjetoUpdate(BaseModel):
    """Request para atualizar um projeto"""
    nome: Optional[str] = Field(None, min_length=1, max_length=200)
    descricao: Optional[str] = None
    prompt_id: Optional[int] = None
    modelo: Optional[str] = None
    modo_processamento: Optional[str] = None
    posicao_chunk: Optional[str] = None
    tamanho_chunk: Optional[int] = Field(None, ge=100, le=4000)
    max_concurrent: Optional[int] = Field(None, ge=1, le=10)
    ativo: Optional[bool] = None


class ProjetoResponse(BaseModel):
    """Response com dados de um projeto"""
    id: int
    nome: str
    descricao: Optional[str]
    prompt_id: Optional[int]
    modelo: str
    modo_processamento: str
    posicao_chunk: str
    tamanho_chunk: int
    max_concurrent: int
    ativo: bool
    total_codigos: int = 0
    total_execucoes: int = 0
    ultima_execucao: Optional[datetime] = None
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


# ============================================
# Schemas de Código de Documento
# ============================================

class CodigoDocumentoCreate(BaseModel):
    """Request para adicionar código de documento a um projeto"""
    codigo: str = Field(..., min_length=1, max_length=100)
    numero_processo: Optional[str] = Field(None, max_length=30)
    descricao: Optional[str] = Field(None, max_length=500)
    fonte: str = "tjms"


class CodigoDocumentoBulkCreate(BaseModel):
    """Request para adicionar múltiplos códigos de documento"""
    codigos: List[str] = Field(..., min_items=1)
    numero_processo: Optional[str] = None
    fonte: str = "tjms"


class CodigoDocumentoResponse(BaseModel):
    """Response com dados de um código de documento"""
    id: int
    projeto_id: int
    codigo: str
    numero_processo: Optional[str]
    descricao: Optional[str]
    fonte: str
    ativo: bool
    criado_em: datetime

    class Config:
        from_attributes = True


# ============================================
# Schemas de Execução
# ============================================

class ExecucaoCreate(BaseModel):
    """Request para iniciar uma execução"""
    projeto_id: int
    codigos_ids: Optional[List[int]] = None  # Se None, processa todos os códigos ativos


class ExecucaoResponse(BaseModel):
    """Response com dados de uma execução"""
    id: int
    projeto_id: int
    status: str
    total_arquivos: int
    arquivos_processados: int
    arquivos_sucesso: int
    arquivos_erro: int
    progresso_percentual: float
    modelo_usado: Optional[str]
    config_usada: Optional[Dict[str, Any]]
    erro_mensagem: Optional[str]
    iniciado_em: Optional[datetime]
    finalizado_em: Optional[datetime]
    criado_em: datetime

    class Config:
        from_attributes = True


# ============================================
# Schemas de Resultado
# ============================================

class ResultadoResponse(BaseModel):
    """Response com dados de um resultado de classificação"""
    id: int
    execucao_id: int
    codigo_documento: str
    numero_processo: Optional[str]
    nome_arquivo: Optional[str]
    status: str
    fonte: str
    texto_extraido_via: Optional[str]
    tokens_extraidos: Optional[int]
    categoria: Optional[str]
    subcategoria: Optional[str]
    confianca: Optional[str]
    justificativa: Optional[str]
    erro_mensagem: Optional[str]
    processado_em: Optional[datetime]
    criado_em: datetime

    class Config:
        from_attributes = True


class ResultadoFiltros(BaseModel):
    """Filtros para listar resultados"""
    categoria: Optional[str] = None
    confianca: Optional[str] = None
    status: Optional[str] = None
    apenas_erros: bool = False


# ============================================
# Schemas de Exportação
# ============================================

class ExportacaoRequest(BaseModel):
    """Request para exportar resultados"""
    execucao_id: int
    formato: str = "excel"  # "excel" ou "csv"
    filtros: Optional[ResultadoFiltros] = None


# ============================================
# Schemas de Classificação Avulsa (upload manual)
# ============================================

class ClassificacaoAvulsaRequest(BaseModel):
    """Request para classificar documentos avulsos (upload)"""
    modelo: str = "google/gemini-2.5-flash-lite"
    prompt_id: Optional[int] = None
    prompt_texto: Optional[str] = None
    modo_processamento: str = "chunk"
    posicao_chunk: str = "fim"
    tamanho_chunk: int = Field(512, ge=100, le=4000)
    codigos: Optional[List[str]] = None  # Códigos para associar aos arquivos


# ============================================
# Schemas de Status da API
# ============================================

class StatusAPIResponse(BaseModel):
    """Response com status da API OpenRouter"""
    disponivel: bool
    modelo_padrao: str
    modelos_disponiveis: List[str]


# ============================================
# Schemas de Configuração
# ============================================

class ConfiguracaoClassificador(BaseModel):
    """Configurações do classificador"""
    modelo_padrao: str = "google/gemini-2.5-flash-lite"
    modelos_disponiveis: List[str] = [
        "google/gemini-2.5-flash-lite",
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
        "anthropic/claude-sonnet-4",
        "openai/gpt-4o-mini"
    ]
    modo_processamento_padrao: str = "chunk"
    tamanho_chunk_padrao: int = 512
    max_concurrent_padrao: int = 3
    timeout_segundos: int = 60
    retry_delays: List[int] = [5, 15, 30]
