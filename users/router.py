# users/router.py
"""
Endpoints de gestão de usuários (somente admin)

SECURITY: Todas as ações de usuários são registradas no audit log.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List

from database.connection import get_db
from auth.models import User
from auth.schemas import UserCreate, UserUpdate, UserResponse
from auth.security import get_password_hash
from auth.dependencies import require_admin
from config import DEFAULT_USER_PASSWORD
from admin.models_prompt_groups import PromptGroup

# SECURITY: Audit Logging
from utils.audit import (
    log_user_created, log_user_deleted, log_admin_action, log_audit_event, AuditEvent
)

router = APIRouter(prefix="/users", tags=["Usuários"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista todos os usuários do sistema.
    
    **Acesso:** Apenas administradores
    """
    users = db.query(User).offset(skip).limit(limit).all()
    return users


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    user_data: UserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Cria um novo usuário.

    **Acesso:** Apenas administradores

    - Se **password** não for informada, usa a senha padrão "senha"
    - O usuário será forçado a trocar a senha no primeiro acesso

    SECURITY: Ação registrada no audit log.
    """
    # Verifica se username já existe
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Usuário '{user_data.username}' já existe"
        )
    
    # Verifica se email já existe (se informado)
    if user_data.email:
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{user_data.email}' já cadastrado"
            )
    
    # Resolve grupo padrão e grupos permitidos
    default_group = None
    if user_data.default_group_id:
        default_group = db.query(PromptGroup).filter(PromptGroup.id == user_data.default_group_id).first()
        if not default_group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Grupo padrao invalido"
            )
    else:
        default_group = db.query(PromptGroup).filter(PromptGroup.slug == "ps").first()

    allowed_ids = user_data.allowed_group_ids or []
    if not allowed_ids and default_group:
        allowed_ids = [default_group.id]
    if default_group and default_group.id not in allowed_ids:
        allowed_ids.append(default_group.id)

    allowed_groups = []
    if allowed_ids:
        allowed_groups = db.query(PromptGroup).filter(PromptGroup.id.in_(allowed_ids)).all()
        if len(allowed_groups) != len(set(allowed_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lista de grupos permitidos contem IDs invalidos"
            )

    # Define senha (padrão ou informada)
    password = user_data.password if user_data.password else DEFAULT_USER_PASSWORD
    
    # Cria usuário
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(password),
        role=user_data.role,
        sistemas_permitidos=user_data.sistemas_permitidos,
        permissoes_especiais=user_data.permissoes_especiais,
        default_group_id=default_group.id if default_group else None,
        allowed_groups=allowed_groups,
        must_change_password=True,  # Força troca no primeiro acesso
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # SECURITY: Audit log de criação de usuário
    log_user_created(new_user.id, new_user.username, admin.username, request)

    return new_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retorna detalhes de um usuário específico.
    
    **Acesso:** Apenas administradores
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    request: Request,
    user_id: int,
    user_data: UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Atualiza dados de um usuário.

    **Acesso:** Apenas administradores

    Campos que podem ser atualizados:
    - email
    - full_name
    - role
    - is_active

    SECURITY: Ação registrada no audit log.
    """
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    # Impede desativar o próprio usuário admin
    if user.id == admin.id and user_data.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode desativar sua própria conta"
        )
    
    # Impede remover role admin do próprio usuário
    if user.id == admin.id and user_data.role == "user":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode remover seu próprio acesso de administrador"
        )
    
    # Verifica email duplicado
    if user_data.email and user_data.email != user.email:
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email '{user_data.email}' já cadastrado"
            )
    
    # Atualiza grupos permitidos e grupo padrão quando informado
    allowed_ids_provided = user_data.allowed_group_ids is not None
    default_group_provided = user_data.default_group_id is not None

    if allowed_ids_provided:
        allowed_ids = user_data.allowed_group_ids
        allowed_groups = []
        if allowed_ids:
            allowed_groups = db.query(PromptGroup).filter(PromptGroup.id.in_(allowed_ids)).all()
            if len(allowed_groups) != len(set(allowed_ids)):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Lista de grupos permitidos contem IDs invalidos"
                )
        user.allowed_groups = allowed_groups

    if default_group_provided:
        default_group = db.query(PromptGroup).filter(PromptGroup.id == user_data.default_group_id).first()
        if not default_group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Grupo padrao invalido"
            )
        if allowed_ids_provided and user_data.allowed_group_ids:
            if default_group.id not in user_data.allowed_group_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Grupo padrao deve estar nos grupos permitidos"
                )
        user.default_group_id = default_group.id
        if not allowed_ids_provided and default_group not in user.allowed_groups:
            user.allowed_groups.append(default_group)

    # Se mudou os grupos permitidos sem definir grupo padrão, ajusta para o primeiro permitido
    if allowed_ids_provided and user.allowed_groups and not default_group_provided:
        if not user.default_group_id or not any(g.id == user.default_group_id for g in user.allowed_groups):
            user.default_group_id = user.allowed_groups[0].id

    # Atualiza campos informados
    update_data = user_data.model_dump(exclude_unset=True, exclude={"allowed_group_ids", "default_group_id"})
    for field, value in update_data.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)

    # SECURITY: Audit log de atualização de usuário
    log_audit_event(
        AuditEvent.USER_UPDATED,
        user_id=user.id,
        username=user.username,
        request=request,
        details={"updated_by": admin.username, "fields_updated": list(update_data.keys())}
    )

    return user


@router.delete("/{user_id}")
async def delete_user(
    request: Request,
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Desativa um usuário (soft delete).

    **Acesso:** Apenas administradores

    Nota: O usuário não é removido do banco, apenas desativado.

    SECURITY: Ação registrada no audit log.
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )

    # Impede deletar o próprio usuário
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não pode desativar sua própria conta"
        )

    user.is_active = False
    db.commit()

    # SECURITY: Audit log de desativação de usuário
    log_user_deleted(user.id, user.username, admin.username, request)

    return {"message": f"Usuário '{user.username}' desativado com sucesso"}


@router.post("/{user_id}/reset-password")
async def reset_password(
    request: Request,
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reseta a senha de um usuário para a senha padrão.

    **Acesso:** Apenas administradores

    - A senha será resetada para "senha"
    - O usuário será forçado a trocar no próximo acesso

    SECURITY: Ação registrada no audit log.
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )

    user.hashed_password = get_password_hash(DEFAULT_USER_PASSWORD)
    user.must_change_password = True
    db.commit()

    # SECURITY: Audit log de reset de senha
    log_audit_event(
        AuditEvent.USER_PASSWORD_RESET,
        user_id=user.id,
        username=user.username,
        request=request,
        details={"reset_by": admin.username}
    )

    return {
        "message": f"Senha do usuário '{user.username}' resetada com sucesso",
        "new_password": DEFAULT_USER_PASSWORD
    }
