# auth/router.py
"""
Endpoints de autenticação: login, logout, troca de senha

SECURITY: Implementa autenticação via HttpOnly cookies para prevenir XSS.
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from database.connection import get_db
from auth.models import User
from auth.schemas import (
    Token, LoginRequest, ChangePasswordRequest, UserMe
)
from auth.security import verify_password, get_password_hash, create_access_token
from auth.dependencies import get_current_active_user
from config import ACCESS_TOKEN_EXPIRE_MINUTES, IS_PRODUCTION

# SECURITY: Rate Limiting
from utils.rate_limit import limiter, LIMITS

# SECURITY: Audit Logging
from utils.audit import (
    log_login_success, log_login_failure, log_logout, log_password_change
)

# SECURITY: Política de senhas
from utils.password_policy import get_password_requirements

# SECURITY: Token blacklist para revogação
from utils.token_blacklist import revoke_token

router = APIRouter(prefix="/auth", tags=["Autenticação"])

# SECURITY: Nome do cookie de autenticação
AUTH_COOKIE_NAME = "access_token"


@router.post("/login", response_model=Token)
@limiter.limit(LIMITS["login"])  # SECURITY: 5 tentativas/minuto por IP
async def login(
    request: Request,  # Necessário para rate limiting
    response: Response,  # SECURITY: Para definir cookie HttpOnly
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Autentica o usuário e retorna um token JWT.

    - **username**: Nome de usuário
    - **password**: Senha

    SECURITY: O token é retornado no body E também definido como HttpOnly cookie.
    O cookie previne roubo de token via XSS.
    """
    # Busca usuário
    user = db.query(User).filter(User.username == form_data.username).first()

    if not user:
        # SECURITY: Audit log de falha de login
        log_login_failure(form_data.username, request, "user_not_found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verifica senha
    if not verify_password(form_data.password, user.hashed_password):
        # SECURITY: Audit log de falha de login
        log_login_failure(form_data.username, request, "invalid_password")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verifica se usuário está ativo
    if not user.is_active:
        # SECURITY: Audit log de falha de login
        log_login_failure(form_data.username, request, "user_inactive")
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

    # SECURITY: Define cookie HttpOnly para prevenir XSS
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=f"Bearer {access_token}",
        httponly=True,                        # JavaScript não pode acessar
        secure=IS_PRODUCTION,                 # HTTPS only em produção
        samesite="lax",                        # Proteção CSRF
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Expiração em segundos
        path="/"                               # Disponível em toda aplicação
    )

    # SECURITY: Audit log de login bem sucedido
    log_login_success(user.id, user.username, request)

    # SECURITY: Também retorna no body para compatibilidade com clientes que precisam
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

    # SECURITY: Audit log de alteração de senha
    log_password_change(current_user.id, current_user.username, request)

    return {"message": "Senha alterada com sucesso"}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_active_user)
):
    """
    Logout do usuário.

    SECURITY: Revoga o token JWT e remove o cookie HttpOnly de autenticação.
    O frontend também deve limpar qualquer token armazenado localmente.
    """
    # SECURITY: Extrai o token para revogação
    token = None
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie_token:
        token = cookie_token[7:] if cookie_token.startswith("Bearer ") else cookie_token
    else:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    # SECURITY: Revoga o token (adiciona à blacklist)
    if token:
        revoke_token(token)

    # SECURITY: Audit log de logout
    log_logout(current_user.id, current_user.username, request)

    # SECURITY: Remove o cookie de autenticação
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax",
        path="/"
    )

    return {"message": "Logout realizado com sucesso"}


@router.get("/password-requirements")
async def password_requirements():
    """
    Retorna os requisitos de senha do sistema.

    Útil para o frontend exibir as regras de senha ao usuário.
    Não requer autenticação.
    """
    return get_password_requirements()
