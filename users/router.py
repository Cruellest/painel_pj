# users/router.py
"""
Endpoints de gestão de usuários (somente admin)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database.connection import get_db
from auth.models import User
from auth.schemas import UserCreate, UserUpdate, UserResponse
from auth.security import get_password_hash
from auth.dependencies import require_admin
from config import DEFAULT_USER_PASSWORD

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
    user_data: UserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Cria um novo usuário.
    
    **Acesso:** Apenas administradores
    
    - Se **password** não for informada, usa a senha padrão "senha"
    - O usuário será forçado a trocar a senha no primeiro acesso
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
        must_change_password=True,  # Força troca no primeiro acesso
        is_active=True
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
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
    
    # Atualiza campos informados
    update_data = user_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    
    return user


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Desativa um usuário (soft delete).
    
    **Acesso:** Apenas administradores
    
    Nota: O usuário não é removido do banco, apenas desativado.
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
    
    return {"message": f"Usuário '{user.username}' desativado com sucesso"}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Reseta a senha de um usuário para a senha padrão.
    
    **Acesso:** Apenas administradores
    
    - A senha será resetada para "senha"
    - O usuário será forçado a trocar no próximo acesso
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
    
    return {
        "message": f"Senha do usuário '{user.username}' resetada com sucesso",
        "new_password": DEFAULT_USER_PASSWORD
    }
