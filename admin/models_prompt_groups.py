# admin/models_prompt_groups.py
"""
Modelos de grupos e subgrupos para prompts modulares.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, Table
from sqlalchemy.orm import relationship

from database.connection import Base
from utils.timezone import get_utc_now


user_prompt_groups = Table(
    "user_prompt_groups",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("group_id", Integer, ForeignKey("prompt_groups.id"), primary_key=True),
)


class PromptGroup(Base):
    __tablename__ = "prompt_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(50), nullable=False, unique=True, index=True)
    active = Column(Boolean, default=True, index=True)
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    subgroups = relationship("PromptSubgroup", back_populates="group", order_by="PromptSubgroup.order")
    users = relationship("User", secondary=user_prompt_groups, back_populates="allowed_groups")

    def __repr__(self):
        return f"<PromptGroup(id={self.id}, slug='{self.slug}')>"


class PromptSubgroup(Base):
    __tablename__ = "prompt_subgroups"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("prompt_groups.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(50), nullable=False)
    active = Column(Boolean, default=True, index=True)
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    group = relationship("PromptGroup", back_populates="subgroups")

    __table_args__ = (
        UniqueConstraint("group_id", "slug", name="uq_prompt_subgroup_group_slug"),
    )

    def __repr__(self):
        return f"<PromptSubgroup(id={self.id}, slug='{self.slug}', group_id={self.group_id})>"


class PromptSubcategoria(Base):
    """Subcategorias para filtrar módulos de prompt na geração de peças"""
    __tablename__ = "prompt_subcategorias"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("prompt_groups.id"), nullable=False, index=True)
    nome = Column(String(100), nullable=False)  # Nome de exibição
    slug = Column(String(50), nullable=False)   # Identificador único (usado no campo subcategoria do PromptModulo)
    descricao = Column(String(255), nullable=True)
    active = Column(Boolean, default=True, index=True)
    order = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    group = relationship("PromptGroup")

    __table_args__ = (
        UniqueConstraint("group_id", "slug", name="uq_prompt_subcategoria_group_slug"),
    )

    def __repr__(self):
        return f"<PromptSubcategoria(id={self.id}, slug='{self.slug}', group_id={self.group_id})>"


class CategoriaOrdem(Base):
    """
    Define a ordem de exibição das categorias de módulos de conteúdo no prompt.
    Usado para ordenar as seções (Preliminar, Mérito, Eventualidade, etc.) na peça gerada.
    """
    __tablename__ = "categoria_ordem"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("prompt_groups.id"), nullable=False, index=True)
    nome = Column(String(100), nullable=False)  # Nome da categoria (ex: "Preliminar", "Mérito")
    ordem = Column(Integer, default=0)  # Ordem de exibição (menor = primeiro)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    group = relationship("PromptGroup")

    __table_args__ = (
        UniqueConstraint("group_id", "nome", name="uq_categoria_ordem_group_nome"),
    )

    def __repr__(self):
        return f"<CategoriaOrdem(id={self.id}, nome='{self.nome}', ordem={self.ordem}, group_id={self.group_id})>"
