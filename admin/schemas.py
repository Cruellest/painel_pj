# admin/schemas.py
"""
Schemas Pydantic para API de administração
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ============================================
# Prompts
# ============================================

class PromptBase(BaseModel):
    sistema: str
    tipo: str
    nome: str
    descricao: Optional[str] = None
    conteudo: str


class PromptCreate(PromptBase):
    pass


class PromptUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    conteudo: Optional[str] = None
    is_active: Optional[bool] = None


class PromptResponse(PromptBase):
    id: int
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


class PromptListResponse(BaseModel):
    prompts: List[PromptResponse]
    total: int


# ============================================
# Configurações de IA
# ============================================

class ConfiguracaoIABase(BaseModel):
    sistema: str
    chave: str
    valor: str
    tipo_valor: str = "string"
    descricao: Optional[str] = None


class ConfiguracaoIACreate(ConfiguracaoIABase):
    pass


class ConfiguracaoIAUpdate(BaseModel):
    valor: Optional[str] = None
    descricao: Optional[str] = None


class ConfiguracaoIAResponse(ConfiguracaoIABase):
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
