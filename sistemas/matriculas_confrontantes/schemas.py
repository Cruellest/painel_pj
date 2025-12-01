# sistemas/matriculas_confrontantes/schemas.py
"""
Schemas Pydantic para o sistema Matrículas Confrontantes
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==========================================
# Schemas de Arquivo
# ==========================================

class FileInfo(BaseModel):
    """Informações de um arquivo"""
    id: str
    name: str
    path: str
    type: str  # 'pdf' ou 'image'
    size: str
    date: str
    analyzed: bool = False


class FileUploadResponse(BaseModel):
    """Resposta de upload de arquivo"""
    success: bool
    file: Optional[FileInfo] = None
    error: Optional[str] = None
    message: Optional[str] = None


# ==========================================
# Schemas de Análise
# ==========================================

class LoteConfrontante(BaseModel):
    """Lote confrontante identificado"""
    descricao: str
    direcao: Optional[str] = None
    proprietarios: List[str] = []


class AnaliseResponse(BaseModel):
    """Resposta de uma análise"""
    id: str
    matricula: Optional[str] = None
    lote: Optional[str] = None
    dataOperacao: str
    tipo: str = "Matrícula"
    proprietario: str = "N/A"
    estado: str = "Analisado"
    confianca: int = 0
    confrontantes: List[LoteConfrontante] = []
    num_confrontantes: int = 0


class AnaliseStatusResponse(BaseModel):
    """Status de uma análise em andamento"""
    processing: bool
    analyzed: bool
    has_result: bool


class ResultadoAnalise(BaseModel):
    """Resultado completo de uma análise"""
    arquivo: str
    matricula_principal: Optional[str]
    matriculas_confrontantes: List[str]
    lotes_confrontantes: List[Dict[str, Any]]
    matriculas_nao_confrontantes: List[str]
    lotes_sem_matricula: List[str]
    confrontacao_completa: Optional[bool]
    proprietarios_identificados: Dict[str, List[str]]
    confidence: Optional[float]
    reasoning: str


# ==========================================
# Schemas de Registro
# ==========================================

class RegistroBase(BaseModel):
    """Base para registro"""
    matricula: str
    dataOperacao: Optional[str] = None
    tipo: str = "Imovel"
    proprietario: Optional[str] = None
    estado: str = "Pendente"
    confianca: float = 0.0
    children: List[Dict] = []


class RegistroCreate(RegistroBase):
    """Schema para criação de registro"""
    pass


class RegistroUpdate(BaseModel):
    """Schema para atualização de registro"""
    matricula: Optional[str] = None
    dataOperacao: Optional[str] = None
    tipo: Optional[str] = None
    proprietario: Optional[str] = None
    estado: Optional[str] = None
    confianca: Optional[float] = None
    expanded: Optional[bool] = None
    children: Optional[List[Dict]] = None


class RegistroResponse(RegistroBase):
    """Resposta de registro"""
    id: int
    expanded: bool = False

    class Config:
        from_attributes = True


# ==========================================
# Schemas de Configuração
# ==========================================

class ConfigResponse(BaseModel):
    """Configuração do sistema"""
    version: str
    model: str
    hasApiKey: bool
    has_api_key: bool
    analysis_available: bool


class ApiKeyRequest(BaseModel):
    """Request para definir API Key"""
    api_key: str


class ModelRequest(BaseModel):
    """Request para definir modelo"""
    model: str


# ==========================================
# Schemas de Relatório
# ==========================================

class RelatorioResponse(BaseModel):
    """Resposta de geração de relatório"""
    success: bool
    report: Optional[str] = None
    payload: Optional[str] = None
    cached: bool = False
    error: Optional[str] = None


# ==========================================
# Schemas de Log
# ==========================================

class LogEntry(BaseModel):
    """Entrada de log"""
    time: str
    status: str
    message: str
