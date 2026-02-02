# auth/schemas.py
"""
Schemas Pydantic para autenticação

SECURITY: Inclui validação de política de senhas fortes.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime

from utils.password_policy import validate_password, MIN_PASSWORD_LENGTH


# ==========================================
# Schemas de Token
# ==========================================

class Token(BaseModel):
    """Token JWT retornado no login."""
    access_token: str = Field(
        ...,
        description="Token JWT para autenticação",
        json_schema_extra={"example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}
    )
    token_type: str = Field(
        default="bearer",
        description="Tipo do token (sempre 'bearer')"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMSIsImV4cCI6MTcwMDAwMDAwMH0.xxx",
                "token_type": "bearer"
            }
        }
    }


class TokenData(BaseModel):
    """Dados extraídos do token JWT"""
    username: Optional[str] = None
    user_id: Optional[int] = None
    role: Optional[str] = None


# ==========================================
# Schemas de Login
# ==========================================

class HTTPError(BaseModel):
    """Schema padrão de erro HTTP."""
    detail: str = Field(..., description="Mensagem de erro detalhada")

    model_config = {
        "json_schema_extra": {
            "example": {"detail": "Usuário ou senha incorretos"}
        }
    }


class LoginRequest(BaseModel):
    """Request de login."""
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Nome de usuário",
        json_schema_extra={"example": "joao.silva"}
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Senha do usuário",
        json_schema_extra={"example": "MinhaSenh@123"}
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "username": "joao.silva",
                "password": "MinhaSenh@123"
            }
        }
    }


class ChangePasswordRequest(BaseModel):
    """
    Request de troca de senha.

    SECURITY: A nova senha é validada contra política de senhas fortes.
    """
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, max_length=128)

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v):
        """SECURITY: Valida força da nova senha"""
        return validate_password(v)


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
    """
    Schema para criação de usuário.

    SECURITY: Se uma senha for fornecida, ela é validada contra política de senhas fortes.
    Se não for fornecida, usa senha padrão que o usuário será forçado a trocar.
    """
    password: Optional[str] = None  # Se None, usa senha padrão
    sistemas_permitidos: Optional[List[str]] = None  # Lista de sistemas
    permissoes_especiais: Optional[List[str]] = None  # Lista de permissões
    setor: Optional[str] = Field(None, max_length=120)  # Setor/departamento
    default_group_id: Optional[int] = None
    allowed_group_ids: Optional[List[int]] = None

    @field_validator('password')
    @classmethod
    def validate_user_password(cls, v):
        """SECURITY: Valida força da senha se fornecida"""
        if v is not None:
            return validate_password(v)
        return v


class UserUpdate(BaseModel):
    """Schema para atualização de usuário"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=2, max_length=200)
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    is_active: Optional[bool] = None
    sistemas_permitidos: Optional[List[str]] = None
    permissoes_especiais: Optional[List[str]] = None
    setor: Optional[str] = Field(None, max_length=120)
    default_group_id: Optional[int] = None
    allowed_group_ids: Optional[List[int]] = None


class UserResponse(UserBase):
    """Schema de resposta com dados do usuário"""
    id: int
    is_active: bool
    must_change_password: bool
    sistemas_permitidos: Optional[List[str]] = None
    permissoes_especiais: Optional[List[str]] = None
    setor: Optional[str] = None
    default_group_id: Optional[int] = None
    allowed_group_ids: Optional[List[int]] = None
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
    setor: Optional[str] = None
    default_group_id: Optional[int] = None
    allowed_group_ids: Optional[List[int]] = None

    class Config:
        from_attributes = True
