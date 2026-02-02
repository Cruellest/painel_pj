# sistemas/cumprimento_beta/dependencies.py
"""
Dependencies para injeção de dependências do módulo Cumprimento de Sentença Beta.

Inclui verificação de acesso baseada em:
- Admin: sempre tem acesso
- Usuário comum: grupo padrão deve ser "PS"
"""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from database.connection import get_db
from auth.dependencies import get_current_active_user
from auth.models import User
from sistemas.cumprimento_beta.constants import GRUPO_ACESSO_BETA
from sistemas.cumprimento_beta.exceptions import AcessoNegadoError


def verificar_acesso_beta(current_user: User, db: Session) -> bool:
    """
    Verifica se o usuário tem acesso ao módulo beta.

    Regras:
    - Admin: sempre tem acesso
    - Usuário comum: grupo padrão deve ser "PS"

    Args:
        current_user: Usuário autenticado
        db: Sessão do banco de dados

    Returns:
        True se tem acesso, False caso contrário
    """
    # Admin sempre tem acesso
    if current_user.role == "admin":
        return True

    # Verifica grupo padrão
    if current_user.default_group:
        # Verifica pelo slug do grupo
        if current_user.default_group.slug == GRUPO_ACESSO_BETA:
            return True
        # Fallback: verifica pelo nome (case insensitive)
        if current_user.default_group.name.upper() == GRUPO_ACESSO_BETA:
            return True

    return False


async def require_beta_access(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency que exige acesso ao beta.

    Uso:
        @router.get("/rota")
        async def rota(user: User = Depends(require_beta_access)):
            ...

    Raises:
        HTTPException 403: Se usuário não tem acesso

    Returns:
        User: Usuário autenticado com acesso confirmado
    """
    if not verificar_acesso_beta(current_user, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Módulo disponível apenas para usuários do grupo PS ou administradores."
        )

    return current_user


async def get_user_pode_acessar_beta(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> dict:
    """
    Dependency que retorna se o usuário pode acessar o beta.

    Útil para endpoints que precisam verificar acesso sem bloquear.

    Returns:
        dict com {pode_acessar: bool, motivo: str}
    """
    pode = verificar_acesso_beta(current_user, db)

    if pode:
        return {
            "pode_acessar": True,
            "motivo": "Acesso permitido"
        }

    # Monta motivo
    if current_user.default_group:
        motivo = f"Grupo padrão '{current_user.default_group.name}' não tem acesso. Requer grupo '{GRUPO_ACESSO_BETA}'."
    else:
        motivo = f"Usuário sem grupo padrão definido. Requer grupo '{GRUPO_ACESSO_BETA}'."

    return {
        "pode_acessar": False,
        "motivo": motivo
    }
