# auth/dependencies.py
"""
Dependencies de autenticação para injeção nas rotas

SECURITY: Implementa autenticação híbrida que aceita token de:
1. Cookie HttpOnly (preferencial - mais seguro contra XSS)
2. Header Authorization Bearer (para APIs/clients externos)
3. Query string (para casos especiais como download de arquivos)
"""

from fastapi import Depends, HTTPException, status, Query, Request, Cookie
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional

from database.connection import get_db
from auth.models import User
from auth.security import decode_token
from auth.schemas import TokenData

# SECURITY: Token blacklist para revogação
from utils.token_blacklist import is_token_revoked

# OAuth2 scheme - define o endpoint de login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# SECURITY: Nome do cookie de autenticação (deve corresponder ao definido em router.py)
AUTH_COOKIE_NAME = "access_token"


def extract_token_from_sources(
    authorization_header: Optional[str] = None,
    cookie_token: Optional[str] = None,
    query_token: Optional[str] = None
) -> Optional[str]:
    """
    SECURITY: Extrai token de múltiplas fontes em ordem de prioridade.

    Prioridade:
    1. Cookie HttpOnly (mais seguro)
    2. Header Authorization
    3. Query string (menos seguro, usar apenas quando necessário)

    Returns:
        Token JWT limpo (sem prefixo "Bearer ") ou None
    """
    # 1. Tenta cookie primeiro (mais seguro contra XSS)
    if cookie_token:
        # Cookie pode ter prefixo "Bearer " ou não
        if cookie_token.startswith("Bearer "):
            return cookie_token[7:]
        return cookie_token

    # 2. Tenta header Authorization
    if authorization_header:
        if authorization_header.startswith("Bearer "):
            return authorization_header[7:]
        return authorization_header

    # 3. Tenta query string (menos seguro)
    if query_token:
        if query_token.startswith("Bearer "):
            return query_token[7:]
        return query_token

    return None


async def get_current_user(
    request: Request,
    token_header: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    SECURITY: Dependency que retorna o usuário atual baseado no token JWT.

    Aceita token de:
    1. Cookie HttpOnly "access_token" (preferencial)
    2. Header Authorization Bearer
    3. Query string "token" (para downloads)

    Lança HTTPException 401 se token inválido ou ausente.

    Uso:
        @router.get("/rota-protegida")
        def rota(user: User = Depends(get_current_user)):
            ...
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # SECURITY: Extrai token de múltiplas fontes
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)
    query_token = request.query_params.get("token")

    token = extract_token_from_sources(
        authorization_header=token_header,
        cookie_token=cookie_token,
        query_token=query_token
    )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # SECURITY: Verifica se o token foi revogado (logout)
    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revogado. Faça login novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decodifica o token
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    username: str = payload.get("sub")
    user_id: int = payload.get("user_id")

    if username is None:
        raise credentials_exception

    # Busca usuário no banco
    user = db.query(User).filter(User.username == username).first()

    if user is None:
        raise credentials_exception

    return user


async def get_current_user_from_token_or_query(
    request: Request,
    token_header: Optional[str] = Depends(oauth2_scheme_optional),
    token_query: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db)
) -> User:
    """
    SECURITY: Dependency que aceita token de múltiplas fontes.

    Prioridade:
    1. Cookie HttpOnly (mais seguro)
    2. Header Authorization
    3. Query string (para downloads/iframes)
    """
    # SECURITY: Extrai token de múltiplas fontes
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)

    token = extract_token_from_sources(
        authorization_header=token_header,
        cookie_token=cookie_token,
        query_token=token_query
    )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # SECURITY: Verifica se o token foi revogado (logout)
    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revogado. Faça login novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário desativado"
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency que retorna o usuário atual apenas se estiver ativo.
    Lança HTTPException 403 se usuário desativado.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário desativado"
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency que exige que o usuário seja administrador.
    Lança HTTPException 403 se não for admin.
    
    Uso:
        @router.get("/rota-admin")
        def rota(admin: User = Depends(require_admin)):
            ...
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores"
        )
    return current_user


async def get_optional_user(
    request: Request,
    token_header: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    SECURITY: Dependency que retorna o usuário se autenticado, ou None se não.
    Útil para rotas que funcionam diferente para usuários logados.

    Aceita token de cookie HttpOnly ou header Authorization.
    """
    # SECURITY: Extrai token de múltiplas fontes
    cookie_token = request.cookies.get(AUTH_COOKIE_NAME)

    token = extract_token_from_sources(
        authorization_header=token_header,
        cookie_token=cookie_token
    )

    if not token:
        return None

    # SECURITY: Verifica se o token foi revogado
    if is_token_revoked(token):
        return None

    payload = decode_token(token)
    if payload is None:
        return None

    username: str = payload.get("sub")
    if username is None:
        return None

    user = db.query(User).filter(User.username == username).first()
    return user
