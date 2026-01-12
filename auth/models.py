# auth/models.py
"""
Modelo de usuário para autenticação
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from database.connection import Base
from admin.models_prompt_groups import user_prompt_groups


class User(Base):
    """Modelo de usuário do sistema"""
    
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=True)
    full_name = Column(String(200), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # 'admin' ou 'user'
    
    # Sistemas que o usuário pode acessar (lista de strings)
    # Ex: ["matriculas", "assistencia_judiciaria", "gerador_pecas", "pedido_calculo"]
    # Se vazio ou None, usuário tem acesso a todos (compatibilidade)
    sistemas_permitidos = Column(JSON, nullable=True, default=None)
    
    # Permissões especiais (lista de strings)
    # Ex: ["editar_prompts", "criar_prompts", "ver_historico_prompts"]
    permissoes_especiais = Column(JSON, nullable=True, default=None)

    # Grupo padrão e grupos permitidos para prompts modulares
    default_group_id = Column(Integer, ForeignKey("prompt_groups.id"), nullable=True)
    default_group = relationship("PromptGroup", foreign_keys=[default_group_id])
    allowed_groups = relationship("PromptGroup", secondary=user_prompt_groups, back_populates="users")
    
    must_change_password = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def pode_acessar_sistema(self, sistema: str) -> bool:
        """Verifica se o usuário pode acessar um sistema específico"""
        # Admin tem acesso a tudo
        if self.role == "admin":
            return True
        # Se não tem sistemas definidos, tem acesso a todos (compatibilidade)
        if not self.sistemas_permitidos:
            return True
        return sistema in self.sistemas_permitidos
    
    def tem_permissao(self, permissao: str) -> bool:
        """Verifica se o usuário tem uma permissão especial"""
        # Admin tem todas as permissões
        if self.role == "admin":
            return True
        if not self.permissoes_especiais:
            return False
        return permissao in self.permissoes_especiais

    def tem_acesso_grupo(self, group_id: int) -> bool:
        """Verifica se o usuário tem acesso ao grupo de prompts."""
        if self.role == "admin":
            return True
        if not group_id:
            return False
        if self.allowed_groups:
            return any(g.id == group_id for g in self.allowed_groups)
        return self.default_group_id == group_id

    @property
    def allowed_group_ids(self):
        if not self.allowed_groups:
            return []
        return [g.id for g in self.allowed_groups]

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"
