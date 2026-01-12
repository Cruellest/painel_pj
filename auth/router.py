# auth/router.py
"""
Endpoints de autenticação: login, logout, troca de senha
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database.connection import get_db
from auth.models import User
from auth.schemas import (
    Token, LoginRequest, ChangePasswordRequest, UserMe
)
from auth.security import verify_password, get_password_hash, create_access_token
from auth.dependencies import get_current_active_user
from config import ACCESS_TOKEN_EXPIRE_MINUTES

# SECURITY: Rate Limiting
from utils.rate_limit import limiter, LIMITS

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/login", response_model=Token)
@limiter.limit(LIMITS["login"])  # SECURITY: 5 tentativas/minuto por IP
async def login(
    request: Request,  # Necessário para rate limiting
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Autentica o usuário e retorna um token JWT.
    
    - **username**: Nome de usuário
    - **password**: Senha
    
    Retorna um token JWT válido por 8 horas.
    """
    # Busca usuário
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verifica senha
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verifica se usuário está ativo
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário desativado. Contate o administrador."
        )
    
    # Cria token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "role": user.role,
            "must_change_password": user.must_change_password
        },
        expires_delta=access_token_expires
    )
    
    return Token(access_token=access_token, token_type="bearer")


@router.get("/me", response_model=UserMe)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """
    Retorna os dados do usuário autenticado.
    """
    return current_user


@router.post("/change-password")
@limiter.limit(LIMITS["login"])  # SECURITY: 5 tentativas/minuto por IP
async def change_password(
    request: Request,  # Necessário para rate limiting
    password_request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Altera a senha do usuário autenticado.
    
    - **current_password**: Senha atual
    - **new_password**: Nova senha (mínimo 4 caracteres)
    """
    # Verifica senha atual
    if not verify_password(password_request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha atual incorreta"
        )

    # Verifica se nova senha é diferente da atual
    if password_request.current_password == password_request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nova senha deve ser diferente da atual"
        )

    # Atualiza senha
    current_user.hashed_password = get_password_hash(password_request.new_password)
    current_user.must_change_password = False
    db.commit()
    
    return {"message": "Senha alterada com sucesso"}


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_active_user)):
    """
    Logout do usuário.
    
    Nota: Como JWT é stateless, o logout real acontece no frontend
    removendo o token do storage. Este endpoint existe para 
    compatibilidade e logging.
    """
    return {"message": "Logout realizado com sucesso"}
