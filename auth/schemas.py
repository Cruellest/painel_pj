# auth/schemas.py
"""
Schemas Pydantic para autenticação
"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# ==========================================
# Schemas de Token
# ==========================================

class Token(BaseModel):
    """Token JWT retornado no login"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Dados extraídos do token JWT"""
    username: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[str] = None


# ==========================================
# Schemas de Login
# ==========================================

class LoginRequest(BaseModel):
    """Request de login"""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=1)


class ChangePasswordRequest(BaseModel):
    """Request de troca de senha"""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=4, max_length=100)


# ==========================================
# Schemas de Usuário
# ==========================================

class UserBase(BaseModel):
    """Base para schemas de usuário"""
    username: str = Field(..., min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    full_name: str = Field(..., min_length=2, max_length=200)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserCreate(UserBase):
    """Schema para criação de usuário"""
    password: Optional[str] = None  # Se None, usa senha padrão
    sistemas_permitidos: Optional[List[str]] = None  # Lista de sistemas
    permissoes_especiais: Optional[List[str]] = None  # Lista de permissões


class UserUpdate(BaseModel):
    """Schema para atualização de usuário"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=2, max_length=200)
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    is_active: Optional[bool] = None
    sistemas_permitidos: Optional[List[str]] = None
    permissoes_especiais: Optional[List[str]] = None


class UserResponse(UserBase):
    """Schema de resposta com dados do usuário"""
    id: int
    is_active: bool
    must_change_password: bool
    sistemas_permitidos: Optional[List[str]] = None
    permissoes_especiais: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserMe(BaseModel):
    """Schema para /auth/me - dados do usuário logado"""
    id: int
    username: str
    email: Optional[str]
    full_name: str
    role: str
    must_change_password: bool
    sistemas_permitidos: Optional[List[str]] = None
    permissoes_especiais: Optional[List[str]] = None

    class Config:
        from_attributes = True
