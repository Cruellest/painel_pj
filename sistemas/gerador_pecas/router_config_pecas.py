# sistemas/gerador_pecas/router_config_pecas.py
"""
Router para configuração de tipos de peças e categorias de documentos.

Endpoints para:
- CRUD de categorias de documento
- CRUD de tipos de peça
- Associação de categorias a tipos de peça
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from database.connection import get_db
from auth.dependencies import get_current_user
from auth.models import User
from sistemas.gerador_pecas.models_config_pecas import (
    CategoriaDocumento,
    TipoPeca,
    tipo_peca_categorias,
    get_categorias_documento_seed,
    get_tipos_peca_seed,
    carregar_categorias_json,
    get_codigos_por_categoria_json
)

router = APIRouter(prefix="/api/gerador-pecas/config", tags=["Config Peças"])
templates = Jinja2Templates(directory="frontend/templates")


# ===========================================
# Schemas Pydantic
# ===========================================

class CategoriaDocumentoBase(BaseModel):
    nome: str
    titulo: str
    descricao: Optional[str] = None
    codigos_documento: List[int] = []
    ativo: bool = True
    ordem: int = 0
    cor: Optional[str] = None


class CategoriaDocumentoResponse(CategoriaDocumentoBase):
    id: int
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class TipoPecaBase(BaseModel):
    nome: str
    titulo: str
    descricao: Optional[str] = None
    icone: Optional[str] = None
    ativo: bool = True
    ordem: int = 0
    is_padrao: bool = False
    configuracoes: Optional[dict] = None


class TipoPecaCreate(TipoPecaBase):
    categorias_ids: List[int] = []


class TipoPecaResponse(TipoPecaBase):
    id: int
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None
    categorias_documento: List[CategoriaDocumentoResponse] = []
    
    class Config:
        from_attributes = True


class AssociacaoCategoriasRequest(BaseModel):
    categorias_ids: List[int]


# ===========================================
# Endpoints - Categorias de Documento
# ===========================================

@router.get("/categorias-json")
async def listar_categorias_json(
    current_user: User = Depends(get_current_user)
):
    """
    Lista todas as categorias e documentos do arquivo categorias_documentos.json.
    Útil para o frontend mostrar os documentos individuais por categoria.
    """
    categorias = carregar_categorias_json()
    
    # Formatar para o frontend
    resultado = []
    for cat_nome, documentos in categorias.items():
        resultado.append({
            "categoria": cat_nome,
            "nome_id": cat_nome.lower().replace(" ", "_").replace("ã", "a").replace("ç", "c").replace("é", "e").replace("ó", "o"),
            "documentos": documentos,
            "codigos": [d["codigo"] for d in documentos]
        })
    
    # Ordenar por nome da categoria
    resultado.sort(key=lambda x: x["categoria"])
    
    return resultado


@router.get("/categorias", response_model=List[CategoriaDocumentoResponse])
async def listar_categorias(
    ativo: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lista todas as categorias de documento"""
    query = db.query(CategoriaDocumento)
    
    if ativo is not None:
        query = query.filter(CategoriaDocumento.ativo == ativo)
    
    return query.order_by(CategoriaDocumento.ordem, CategoriaDocumento.titulo).all()


@router.get("/categorias/{categoria_id}", response_model=CategoriaDocumentoResponse)
async def obter_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtém uma categoria específica"""
    categoria = db.query(CategoriaDocumento).filter(CategoriaDocumento.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    return categoria


@router.post("/categorias", response_model=CategoriaDocumentoResponse)
async def criar_categoria(
    dados: CategoriaDocumentoBase,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cria uma nova categoria de documento"""
    if not current_user.role == "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Verifica se já existe categoria com esse nome
    existente = db.query(CategoriaDocumento).filter(
        func.lower(CategoriaDocumento.nome) == dados.nome.lower()
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Já existe categoria com esse nome")
    
    categoria = CategoriaDocumento(**dados.dict())
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    
    return categoria


@router.put("/categorias/{categoria_id}", response_model=CategoriaDocumentoResponse)
async def atualizar_categoria(
    categoria_id: int,
    dados: CategoriaDocumentoBase,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Atualiza uma categoria de documento"""
    if not current_user.role == "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    categoria = db.query(CategoriaDocumento).filter(CategoriaDocumento.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    
    # Verifica se nome já existe em outra categoria
    if dados.nome.lower() != categoria.nome.lower():
        existente = db.query(CategoriaDocumento).filter(
            func.lower(CategoriaDocumento.nome) == dados.nome.lower(),
            CategoriaDocumento.id != categoria_id
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="Já existe categoria com esse nome")
    
    for key, value in dados.dict().items():
        setattr(categoria, key, value)
    
    db.commit()
    db.refresh(categoria)
    
    return categoria


@router.delete("/categorias/{categoria_id}")
async def excluir_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Exclui uma categoria de documento"""
    if not current_user.role == "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    categoria = db.query(CategoriaDocumento).filter(CategoriaDocumento.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    
    db.delete(categoria)
    db.commit()
    
    return {"message": "Categoria excluída com sucesso"}


# ===========================================
# Endpoints - Tipos de Peça
# ===========================================

@router.get("/tipos-peca-prompts")
async def listar_tipos_peca_prompts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lista os tipos de peça baseados nos prompts modulares (fonte de verdade).
    Usado para sincronizar o TipoPeca local com os prompts cadastrados.
    """
    from admin.models_prompts import PromptModulo
    
    modulos_peca = db.query(PromptModulo).filter(
        PromptModulo.tipo == "peca",
        PromptModulo.ativo == True
    ).order_by(PromptModulo.ordem).all()
    
    return [
        {
            "prompt_id": m.id,
            "nome": m.categoria or m.nome,  # categoria é o identificador (contestacao, recurso_apelacao)
            "titulo": m.titulo,
            "ativo": m.ativo,
            "ordem": m.ordem
        }
        for m in modulos_peca
    ]


@router.get("/tipos-peca", response_model=List[TipoPecaResponse])
async def listar_tipos_peca(
    ativo: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lista todos os tipos de peça com suas categorias"""
    query = db.query(TipoPeca)
    
    if ativo is not None:
        query = query.filter(TipoPeca.ativo == ativo)
    
    return query.order_by(TipoPeca.ordem, TipoPeca.titulo).all()


@router.get("/tipos-peca/{tipo_id}", response_model=TipoPecaResponse)
async def obter_tipo_peca(
    tipo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtém um tipo de peça específico"""
    tipo = db.query(TipoPeca).filter(TipoPeca.id == tipo_id).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de peça não encontrado")
    return tipo


@router.get("/tipos-peca/nome/{nome}")
async def obter_tipo_peca_por_nome(
    nome: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtém um tipo de peça pelo nome e retorna códigos permitidos"""
    tipo = db.query(TipoPeca).filter(
        func.lower(TipoPeca.nome) == nome.lower(),
        TipoPeca.ativo == True
    ).first()
    
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de peça não encontrado")
    
    return {
        "id": tipo.id,
        "nome": tipo.nome,
        "titulo": tipo.titulo,
        "codigos_permitidos": list(tipo.get_codigos_permitidos()),
        "categorias": [
            {"id": c.id, "nome": c.nome, "titulo": c.titulo}
            for c in tipo.categorias_documento if c.ativo
        ]
    }


@router.post("/tipos-peca", response_model=TipoPecaResponse)
async def criar_tipo_peca(
    dados: TipoPecaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cria um novo tipo de peça"""
    if not current_user.role == "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    # Verifica se já existe tipo com esse nome
    existente = db.query(TipoPeca).filter(
        func.lower(TipoPeca.nome) == dados.nome.lower()
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Já existe tipo de peça com esse nome")
    
    # Cria o tipo de peça
    tipo_data = dados.dict(exclude={'categorias_ids'})
    tipo = TipoPeca(**tipo_data)
    
    # Associa categorias
    if dados.categorias_ids:
        categorias = db.query(CategoriaDocumento).filter(
            CategoriaDocumento.id.in_(dados.categorias_ids)
        ).all()
        tipo.categorias_documento = categorias
    
    db.add(tipo)
    db.commit()
    db.refresh(tipo)
    
    return tipo


@router.put("/tipos-peca/{tipo_id}", response_model=TipoPecaResponse)
async def atualizar_tipo_peca(
    tipo_id: int,
    dados: TipoPecaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Atualiza um tipo de peça"""
    if not current_user.role == "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    tipo = db.query(TipoPeca).filter(TipoPeca.id == tipo_id).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de peça não encontrado")
    
    # Verifica se nome já existe em outro tipo
    if dados.nome.lower() != tipo.nome.lower():
        existente = db.query(TipoPeca).filter(
            func.lower(TipoPeca.nome) == dados.nome.lower(),
            TipoPeca.id != tipo_id
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="Já existe tipo de peça com esse nome")
    
    # Atualiza campos
    tipo_data = dados.dict(exclude={'categorias_ids'})
    for key, value in tipo_data.items():
        setattr(tipo, key, value)
    
    # Atualiza categorias
    if dados.categorias_ids is not None:
        categorias = db.query(CategoriaDocumento).filter(
            CategoriaDocumento.id.in_(dados.categorias_ids)
        ).all()
        tipo.categorias_documento = categorias
    
    db.commit()
    db.refresh(tipo)
    
    return tipo


@router.put("/tipos-peca/{tipo_id}/categorias")
async def atualizar_categorias_tipo_peca(
    tipo_id: int,
    dados: AssociacaoCategoriasRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Atualiza apenas as categorias de um tipo de peça"""
    if not current_user.role == "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    tipo = db.query(TipoPeca).filter(TipoPeca.id == tipo_id).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de peça não encontrado")
    
    categorias = db.query(CategoriaDocumento).filter(
        CategoriaDocumento.id.in_(dados.categorias_ids)
    ).all()
    tipo.categorias_documento = categorias
    
    db.commit()
    
    return {
        "message": "Categorias atualizadas com sucesso",
        "tipo_id": tipo_id,
        "categorias_count": len(categorias)
    }


@router.delete("/tipos-peca/{tipo_id}")
async def excluir_tipo_peca(
    tipo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Exclui um tipo de peça"""
    if not current_user.role == "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    tipo = db.query(TipoPeca).filter(TipoPeca.id == tipo_id).first()
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de peça não encontrado")
    
    db.delete(tipo)
    db.commit()
    
    return {"message": "Tipo de peça excluído com sucesso"}


# ===========================================
# Endpoint para Seed Inicial
# ===========================================

@router.post("/seed")
async def seed_dados_iniciais(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Popula dados iniciais de categorias e tipos de peça"""
    if not current_user.role == "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")
    
    categorias_criadas = 0
    tipos_criados = 0
    
    # Criar categorias
    for cat_data in get_categorias_documento_seed():
        existente = db.query(CategoriaDocumento).filter(
            CategoriaDocumento.nome == cat_data["nome"]
        ).first()
        
        if not existente:
            categoria = CategoriaDocumento(**cat_data)
            db.add(categoria)
            categorias_criadas += 1
    
    db.commit()
    
    # Criar tipos de peça
    for tipo_data in get_tipos_peca_seed():
        existente = db.query(TipoPeca).filter(
            TipoPeca.nome == tipo_data["nome"]
        ).first()
        
        if not existente:
            categorias_nomes = tipo_data.pop("categorias", [])
            tipo = TipoPeca(**tipo_data)
            
            # Associa categorias
            categorias = db.query(CategoriaDocumento).filter(
                CategoriaDocumento.nome.in_(categorias_nomes)
            ).all()
            tipo.categorias_documento = categorias
            
            db.add(tipo)
            tipos_criados += 1
    
    db.commit()
    
    return {
        "message": "Seed executado com sucesso",
        "categorias_criadas": categorias_criadas,
        "tipos_criados": tipos_criados
    }


# ===========================================
# Página Admin HTML
# ===========================================

@router.get("/admin", response_class=HTMLResponse)
async def pagina_admin_config_pecas(request: Request):
    """Página de administração de tipos de peça e categorias.
    A autenticação é feita via JavaScript no cliente."""
    return templates.TemplateResponse(
        "admin_config_pecas.html",
        {"request": request}
    )
