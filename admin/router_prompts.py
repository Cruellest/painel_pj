# admin/router_prompts.py
"""
Router para gerenciamento de prompts modulares
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime
import difflib

from database.connection import get_db
from utils.timezone import to_iso_utc, now_utc
from auth.models import User
from auth.dependencies import get_current_active_user, require_admin
from admin.models_prompts import PromptModulo, PromptModuloHistorico, ModuloTipoPeca, RegraDeterministicaTipoPeca
from admin.models_prompt_groups import PromptGroup, PromptSubgroup, PromptSubcategoria

router = APIRouter(prefix="/prompts-modulos", tags=["Prompts Modulares"])


# ==========================================
# Utilitários para normalização de booleanos
# ==========================================

def normalizar_booleanos_regra(regra: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Normaliza valores booleanos em uma regra determinística (AST JSON).
    
    Converte:
    - 1 -> True
    - 0 -> False
    - "1" -> True
    - "0" -> False
    - "true" -> True
    - "false" -> False
    
    Isso garante que os valores booleanos sejam sempre persistidos como
    true/false nativos do JSON, não como 1/0 (comportamento de alguns drivers SQLite).
    """
    if regra is None:
        return None
    
    def normalizar_valor(valor: Any) -> Any:
        """Normaliza um valor individual para boolean se aplicável."""
        if valor is None:
            return None
        # Já é boolean, retorna como está
        if isinstance(valor, bool):
            return valor
        # Inteiro 1/0 -> boolean
        if isinstance(valor, int) and valor in (0, 1):
            return bool(valor)
        # String "1"/"0" ou "true"/"false" -> boolean
        if isinstance(valor, str):
            if valor.lower() in ("true", "1"):
                return True
            if valor.lower() in ("false", "0"):
                return False
        # Outros valores retornam como estão
        return valor
    
    def normalizar_no(no: Dict[str, Any]) -> Dict[str, Any]:
        """Normaliza um nó da árvore recursivamente."""
        if not isinstance(no, dict):
            return no
        
        resultado = {}
        for chave, valor in no.items():
            if chave == "value":
                # Normaliza o campo value
                resultado[chave] = normalizar_valor(valor)
            elif chave == "conditions" and isinstance(valor, list):
                # Recursivamente normaliza condições aninhadas
                resultado[chave] = [normalizar_no(c) for c in valor]
            elif chave == "condition" and isinstance(valor, dict):
                # Normaliza condição singular (para 'not')
                resultado[chave] = normalizar_no(valor)
            else:
                resultado[chave] = valor
        
        return resultado
    
    return normalizar_no(regra)


# ==========================================
# Schemas
# ==========================================

class PromptModuloBase(BaseModel):
    tipo: str  # 'base', 'peca', 'conteudo'
    categoria: Optional[str] = None
    subcategoria: Optional[str] = None  # Campo texto legado
    subcategoria_ids: Optional[List[int]] = []  # IDs das subcategorias (muitos-para-muitos)
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None
    nome: str
    titulo: str
    condicao_ativacao: Optional[str] = None  # Situação em que o prompt deve ser ativado (para Agente 2)
    conteudo: str  # Conteúdo do prompt (para Agente 3)
    # Modo de ativação: 'llm' (padrão) ou 'deterministic'
    modo_ativacao: Optional[str] = 'llm'
    # Regra determinística PRIMÁRIA (AST JSON) - apenas quando modo_ativacao = 'deterministic'
    regra_deterministica: Optional[dict] = None
    # Texto original da regra primária em linguagem natural
    regra_texto_original: Optional[str] = None
    # Regra determinística SECUNDÁRIA (fallback) - avaliada se primária não existe
    regra_deterministica_secundaria: Optional[dict] = None
    # Texto original da regra secundária em linguagem natural
    regra_secundaria_texto_original: Optional[str] = None
    # Se deve avaliar regra secundária quando primária não existe
    fallback_habilitado: Optional[bool] = False
    tags: Optional[List[str]] = []
    ativo: bool = True
    ordem: int = 0


class PromptModuloCreate(PromptModuloBase):
    pass


class PromptModuloUpdate(BaseModel):
    titulo: Optional[str] = None
    categoria: Optional[str] = None  # Campo texto para agrupamento visual
    subcategoria: Optional[str] = None  # Campo texto legado para organização
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None
    subcategoria_ids: Optional[List[int]] = None  # IDs das subcategorias (muitos-para-muitos)
    condicao_ativacao: Optional[str] = None  # Atualiza condição de ativação
    conteudo: Optional[str] = None
    # Modo de ativação: 'llm' ou 'deterministic'
    modo_ativacao: Optional[str] = None
    # Regra determinística PRIMÁRIA (AST JSON)
    regra_deterministica: Optional[dict] = None
    # Texto original da regra primária em linguagem natural
    regra_texto_original: Optional[str] = None
    # Regra determinística SECUNDÁRIA (fallback)
    regra_deterministica_secundaria: Optional[dict] = None
    # Texto original da regra secundária em linguagem natural
    regra_secundaria_texto_original: Optional[str] = None
    # Se deve avaliar regra secundária quando primária não existe
    fallback_habilitado: Optional[bool] = None
    tags: Optional[List[str]] = None
    ativo: Optional[bool] = None
    ordem: Optional[int] = None
    motivo: Optional[str] = None  # Opcional - motivo da alteração


class PromptModuloResponse(BaseModel):
    id: int
    tipo: str
    categoria: Optional[str] = None
    subcategoria: Optional[str] = None
    subcategoria_ids: List[int] = []
    subcategorias_nomes: List[str] = []  # Nomes das subcategorias para exibição
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None
    nome: str
    titulo: str
    condicao_ativacao: Optional[str] = None
    conteudo: str
    # Modo de ativação: 'llm' ou 'deterministic'
    modo_ativacao: Optional[str] = 'llm'
    # Regra determinística PRIMÁRIA (AST JSON)
    regra_deterministica: Optional[dict] = None
    # Texto original da regra primária em linguagem natural
    regra_texto_original: Optional[str] = None
    # Regra determinística SECUNDÁRIA (fallback)
    regra_deterministica_secundaria: Optional[dict] = None
    # Texto original da regra secundária em linguagem natural
    regra_secundaria_texto_original: Optional[str] = None
    # Se deve avaliar regra secundária quando primária não existe
    fallback_habilitado: Optional[bool] = False
    # Palavras-chave para ativação
    palavras_chave: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    ativo: bool = True
    ordem: int = 0
    versao: int
    criado_por: Optional[int]
    criado_em: datetime
    atualizado_por: Optional[int]
    atualizado_em: Optional[datetime]

    class Config:
        from_attributes = True


class PromptHistoricoResponse(BaseModel):
    id: int
    modulo_id: int
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None
    versao: int
    condicao_ativacao: Optional[str]
    conteudo: str
    tags: Optional[List[str]]
    alterado_por: Optional[int]
    alterado_em: datetime
    motivo: Optional[str]
    diff_resumo: Optional[str]

    class Config:
        from_attributes = True


class DiffResponse(BaseModel):
    v1: int
    v2: int
    diff_html: str
    alteracoes: int


class PromptGroupBase(BaseModel):
    name: str
    slug: str
    active: bool = True
    order: int = 0


class PromptGroupCreate(PromptGroupBase):
    pass


class PromptGroupUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    active: Optional[bool] = None
    order: Optional[int] = None


class PromptGroupResponse(PromptGroupBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PromptSubgroupBase(BaseModel):
    group_id: int
    name: str
    slug: str
    active: bool = True
    order: int = 0


class PromptSubgroupCreate(PromptSubgroupBase):
    pass


class PromptSubgroupUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    active: Optional[bool] = None
    order: Optional[int] = None


class PromptSubgroupResponse(PromptSubgroupBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Schemas para Subcategorias
class PromptSubcategoriaBase(BaseModel):
    nome: str
    slug: str
    descricao: Optional[str] = None
    active: bool = True
    order: int = 0


class PromptSubcategoriaCreate(PromptSubcategoriaBase):
    pass


class PromptSubcategoriaUpdate(BaseModel):
    nome: Optional[str] = None
    slug: Optional[str] = None
    descricao: Optional[str] = None
    active: Optional[bool] = None
    order: Optional[int] = None


class PromptSubcategoriaResponse(PromptSubcategoriaBase):
    id: int
    group_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# Funções auxiliares
# ==========================================

def gerar_diff_resumo(texto_antigo: str, texto_novo: str) -> str:
    """Gera um resumo das diferenças entre duas versões"""
    linhas_antigas = texto_antigo.splitlines()
    linhas_novas = texto_novo.splitlines()
    
    diff = list(difflib.unified_diff(linhas_antigas, linhas_novas, lineterm=''))
    
    adicoes = sum(1 for l in diff if l.startswith('+') and not l.startswith('+++'))
    remocoes = sum(1 for l in diff if l.startswith('-') and not l.startswith('---'))
    
    return f"+{adicoes} linhas, -{remocoes} linhas"


def gerar_diff_html(texto_antigo: str, texto_novo: str) -> str:
    """Gera diff em formato HTML para visualização"""
    linhas_antigas = texto_antigo.splitlines()
    linhas_novas = texto_novo.splitlines()
    
    diff = difflib.HtmlDiff()
    html = diff.make_table(linhas_antigas, linhas_novas, fromdesc='Anterior', todesc='Atual', context=True, numlines=3)
    
    return html


def verificar_permissao_prompts(user: User, acao: str = "editar"):
    """Verifica se usuário tem permissão para gerenciar prompts"""
    permissao = f"{acao}_prompts"
    if not user.tem_permissao(permissao):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Sem permissão para {acao} prompts"
        )


# ==========================================
# Endpoints de Listagem
# ==========================================

@router.get("", response_model=List[PromptModuloResponse])
async def listar_modulos(
    tipo: Optional[str] = None,
    categoria: Optional[str] = None,
    group_id: Optional[int] = None,
    subgroup_id: Optional[int] = None,
    subcategoria_ids: Optional[List[int]] = Query(None, description="IDs das subcategorias (assuntos) para filtrar"),
    modo_ativacao: Optional[str] = Query(None, description="Filtrar por modo de ativação: 'llm' ou 'deterministic'"),
    busca: Optional[str] = None,
    apenas_ativos: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todos os módulos de prompts com filtros"""
    from admin.models_prompts import prompt_modulo_subcategorias

    query = db.query(PromptModulo)

    if apenas_ativos:
        query = query.filter(PromptModulo.ativo == True)

    if tipo:
        query = query.filter(PromptModulo.tipo == tipo)

    if categoria:
        query = query.filter(PromptModulo.categoria == categoria)

    if group_id:
        # Grupo só filtra módulos de conteúdo - peça e base são globais
        query = query.filter(
            (PromptModulo.group_id == group_id) |
            (PromptModulo.tipo.in_(["peca", "base"]))
        )

    if subgroup_id:
        # Subgrupo só filtra módulos de conteúdo
        query = query.filter(
            (PromptModulo.subgroup_id == subgroup_id) |
            (PromptModulo.tipo.in_(["peca", "base"]))
        )

    # Filtro por modo de ativação (llm ou deterministic)
    if modo_ativacao:
        if modo_ativacao == 'llm':
            # LLM: modo_ativacao é 'llm' ou NULL (valor padrão)
            query = query.filter(
                (PromptModulo.modo_ativacao == 'llm') |
                (PromptModulo.modo_ativacao.is_(None))
            )
        elif modo_ativacao == 'deterministic':
            query = query.filter(PromptModulo.modo_ativacao == 'deterministic')

    # Filtro por subcategorias (assuntos) - lógica OR (qualquer um dos assuntos selecionados)
    # NOTA: Usa subquery para evitar DISTINCT em colunas JSON (PostgreSQL não suporta)
    if subcategoria_ids:
        subquery_ids = db.query(prompt_modulo_subcategorias.c.modulo_id).filter(
            prompt_modulo_subcategorias.c.subcategoria_id.in_(subcategoria_ids)
        ).distinct().subquery()
        query = query.filter(PromptModulo.id.in_(subquery_ids))

    if busca:
        busca_like = f"%{busca}%"
        query = query.filter(
            (PromptModulo.titulo.ilike(busca_like)) |
            (PromptModulo.nome.ilike(busca_like)) |
            (PromptModulo.conteudo.ilike(busca_like))
        )

    # Eager loading para evitar N+1 queries nas subcategorias
    query = query.options(joinedload(PromptModulo.subcategorias))

    modulos = query.order_by(PromptModulo.tipo, PromptModulo.categoria, PromptModulo.ordem).all()

    # ==========================================================================
    # REGRA DE OURO: Calcula effective_activation_mode para cada módulo
    # O frontend DEVE usar este campo, não deduzir baseado em regras
    # ==========================================================================
    from sistemas.gerador_pecas.services_deterministic import resolve_activation_mode_from_db

    # Adiciona subcategoria_ids e subcategorias_nomes a cada modulo (agora sem queries extras)
    result = []
    for modulo in modulos:
        # Calcula o modo efetivo REAL
        effective_mode = resolve_activation_mode_from_db(
            db=db,
            modulo_id=modulo.id,
            modo_ativacao_salvo=modulo.modo_ativacao,
            regra_primaria=modulo.regra_deterministica,
            regra_secundaria=modulo.regra_deterministica_secundaria,
            fallback_habilitado=modulo.fallback_habilitado or False
        )

        modulo_dict = {
            "id": modulo.id,
            "tipo": modulo.tipo,
            "categoria": modulo.categoria,
            "subcategoria": modulo.subcategoria,
            "subcategoria_ids": [s.id for s in modulo.subcategorias],
            "subcategorias_nomes": [s.nome for s in modulo.subcategorias],
            "group_id": modulo.group_id,
            "subgroup_id": modulo.subgroup_id,
            "nome": modulo.nome,
            "titulo": modulo.titulo,
            "condicao_ativacao": modulo.condicao_ativacao,
            "conteudo": modulo.conteudo,
            # Campos de modo determinístico (primária) - normaliza booleanos 1/0 para true/false
            "modo_ativacao": modulo.modo_ativacao or 'llm',
            # ==========================================================================
            # CAMPO OBRIGATÓRIO: effective_activation_mode
            # Este é o ÚNICO campo que o frontend deve usar para mostrar o badge
            # ==========================================================================
            "effective_activation_mode": effective_mode,
            "regra_deterministica": normalizar_booleanos_regra(modulo.regra_deterministica),
            "regra_texto_original": modulo.regra_texto_original,
            # Campos de regra secundária (fallback) - normaliza booleanos 1/0 para true/false
            "regra_deterministica_secundaria": normalizar_booleanos_regra(modulo.regra_deterministica_secundaria),
            "regra_secundaria_texto_original": modulo.regra_secundaria_texto_original,
            "fallback_habilitado": modulo.fallback_habilitado or False,
            "palavras_chave": modulo.palavras_chave,
            "tags": modulo.tags,
            "ativo": modulo.ativo,
            "ordem": modulo.ordem,
            "versao": modulo.versao,
            "criado_por": modulo.criado_por,
            "criado_em": modulo.criado_em,
            "atualizado_por": modulo.atualizado_por,
            "atualizado_em": modulo.atualizado_em,
        }
        result.append(modulo_dict)
    return result


@router.get("/categorias")
async def listar_categorias(
    group_id: Optional[int] = None,
    apenas_ativos: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todas as categorias disponíveis (de módulos ativos por padrão)"""
    query = db.query(PromptModulo.categoria).distinct().filter(
        PromptModulo.categoria.isnot(None),
        PromptModulo.tipo.in_(["base", "peca", "conteudo"])  # Apenas tipos válidos
    )
    if apenas_ativos:
        query = query.filter(PromptModulo.ativo == True)
    if group_id:
        query = query.filter(PromptModulo.group_id == group_id)
    categorias = query.all()
    return [c[0] for c in categorias if c[0]]


@router.get("/tipos")
async def listar_tipos(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todos os tipos de módulos (sem 'base' - o base fica em Prompts de IA)"""
    return ["peca", "conteudo"]


@router.get("/tipos-peca")
async def listar_tipos_peca(
    group_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todos os tipos de peça disponíveis (módulos tipo='peca').
    Tipos de peça são globais (não pertencem a grupos específicos).
    O parâmetro group_id é ignorado pois tipos de peça são sempre globais.
    """
    query = db.query(PromptModulo).filter(
        PromptModulo.tipo == "peca",
        PromptModulo.ativo == True
    )

    # Tipos de peça são globais - não filtra por grupo
    modulos_peca = query.order_by(PromptModulo.ordem).all()

    return [
        {
            "id": m.id,
            "categoria": m.categoria,
            "titulo": m.titulo,
            "nome": m.nome
        }
        for m in modulos_peca
    ]


@router.get("/resumo-configuracao-tipos-peca")
async def resumo_configuracao_tipos_peca(
    group_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retorna um resumo da configuração de módulos por tipo de peça.
    Mostra quantos módulos estão ativos para cada tipo.
    O group_id filtra apenas os módulos de conteúdo, não os tipos de peça.
    """
    from sqlalchemy import func, case

    # Busca tipos de peça (são globais, não filtra por grupo)
    tipos_peca = db.query(PromptModulo).filter(
        PromptModulo.tipo == "peca",
        PromptModulo.ativo == True
    ).all()

    # Conta total de módulos de conteúdo
    query_conteudo = db.query(PromptModulo).filter(
        PromptModulo.tipo == "conteudo",
        PromptModulo.ativo == True
    )
    if group_id:
        query_conteudo = query_conteudo.filter(PromptModulo.group_id == group_id)
    total_modulos = query_conteudo.count()

    # Query única para contar ativos/inativos por tipo_peca (evita N+1)
    contagens = db.query(
        ModuloTipoPeca.tipo_peca,
        func.sum(case((ModuloTipoPeca.ativo == True, 1), else_=0)).label('ativos'),
        func.sum(case((ModuloTipoPeca.ativo == False, 1), else_=0)).label('inativos')
    ).group_by(ModuloTipoPeca.tipo_peca).all()

    # Mapeia resultados
    contagens_map = {c.tipo_peca: {'ativos': c.ativos or 0, 'inativos': c.inativos or 0} for c in contagens}

    resultado = []
    for tipo in tipos_peca:
        contagem = contagens_map.get(tipo.categoria, {'ativos': 0, 'inativos': 0})
        ativos = contagem['ativos']
        inativos = contagem['inativos']

        # Módulos sem associação (considerados ativos por padrão)
        sem_config = total_modulos - ativos - inativos

        resultado.append({
            "tipo_peca": tipo.categoria,
            "titulo": tipo.titulo,
            "modulos_ativos": ativos + sem_config,  # Inclui sem config como ativos
            "modulos_inativos": inativos,
            "modulos_configurados": ativos + inativos,
            "total_modulos": total_modulos
        })

    return {
        "tipos_peca": resultado,
        "total_modulos_conteudo": total_modulos
    }


# ==========================================
# Endpoints CRUD
# ==========================================

# ==========================================
# Endpoints Grupos/Subgrupos
# ==========================================

@router.get("/grupos", response_model=List[PromptGroupResponse])
async def listar_grupos(
    apenas_ativos: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    query = db.query(PromptGroup)
    if apenas_ativos:
        query = query.filter(PromptGroup.active == True)
    grupos = query.order_by(PromptGroup.order, PromptGroup.name).all()
    return grupos


@router.post("/grupos", response_model=PromptGroupResponse, status_code=status.HTTP_201_CREATED)
async def criar_grupo(
    grupo_data: PromptGroupCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    verificar_permissao_prompts(current_user, "criar")

    slug = grupo_data.slug.strip().lower()
    if not slug:
        raise HTTPException(status_code=400, detail="Slug do grupo e obrigatorio")

    existente = db.query(PromptGroup).filter(PromptGroup.slug == slug).first()
    if existente:
        raise HTTPException(status_code=400, detail="Slug de grupo ja existe")

    grupo = PromptGroup(
        name=grupo_data.name.strip(),
        slug=slug,
        active=grupo_data.active,
        order=grupo_data.order
    )
    db.add(grupo)
    db.commit()
    db.refresh(grupo)
    return grupo


@router.put("/grupos/{group_id}", response_model=PromptGroupResponse)
async def atualizar_grupo(
    group_id: int,
    grupo_data: PromptGroupUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    verificar_permissao_prompts(current_user, "editar")

    grupo = db.query(PromptGroup).filter(PromptGroup.id == group_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")

    if grupo_data.slug:
        slug = grupo_data.slug.strip().lower()
        existente = db.query(PromptGroup).filter(
            PromptGroup.slug == slug,
            PromptGroup.id != group_id
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="Slug de grupo ja existe")
        grupo.slug = slug

    update_data = grupo_data.model_dump(exclude_unset=True, exclude={"slug"})
    for field, value in update_data.items():
        setattr(grupo, field, value)

    db.commit()
    db.refresh(grupo)
    return grupo


@router.get("/grupos/{group_id}/subgrupos", response_model=List[PromptSubgroupResponse])
async def listar_subgrupos(
    group_id: int,
    apenas_ativos: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    query = db.query(PromptSubgroup).filter(PromptSubgroup.group_id == group_id)
    if apenas_ativos:
        query = query.filter(PromptSubgroup.active == True)
    subgrupos = query.order_by(PromptSubgroup.order, PromptSubgroup.name).all()
    return subgrupos


@router.post("/grupos/{group_id}/subgrupos", response_model=PromptSubgroupResponse, status_code=status.HTTP_201_CREATED)
async def criar_subgrupo(
    group_id: int,
    subgrupo_data: PromptSubgroupCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    verificar_permissao_prompts(current_user, "criar")

    grupo = db.query(PromptGroup).filter(PromptGroup.id == group_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")

    slug = subgrupo_data.slug.strip().lower()
    if not slug:
        raise HTTPException(status_code=400, detail="Slug do subgrupo e obrigatorio")

    existente = db.query(PromptSubgroup).filter(
        PromptSubgroup.group_id == group_id,
        PromptSubgroup.slug == slug
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Slug de subgrupo ja existe no grupo")

    subgrupo = PromptSubgroup(
        group_id=group_id,
        name=subgrupo_data.name.strip(),
        slug=slug,
        active=subgrupo_data.active,
        order=subgrupo_data.order
    )
    db.add(subgrupo)
    db.commit()
    db.refresh(subgrupo)
    return subgrupo


@router.put("/subgrupos/{subgroup_id}", response_model=PromptSubgroupResponse)
async def atualizar_subgrupo(
    subgroup_id: int,
    subgrupo_data: PromptSubgroupUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    verificar_permissao_prompts(current_user, "editar")

    subgrupo = db.query(PromptSubgroup).filter(PromptSubgroup.id == subgroup_id).first()
    if not subgrupo:
        raise HTTPException(status_code=404, detail="Subgrupo nao encontrado")

    if subgrupo_data.slug:
        slug = subgrupo_data.slug.strip().lower()
        existente = db.query(PromptSubgroup).filter(
            PromptSubgroup.group_id == subgrupo.group_id,
            PromptSubgroup.slug == slug,
            PromptSubgroup.id != subgroup_id
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="Slug de subgrupo ja existe no grupo")
        subgrupo.slug = slug

    update_data = subgrupo_data.model_dump(exclude_unset=True, exclude={"slug"})
    for field, value in update_data.items():
        setattr(subgrupo, field, value)

    db.commit()
    db.refresh(subgrupo)
    return subgrupo


@router.delete("/subgrupos/{subgroup_id}")
async def deletar_subgrupo(
    subgroup_id: int,
    force: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deleta um subgrupo. Use force=true para remover associacoes e deletar mesmo com modulos vinculados."""
    verificar_permissao_prompts(current_user, "excluir")

    try:
        subgrupo = db.query(PromptSubgroup).filter(PromptSubgroup.id == subgroup_id).first()
        if not subgrupo:
            raise HTTPException(status_code=404, detail="Subgrupo nao encontrado")

        # Verifica se há módulos usando este subgrupo
        modulos_usando = db.query(PromptModulo).filter(
            PromptModulo.subgroup_id == subgroup_id
        ).count()

        if modulos_usando > 0 and not force:
            raise HTTPException(
                status_code=409,
                detail=f"{modulos_usando} modulo(s) estao usando este subgrupo"
            )

        # Se force=true, remove a associação dos módulos e histórico
        if force:
            # Remove referência nos módulos
            if modulos_usando > 0:
                db.query(PromptModulo).filter(
                    PromptModulo.subgroup_id == subgroup_id
                ).update({PromptModulo.subgroup_id: None}, synchronize_session=False)

            # Remove referência no histórico de módulos (foreign key constraint)
            db.query(PromptModuloHistorico).filter(
                PromptModuloHistorico.subgroup_id == subgroup_id
            ).update({PromptModuloHistorico.subgroup_id: None}, synchronize_session=False)

        nome = subgrupo.name
        db.delete(subgrupo)
        db.commit()

        if modulos_usando > 0:
            return {"message": f"Subgrupo '{nome}' deletado com sucesso. {modulos_usando} modulo(s) foram desvinculados."}
        return {"message": f"Subgrupo '{nome}' deletado com sucesso"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao deletar subgrupo: {str(e)}")


# ==========================================
# Endpoints Subcategorias
# ==========================================

@router.get("/subcategorias")
async def listar_todas_subcategorias(
    apenas_ativas: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todas as subcategorias (assuntos) de todos os grupos"""
    query = db.query(PromptSubcategoria).join(PromptGroup)
    if apenas_ativas:
        query = query.filter(PromptSubcategoria.active == True)
    subcategorias = query.order_by(PromptGroup.name, PromptSubcategoria.order, PromptSubcategoria.nome).all()

    # Retorna com nome do grupo para facilitar exibição
    result = []
    for sub in subcategorias:
        grupo = db.query(PromptGroup).filter(PromptGroup.id == sub.group_id).first()
        result.append({
            "id": sub.id,
            "group_id": sub.group_id,
            "group_name": grupo.name if grupo else "",
            "nome": sub.nome,
            "slug": sub.slug,
            "descricao": sub.descricao,
            "active": sub.active,
            "order": sub.order,
            "created_at": sub.created_at,
            "updated_at": sub.updated_at
        })
    return result


@router.get("/grupos/{group_id}/subcategorias", response_model=List[PromptSubcategoriaResponse])
async def listar_subcategorias(
    group_id: int,
    apenas_ativas: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista subcategorias de um grupo"""
    query = db.query(PromptSubcategoria).filter(PromptSubcategoria.group_id == group_id)
    if apenas_ativas:
        query = query.filter(PromptSubcategoria.active == True)
    subcategorias = query.order_by(PromptSubcategoria.order, PromptSubcategoria.nome).all()
    return subcategorias


@router.post("/grupos/{group_id}/subcategorias", response_model=PromptSubcategoriaResponse, status_code=status.HTTP_201_CREATED)
async def criar_subcategoria(
    group_id: int,
    subcategoria_data: PromptSubcategoriaCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cria uma nova subcategoria para um grupo"""
    verificar_permissao_prompts(current_user, "criar")

    grupo = db.query(PromptGroup).filter(PromptGroup.id == group_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")

    slug = subcategoria_data.slug.strip().lower().replace(" ", "_")
    if not slug:
        raise HTTPException(status_code=400, detail="Slug da subcategoria e obrigatorio")

    existente = db.query(PromptSubcategoria).filter(
        PromptSubcategoria.group_id == group_id,
        PromptSubcategoria.slug == slug
    ).first()
    if existente:
        raise HTTPException(status_code=400, detail="Subcategoria com este slug ja existe no grupo")

    subcategoria = PromptSubcategoria(
        group_id=group_id,
        nome=subcategoria_data.nome.strip(),
        slug=slug,
        descricao=subcategoria_data.descricao,
        active=subcategoria_data.active,
        order=subcategoria_data.order
    )
    db.add(subcategoria)
    db.commit()
    db.refresh(subcategoria)
    return subcategoria


@router.put("/subcategorias/{subcategoria_id}", response_model=PromptSubcategoriaResponse)
async def atualizar_subcategoria(
    subcategoria_id: int,
    subcategoria_data: PromptSubcategoriaUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Atualiza uma subcategoria"""
    verificar_permissao_prompts(current_user, "editar")

    subcategoria = db.query(PromptSubcategoria).filter(PromptSubcategoria.id == subcategoria_id).first()
    if not subcategoria:
        raise HTTPException(status_code=404, detail="Subcategoria nao encontrada")

    if subcategoria_data.slug:
        slug = subcategoria_data.slug.strip().lower().replace(" ", "_")
        existente = db.query(PromptSubcategoria).filter(
            PromptSubcategoria.group_id == subcategoria.group_id,
            PromptSubcategoria.slug == slug,
            PromptSubcategoria.id != subcategoria_id
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="Slug de subcategoria ja existe no grupo")
        subcategoria.slug = slug

    update_data = subcategoria_data.model_dump(exclude_unset=True, exclude={"slug"})
    for field, value in update_data.items():
        setattr(subcategoria, field, value)

    db.commit()
    db.refresh(subcategoria)
    return subcategoria


@router.delete("/subcategorias/{subcategoria_id}")
async def deletar_subcategoria(
    subcategoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Deleta uma subcategoria"""
    verificar_permissao_prompts(current_user, "deletar")

    subcategoria = db.query(PromptSubcategoria).filter(PromptSubcategoria.id == subcategoria_id).first()
    if not subcategoria:
        raise HTTPException(status_code=404, detail="Subcategoria nao encontrada")

    # Verifica se há módulos usando esta subcategoria
    modulos_usando = db.query(PromptModulo).filter(
        PromptModulo.subcategoria == subcategoria.slug,
        PromptModulo.group_id == subcategoria.group_id
    ).count()

    if modulos_usando > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Nao e possivel deletar: {modulos_usando} modulo(s) estao usando esta subcategoria"
        )

    db.delete(subcategoria)
    db.commit()
    return {"message": "Subcategoria deletada com sucesso"}


@router.get("/{modulo_id}", response_model=PromptModuloResponse)
async def obter_modulo(
    modulo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém um módulo específico"""
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()

    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")

    # Retorna com subcategoria_ids e normaliza booleanos nas regras (1/0 -> true/false)
    response = modulo.__dict__.copy()
    response["subcategoria_ids"] = [s.id for s in modulo.subcategorias]
    response["regra_deterministica"] = normalizar_booleanos_regra(modulo.regra_deterministica)
    response["regra_deterministica_secundaria"] = normalizar_booleanos_regra(modulo.regra_deterministica_secundaria)

    # ==========================================================================
    # REGRA DE OURO: Calcula effective_activation_mode
    # O frontend DEVE usar este campo para mostrar o badge, não deduzir
    # ==========================================================================
    from sistemas.gerador_pecas.services_deterministic import resolve_activation_mode_from_db
    response["effective_activation_mode"] = resolve_activation_mode_from_db(
        db=db,
        modulo_id=modulo.id,
        modo_ativacao_salvo=modulo.modo_ativacao,
        regra_primaria=modulo.regra_deterministica,
        regra_secundaria=modulo.regra_deterministica_secundaria,
        fallback_habilitado=modulo.fallback_habilitado or False
    )

    # Validação de integridade: verifica variáveis inválidas nas regras
    # Usa effective_activation_mode para determinar se deve validar
    if response["effective_activation_mode"] == 'deterministic':
        try:
            from sistemas.gerador_pecas.services_deterministic import RuleIntegrityValidator
            validator = RuleIntegrityValidator(db)
            validacao = validator.validar_modulo(modulo.id)
            response["validacao_integridade"] = {
                "valido": validacao["valido"],
                "variaveis_invalidas": validacao["variaveis_invalidas"],
                "resumo": validacao["resumo"]
            }
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Erro ao validar integridade: {e}")
            response["validacao_integridade"] = None

    return response


@router.post("", response_model=PromptModuloResponse, status_code=status.HTTP_201_CREATED)
async def criar_modulo(
    modulo_data: PromptModuloCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cria um novo módulo de prompt"""
    verificar_permissao_prompts(current_user, "criar")
    
    # Verifica se já existe com mesmo nome
    if modulo_data.tipo == "peca":
        # Para peça, verifica apenas tipo + nome (categoria/subcategoria são null)
        existente = db.query(PromptModulo).filter(
            PromptModulo.tipo == "peca",
            PromptModulo.nome == modulo_data.nome
        ).first()
    else:
        existente = db.query(PromptModulo).filter(
            PromptModulo.tipo == modulo_data.tipo,
            PromptModulo.categoria == modulo_data.categoria,
            PromptModulo.subcategoria == modulo_data.subcategoria,
            PromptModulo.nome == modulo_data.nome
        ).first()

    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe um módulo com este nome" if modulo_data.tipo == "peca" else "Já existe um módulo com esta combinação tipo/categoria/subcategoria/nome"
        )

    group_id = modulo_data.group_id
    subgroup_id = modulo_data.subgroup_id
    if modulo_data.tipo == "conteudo":
        if not group_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Grupo e obrigatorio para modulo de conteudo"
            )
        grupo = db.query(PromptGroup).filter(PromptGroup.id == group_id).first()
        if not grupo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Grupo invalido"
            )
        if subgroup_id:
            subgrupo = db.query(PromptSubgroup).filter(
                PromptSubgroup.id == subgroup_id,
                PromptSubgroup.group_id == group_id
            ).first()
            if not subgrupo:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Subgrupo invalido para o grupo informado"
                )
    else:
        group_id = None
        subgroup_id = None
    
    modulo_payload = modulo_data.model_dump(exclude={"subcategoria_ids"})

    # Normaliza booleanos nas regras determinísticas antes de salvar (1/0 -> true/false)
    if modulo_payload.get("regra_deterministica"):
        modulo_payload["regra_deterministica"] = normalizar_booleanos_regra(modulo_payload["regra_deterministica"])
    if modulo_payload.get("regra_deterministica_secundaria"):
        modulo_payload["regra_deterministica_secundaria"] = normalizar_booleanos_regra(modulo_payload["regra_deterministica_secundaria"])

    # ==========================================================================
    # REGRA DE OURO: Resolve o modo de ativação CORRETO baseado nas regras
    # NUNCA confia no valor enviado pelo frontend - sempre deriva das regras
    # ==========================================================================
    from sistemas.gerador_pecas.services_deterministic import resolve_activation_mode
    modo_correto = resolve_activation_mode(
        modo_ativacao_salvo=modulo_payload.get("modo_ativacao", "llm"),
        regra_primaria=modulo_payload.get("regra_deterministica"),
        regra_secundaria=modulo_payload.get("regra_deterministica_secundaria"),
        fallback_habilitado=modulo_payload.get("fallback_habilitado", False)
    )
    if modulo_payload.get("modo_ativacao") != modo_correto:
        import logging
        logging.getLogger(__name__).info(
            f"[REGRA-DE-OURO] Novo módulo: modo_ativacao forçado de "
            f"'{modulo_payload.get('modo_ativacao')}' para '{modo_correto}'"
        )
    modulo_payload["modo_ativacao"] = modo_correto

    # Prompts de peça não devem ter categoria (categoria é usada como identificador único)
    if modulo_data.tipo == "peca":
        modulo_payload["categoria"] = None
        modulo_payload["subcategoria"] = None
    modulo_payload["group_id"] = group_id
    modulo_payload["subgroup_id"] = subgroup_id

    modulo = PromptModulo(
        **modulo_payload,
        versao=1,
        criado_por=current_user.id,
        atualizado_por=current_user.id
    )

    # Adiciona subcategorias se fornecidas
    if modulo_data.subcategoria_ids:
        subcategorias = db.query(PromptSubcategoria).filter(
            PromptSubcategoria.id.in_(modulo_data.subcategoria_ids),
            PromptSubcategoria.group_id == group_id
        ).all()
        modulo.subcategorias = subcategorias

    db.add(modulo)
    db.commit()
    db.refresh(modulo)

    # ==========================================================================
    # BANCO VETORIAL: Cria embedding se for módulo de conteúdo
    # ==========================================================================
    if modulo.tipo == 'conteudo':
        try:
            from sistemas.gerador_pecas.services_embeddings import atualizar_embedding_modulo_sync
            # Executa em background para não bloquear a resposta
            import threading
            thread = threading.Thread(
                target=atualizar_embedding_modulo_sync,
                args=(modulo.id,),
                daemon=True
            )
            thread.start()
            import logging
            logging.getLogger(__name__).info(f"[EMBEDDING] Agendada criacao do embedding do modulo {modulo.id}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Erro ao agendar criacao de embedding: {e}")

    # Retorna com subcategoria_ids e effective_activation_mode
    response = modulo.__dict__.copy()
    response["subcategoria_ids"] = [s.id for s in modulo.subcategorias]
    # REGRA DE OURO: modo efetivo é sempre o modo já corrigido após salvar
    response["effective_activation_mode"] = modulo.modo_ativacao
    return response


@router.put("/{modulo_id}", response_model=PromptModuloResponse)
async def atualizar_modulo(
    modulo_id: int,
    modulo_data: PromptModuloUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Atualiza um módulo (cria nova versão no histórico)"""
    verificar_permissao_prompts(current_user, "editar")
    
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")

    # Salva versão atual no histórico
    diff_resumo = ""
    if modulo_data.conteudo and modulo_data.conteudo != modulo.conteudo:
        diff_resumo = gerar_diff_resumo(modulo.conteudo, modulo_data.conteudo)

    historico = PromptModuloHistorico(
        modulo_id=modulo.id,
        versao=modulo.versao,
        group_id=modulo.group_id,
        subgroup_id=modulo.subgroup_id,
        condicao_ativacao=modulo.condicao_ativacao,
        conteudo=modulo.conteudo,
        palavras_chave=modulo.palavras_chave,
        tags=modulo.tags,
        # Campos de modo determinístico (primária)
        modo_ativacao=modulo.modo_ativacao,
        regra_deterministica=modulo.regra_deterministica,
        regra_texto_original=modulo.regra_texto_original,
        # Campos de regra secundária (fallback)
        regra_deterministica_secundaria=modulo.regra_deterministica_secundaria,
        regra_secundaria_texto_original=modulo.regra_secundaria_texto_original,
        fallback_habilitado=modulo.fallback_habilitado,
        alterado_por=current_user.id,
        motivo=modulo_data.motivo,
        diff_resumo=diff_resumo
    )
    db.add(historico)
    
    # Atualiza módulo
    update_data = modulo_data.model_dump(exclude_unset=True, exclude={"motivo", "subcategoria_ids"})

    # Normaliza booleanos nas regras determinísticas antes de salvar (1/0 -> true/false)
    if "regra_deterministica" in update_data and update_data["regra_deterministica"]:
        update_data["regra_deterministica"] = normalizar_booleanos_regra(update_data["regra_deterministica"])
    if "regra_deterministica_secundaria" in update_data and update_data["regra_deterministica_secundaria"]:
        update_data["regra_deterministica_secundaria"] = normalizar_booleanos_regra(update_data["regra_deterministica_secundaria"])

    # ==========================================================================
    # REGRA DE OURO: Resolve o modo de ativação CORRETO baseado nas regras
    # Considera as regras ATUAIS do módulo combinadas com as novas do update
    # ==========================================================================
    from sistemas.gerador_pecas.services_deterministic import resolve_activation_mode_from_db

    # Combina regras atuais com as novas (se houver)
    regra_primaria_final = update_data.get("regra_deterministica", modulo.regra_deterministica)
    regra_secundaria_final = update_data.get("regra_deterministica_secundaria", modulo.regra_deterministica_secundaria)
    fallback_final = update_data.get("fallback_habilitado", modulo.fallback_habilitado or False)

    modo_correto = resolve_activation_mode_from_db(
        db=db,
        modulo_id=modulo_id,
        modo_ativacao_salvo=update_data.get("modo_ativacao", modulo.modo_ativacao),
        regra_primaria=regra_primaria_final,
        regra_secundaria=regra_secundaria_final,
        fallback_habilitado=fallback_final
    )

    modo_atual = update_data.get("modo_ativacao", modulo.modo_ativacao)
    if modo_atual != modo_correto:
        import logging
        logging.getLogger(__name__).info(
            f"[REGRA-DE-OURO] Prompt {modulo_id}: modo_ativacao forçado de "
            f"'{modo_atual}' para '{modo_correto}'"
        )
    update_data["modo_ativacao"] = modo_correto

    if modulo.tipo == "peca":
        # Prompts de peça não devem ter categoria/subcategoria
        update_data["categoria"] = None
        update_data["subcategoria"] = None
        update_data["group_id"] = None
        update_data["subgroup_id"] = None
    elif modulo.tipo != "conteudo":
        if "group_id" in update_data:
            update_data["group_id"] = None
        if "subgroup_id" in update_data:
            update_data["subgroup_id"] = None
    else:
        new_group_id = modulo_data.group_id if modulo_data.group_id is not None else modulo.group_id
        if modulo_data.group_id is not None and modulo_data.subgroup_id is None and modulo.group_id != new_group_id:
            update_data["subgroup_id"] = None
    for field, value in update_data.items():
        setattr(modulo, field, value)

    # Atualiza subcategorias se fornecidas
    if modulo_data.subcategoria_ids is not None:
        group_id_atual = modulo.group_id
        subcategorias = db.query(PromptSubcategoria).filter(
            PromptSubcategoria.id.in_(modulo_data.subcategoria_ids),
            PromptSubcategoria.group_id == group_id_atual
        ).all() if modulo_data.subcategoria_ids else []
        modulo.subcategorias = subcategorias

    modulo.versao += 1
    modulo.atualizado_por = current_user.id
    modulo.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(modulo)

    # Sincroniza uso de variáveis se modo determinístico
    if modulo.modo_ativacao == 'deterministic' and modulo.regra_deterministica:
        try:
            from sistemas.gerador_pecas.services_deterministic import PromptVariableUsageSync
            sync = PromptVariableUsageSync(db)
            # Passa tanto regra primária quanto secundária para sincronizar todas as variáveis usadas
            sync.atualizar_uso(
                modulo.id,
                modulo.regra_deterministica,
                modulo.regra_deterministica_secundaria if modulo.fallback_habilitado else None
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Erro ao sincronizar uso de variáveis: {e}")
    elif modulo.modo_ativacao == 'llm':
        # Remove registros de uso se voltou para modo LLM
        try:
            from sistemas.gerador_pecas.services_deterministic import PromptVariableUsageSync
            sync = PromptVariableUsageSync(db)
            sync.atualizar_uso(modulo.id, None, None)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Erro ao limpar uso de variáveis: {e}")

    # ==========================================================================
    # BANCO VETORIAL: Atualiza embedding se for módulo de conteúdo
    # ==========================================================================
    if modulo.tipo == 'conteudo':
        try:
            from sistemas.gerador_pecas.services_embeddings import atualizar_embedding_modulo_sync
            # Executa em background para não bloquear a resposta
            import threading
            thread = threading.Thread(
                target=atualizar_embedding_modulo_sync,
                args=(modulo.id,),
                daemon=True
            )
            thread.start()
            import logging
            logging.getLogger(__name__).info(f"[EMBEDDING] Agendada atualizacao do embedding do modulo {modulo.id}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Erro ao agendar atualizacao de embedding: {e}")

    # Retorna com subcategoria_ids e effective_activation_mode
    response = modulo.__dict__.copy()
    response["subcategoria_ids"] = [s.id for s in modulo.subcategorias]
    response["subcategorias_nomes"] = [s.nome for s in modulo.subcategorias]
    # REGRA DE OURO: modo efetivo é sempre o modo já corrigido após salvar
    response["effective_activation_mode"] = modulo.modo_ativacao

    # Validação de integridade: verifica variáveis inválidas nas regras
    if modulo.modo_ativacao == 'deterministic':
        try:
            from sistemas.gerador_pecas.services_deterministic import RuleIntegrityValidator
            validator = RuleIntegrityValidator(db)
            validacao = validator.validar_modulo(modulo.id)
            response["validacao_integridade"] = {
                "valido": validacao["valido"],
                "variaveis_invalidas": validacao["variaveis_invalidas"],
                "resumo": validacao["resumo"]
            }
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Erro ao validar integridade: {e}")
            response["validacao_integridade"] = None

    return response


@router.delete("/{modulo_id}")
async def desativar_modulo(
    modulo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Desativa um módulo (soft delete)"""
    verificar_permissao_prompts(current_user, "excluir")
    
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    
    modulo.ativo = False
    modulo.atualizado_por = current_user.id
    db.commit()
    
    return {"message": f"Módulo '{modulo.titulo}' desativado com sucesso"}


@router.patch("/{modulo_id}/toggle")
async def toggle_modulo_ativo(
    modulo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Alterna o status ativo/inativo de um módulo."""
    verificar_permissao_prompts(current_user, "editar")

    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()

    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")

    modulo.ativo = not modulo.ativo
    modulo.atualizado_por = current_user.id
    db.commit()

    return {
        "success": True,
        "id": modulo_id,
        "ativo": modulo.ativo,
        "titulo": modulo.titulo,
        "mensagem": f"Módulo '{modulo.titulo}' {'ativado' if modulo.ativo else 'desativado'}"
    }


@router.delete("/{modulo_id}/permanente")
async def excluir_modulo_permanente(
    modulo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exclui um módulo permanentemente (incluindo histórico)"""
    verificar_permissao_prompts(current_user, "excluir")
    
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    
    titulo = modulo.titulo
    
    # Remove histórico primeiro
    db.query(PromptModuloHistorico).filter(
        PromptModuloHistorico.modulo_id == modulo_id
    ).delete()
    
    # Remove o módulo
    db.delete(modulo)
    db.commit()
    
    return {"message": f"Módulo '{titulo}' excluído permanentemente"}


# ==========================================
# Endpoints de Histórico
# ==========================================

@router.get("/{modulo_id}/historico", response_model=List[PromptHistoricoResponse])
async def listar_historico(
    modulo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista histórico de versões de um módulo"""
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    
    historico = db.query(PromptModuloHistorico).filter(
        PromptModuloHistorico.modulo_id == modulo_id
    ).order_by(PromptModuloHistorico.versao.desc()).all()
    
    return historico


@router.get("/{modulo_id}/versao/{versao}", response_model=PromptHistoricoResponse)
async def obter_versao(
    modulo_id: int,
    versao: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém uma versão específica do histórico"""
    historico = db.query(PromptModuloHistorico).filter(
        PromptModuloHistorico.modulo_id == modulo_id,
        PromptModuloHistorico.versao == versao
    ).first()
    
    if not historico:
        raise HTTPException(status_code=404, detail="Versão não encontrada")
    
    return historico


@router.post("/{modulo_id}/restaurar/{versao}")
async def restaurar_versao(
    modulo_id: int,
    versao: int,
    motivo: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Restaura uma versão anterior (cria nova versão com conteúdo antigo)"""
    verificar_permissao_prompts(current_user, "editar")
    
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    
    historico = db.query(PromptModuloHistorico).filter(
        PromptModuloHistorico.modulo_id == modulo_id,
        PromptModuloHistorico.versao == versao
    ).first()
    
    if not historico:
        raise HTTPException(status_code=404, detail="Versão não encontrada")
    
    # Salva versão atual no histórico
    novo_historico = PromptModuloHistorico(
        modulo_id=modulo.id,
        versao=modulo.versao,
        group_id=modulo.group_id,
        subgroup_id=modulo.subgroup_id,
        condicao_ativacao=modulo.condicao_ativacao,
        conteudo=modulo.conteudo,
        palavras_chave=modulo.palavras_chave,
        tags=modulo.tags,
        alterado_por=current_user.id,
        motivo=f"Restauração para v{versao}: {motivo}",
        diff_resumo=gerar_diff_resumo(modulo.conteudo, historico.conteudo)
    )
    db.add(novo_historico)
    
    # Restaura conteúdo
    modulo.group_id = historico.group_id
    modulo.subgroup_id = historico.subgroup_id
    modulo.condicao_ativacao = historico.condicao_ativacao
    modulo.conteudo = historico.conteudo
    modulo.palavras_chave = historico.palavras_chave
    modulo.tags = historico.tags
    modulo.versao += 1
    modulo.atualizado_por = current_user.id
    modulo.atualizado_em = datetime.utcnow()
    
    db.commit()
    
    return {"message": f"Versão {versao} restaurada com sucesso. Nova versão: {modulo.versao}"}


@router.get("/{modulo_id}/comparar", response_model=DiffResponse)
async def comparar_versoes(
    modulo_id: int,
    v1: int,
    v2: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Compara duas versões de um módulo"""
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")
    
    # Obtém versão v1
    if v1 == modulo.versao:
        conteudo_v1 = modulo.conteudo
    else:
        hist_v1 = db.query(PromptModuloHistorico).filter(
            PromptModuloHistorico.modulo_id == modulo_id,
            PromptModuloHistorico.versao == v1
        ).first()
        if not hist_v1:
            raise HTTPException(status_code=404, detail=f"Versão {v1} não encontrada")
        conteudo_v1 = hist_v1.conteudo
    
    # Obtém versão v2
    if v2 == modulo.versao:
        conteudo_v2 = modulo.conteudo
    else:
        hist_v2 = db.query(PromptModuloHistorico).filter(
            PromptModuloHistorico.modulo_id == modulo_id,
            PromptModuloHistorico.versao == v2
        ).first()
        if not hist_v2:
            raise HTTPException(status_code=404, detail=f"Versão {v2} não encontrada")
        conteudo_v2 = hist_v2.conteudo
    
    diff_html = gerar_diff_html(conteudo_v1, conteudo_v2)
    
    # Conta alterações
    linhas_v1 = conteudo_v1.splitlines()
    linhas_v2 = conteudo_v2.splitlines()
    diff = list(difflib.unified_diff(linhas_v1, linhas_v2))
    alteracoes = sum(1 for l in diff if l.startswith('+') or l.startswith('-'))
    
    return DiffResponse(v1=v1, v2=v2, diff_html=diff_html, alteracoes=alteracoes)


# ==========================================
# Endpoints de Exportação/Importação
# ==========================================

@router.get("/exportar/todos")
async def exportar_todos(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exporta todos os módulos em formato JSON"""
    modulos = db.query(PromptModulo).filter(PromptModulo.ativo == True).all()

    export_data = {
        "versao": "2.0",
        "exportado_em": to_iso_utc(now_utc()),
        "exportado_por": current_user.username,
        "modulos": []
    }

    for modulo in modulos:
        # Coleta subcategorias associadas
        subcategorias_lista = []
        if modulo.subcategorias:
            for subcat in modulo.subcategorias:
                subcategorias_lista.append({
                    "slug": subcat.slug,
                    "nome": subcat.nome,
                    "group_slug": subcat.group.slug if subcat.group else None
                })

        export_data["modulos"].append({
            "tipo": modulo.tipo,
            "categoria": modulo.categoria,
            "subcategoria": modulo.subcategoria,
            "group_id": modulo.group_id,
            "group_slug": modulo.group.slug if modulo.group else None,
            "group_name": modulo.group.name if modulo.group else None,
            "subgroup_id": modulo.subgroup_id,
            "subgroup_slug": modulo.subgroup.slug if modulo.subgroup else None,
            "subgroup_name": modulo.subgroup.name if modulo.subgroup else None,
            "subcategorias_associadas": subcategorias_lista,
            "nome": modulo.nome,
            "titulo": modulo.titulo,
            "condicao_ativacao": modulo.condicao_ativacao or "",
            "conteudo": modulo.conteudo,
            "palavras_chave": modulo.palavras_chave or [],
            "tags": modulo.tags or [],
            "ordem": modulo.ordem
        })

    return export_data


class ExportarSelecionadosRequest(BaseModel):
    """Schema para exportação de módulos selecionados"""
    ids: List[int]


@router.post("/exportar/selecionados")
async def exportar_selecionados(
    req: ExportarSelecionadosRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Exporta módulos selecionados em formato JSON compatível com importação"""
    if not req.ids:
        raise HTTPException(status_code=400, detail="Nenhum módulo selecionado")

    modulos = db.query(PromptModulo).filter(PromptModulo.id.in_(req.ids)).all()

    export_data = {
        "versao": "2.0",
        "exportado_em": to_iso_utc(now_utc()),
        "exportado_por": current_user.username,
        "total": len(modulos),
        "modulos": []
    }

    for modulo in modulos:
        # Coleta subcategorias associadas
        subcategorias_lista = []
        if modulo.subcategorias:
            for subcat in modulo.subcategorias:
                subcategorias_lista.append({
                    "slug": subcat.slug,
                    "nome": subcat.nome,
                    "group_slug": subcat.group.slug if subcat.group else None
                })

        export_data["modulos"].append({
            "tipo": modulo.tipo,
            "categoria": modulo.categoria,
            "subcategoria": modulo.subcategoria,
            "group_id": modulo.group_id,
            "group_slug": modulo.group.slug if modulo.group else None,
            "group_name": modulo.group.name if modulo.group else None,
            "subgroup_id": modulo.subgroup_id,
            "subgroup_slug": modulo.subgroup.slug if modulo.subgroup else None,
            "subgroup_name": modulo.subgroup.name if modulo.subgroup else None,
            "subcategorias_associadas": subcategorias_lista,
            "nome": modulo.nome,
            "titulo": modulo.titulo,
            "condicao_ativacao": modulo.condicao_ativacao or "",
            "conteudo": modulo.conteudo,
            "palavras_chave": modulo.palavras_chave or [],
            "tags": modulo.tags or [],
            "ordem": modulo.ordem
        })

    return export_data


class ImportarModulosRequest(BaseModel):
    """Schema para importação de módulos"""
    modulos: List[dict]
    sobrescrever_existentes: bool = False


class ImportarModulosResponse(BaseModel):
    """Resposta da importação"""
    total_recebidos: int
    criados: int
    atualizados: int
    ignorados: int
    grupos_criados: int = 0
    subgrupos_criados: int = 0
    subcategorias_criadas: int = 0
    erros: List[str]


def _obter_ou_criar_grupo(db: Session, grupo_slug: str, grupo_name: str = None) -> PromptGroup:
    """Obtém um grupo existente ou cria um novo se não existir."""
    slug_normalizado = str(grupo_slug).lower().strip()
    grupo = db.query(PromptGroup).filter(PromptGroup.slug == slug_normalizado).first()

    if not grupo:
        # Cria o grupo automaticamente
        nome = grupo_name or slug_normalizado.upper()
        grupo = PromptGroup(
            name=nome,
            slug=slug_normalizado,
            active=True,
            order=0
        )
        db.add(grupo)
        db.flush()  # Garante que o ID seja gerado

    return grupo


def _obter_ou_criar_subgrupo(db: Session, grupo: PromptGroup, subgrupo_slug: str, subgrupo_name: str = None) -> PromptSubgroup:
    """Obtém um subgrupo existente ou cria um novo se não existir."""
    slug_normalizado = str(subgrupo_slug).lower().strip()
    subgrupo = db.query(PromptSubgroup).filter(
        PromptSubgroup.group_id == grupo.id,
        PromptSubgroup.slug == slug_normalizado
    ).first()

    if not subgrupo:
        # Cria o subgrupo automaticamente
        nome = subgrupo_name or slug_normalizado.replace("_", " ").title()
        subgrupo = PromptSubgroup(
            group_id=grupo.id,
            name=nome,
            slug=slug_normalizado,
            active=True,
            order=0
        )
        db.add(subgrupo)
        db.flush()

    return subgrupo


def _obter_ou_criar_subcategoria(db: Session, grupo: PromptGroup, subcat_slug: str, subcat_nome: str = None) -> "PromptSubcategoria":
    """Obtém uma subcategoria existente ou cria uma nova se não existir."""
    from admin.models_prompt_groups import PromptSubcategoria

    slug_normalizado = str(subcat_slug).lower().strip()
    subcategoria = db.query(PromptSubcategoria).filter(
        PromptSubcategoria.group_id == grupo.id,
        PromptSubcategoria.slug == slug_normalizado
    ).first()

    if not subcategoria:
        # Cria a subcategoria automaticamente
        nome = subcat_nome or slug_normalizado.replace("_", " ").title()
        subcategoria = PromptSubcategoria(
            group_id=grupo.id,
            nome=nome,
            slug=slug_normalizado,
            active=True,
            order=0
        )
        db.add(subcategoria)
        db.flush()

    return subcategoria


@router.post("/importar", response_model=ImportarModulosResponse)
async def importar_modulos(
    dados: ImportarModulosRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Importa módulos de prompts a partir de arquivo JSON.
    Cria automaticamente grupos, subgrupos e subcategorias que não existirem.

    Formato esperado do JSON (versão 2.0):
    {
        "modulos": [
            {
                "tipo": "conteudo",
                "categoria": "Preliminar",
                "subcategoria": "Competência",
                "group_slug": "ps",
                "group_name": "Prestação de Saúde",
                "subgroup_slug": "medicamentos",
                "subgroup_name": "Medicamentos",
                "subcategorias_associadas": [
                    {"slug": "alto_custo", "nome": "Alto Custo"}
                ],
                "nome": "prel_jef_estadual",
                "titulo": "Competência do Juizado...",
                "condicao_ativacao": "Quando o juízo for...",
                "conteudo": "## COMPETÊNCIA...",
                "palavras_chave": [],
                "tags": [],
                "ordem": 0
            }
        ]
    }
    """
    verificar_permissao_prompts(current_user, "criar")

    criados = 0
    atualizados = 0
    ignorados = 0
    grupos_criados = 0
    subgrupos_criados = 0
    subcategorias_criadas = 0
    erros = []

    # Cache para grupos/subgrupos/subcategorias criados nesta importação
    grupos_cache = {}
    subgrupos_cache = {}
    subcategorias_cache = {}

    for i, item in enumerate(dados.modulos):
        try:
            # Normalizar campos (aceita formatos diferentes)
            tipo_raw = item.get("tipo", "conteudo")
            tipo = tipo_raw.lower().replace("ú", "u")  # "Conteúdo" -> "conteudo"
            if tipo not in ("base", "peca", "conteudo"):
                tipo = "conteudo"  # Default para conteúdo

            # Aceita "nome_unico" ou "nome"
            nome = item.get("nome_unico") or item.get("nome")
            if not nome:
                erros.append(f"Módulo {i+1}: campo 'nome' ou 'nome_unico' é obrigatório")
                continue

            # Aceita "conteudo_prompt" ou "conteudo"
            conteudo = item.get("conteudo_prompt") or item.get("conteudo")
            if not conteudo:
                erros.append(f"Módulo {i+1} ({nome}): campo 'conteudo' ou 'conteudo_prompt' é obrigatório")
                continue

            titulo = item.get("titulo")
            if not titulo:
                erros.append(f"Módulo {i+1} ({nome}): campo 'titulo' é obrigatório")
                continue

            categoria = item.get("categoria")
            subcategoria = item.get("subcategoria")
            condicao_ativacao = item.get("condicao_ativacao")
            palavras_chave = item.get("palavras_chave", [])
            tags = item.get("tags", [])
            ordem = item.get("ordem", 0)

            # Dados do grupo
            grupo_slug = item.get("group_slug") or item.get("grupo_slug")
            grupo_name = item.get("group_name") or item.get("grupo_name")

            # Dados do subgrupo
            subgrupo_slug = item.get("subgroup_slug")
            subgrupo_name = item.get("subgroup_name")

            # Subcategorias associadas (novo formato v2.0)
            subcategorias_associadas = item.get("subcategorias_associadas", [])

            grupo = None
            subgrupo = None

            if tipo == "conteudo":
                # Obtém ou cria o grupo
                if grupo_slug:
                    cache_key = grupo_slug.lower()
                    if cache_key in grupos_cache:
                        grupo = grupos_cache[cache_key]
                    else:
                        grupo_existia = db.query(PromptGroup).filter(
                            PromptGroup.slug == grupo_slug.lower()
                        ).first() is not None

                        grupo = _obter_ou_criar_grupo(db, grupo_slug, grupo_name)
                        grupos_cache[cache_key] = grupo

                        if not grupo_existia:
                            grupos_criados += 1
                else:
                    # Usa grupo padrão "ps" se não informado
                    grupo = db.query(PromptGroup).filter(PromptGroup.slug == "ps").first()
                    if not grupo:
                        grupo = _obter_ou_criar_grupo(db, "ps", "Prestação de Saúde")
                        grupos_criados += 1

                if not grupo:
                    erros.append(f"Módulo {i+1} ({nome}): não foi possível obter/criar grupo")
                    continue

                # Obtém ou cria o subgrupo (se informado)
                if subgrupo_slug and grupo:
                    cache_key = f"{grupo.id}:{subgrupo_slug.lower()}"
                    if cache_key in subgrupos_cache:
                        subgrupo = subgrupos_cache[cache_key]
                    else:
                        subgrupo_existia = db.query(PromptSubgroup).filter(
                            PromptSubgroup.group_id == grupo.id,
                            PromptSubgroup.slug == subgrupo_slug.lower()
                        ).first() is not None

                        subgrupo = _obter_ou_criar_subgrupo(db, grupo, subgrupo_slug, subgrupo_name)
                        subgrupos_cache[cache_key] = subgrupo

                        if not subgrupo_existia:
                            subgrupos_criados += 1

            # Verifica se já existe
            existente = db.query(PromptModulo).filter(
                PromptModulo.tipo == tipo,
                PromptModulo.categoria == categoria,
                PromptModulo.subcategoria == subcategoria,
                PromptModulo.nome == nome
            ).first()

            modulo_para_associar = None

            if existente:
                if dados.sobrescrever_existentes:
                    # Salva versão atual no histórico
                    diff_resumo = gerar_diff_resumo(existente.conteudo, conteudo)
                    historico = PromptModuloHistorico(
                        modulo_id=existente.id,
                        versao=existente.versao,
                        group_id=existente.group_id,
                        subgroup_id=existente.subgroup_id,
                        condicao_ativacao=existente.condicao_ativacao,
                        conteudo=existente.conteudo,
                        palavras_chave=existente.palavras_chave,
                        tags=existente.tags,
                        alterado_por=current_user.id,
                        motivo="Atualizado via importação JSON",
                        diff_resumo=diff_resumo
                    )
                    db.add(historico)

                    # Atualiza módulo existente
                    existente.titulo = titulo
                    existente.condicao_ativacao = condicao_ativacao
                    existente.conteudo = conteudo
                    existente.palavras_chave = palavras_chave
                    existente.tags = tags
                    existente.ordem = ordem
                    existente.group_id = grupo.id if grupo else None
                    existente.subgroup_id = subgrupo.id if subgrupo else None
                    existente.versao += 1
                    existente.atualizado_por = current_user.id
                    existente.atualizado_em = datetime.utcnow()
                    existente.ativo = True

                    modulo_para_associar = existente
                    atualizados += 1
                else:
                    ignorados += 1
            else:
                # Cria novo módulo
                novo_modulo = PromptModulo(
                    tipo=tipo,
                    categoria=categoria,
                    subcategoria=subcategoria,
                    nome=nome,
                    titulo=titulo,
                    condicao_ativacao=condicao_ativacao,
                    conteudo=conteudo,
                    palavras_chave=palavras_chave,
                    tags=tags,
                    ordem=ordem,
                    group_id=grupo.id if grupo else None,
                    subgroup_id=subgrupo.id if subgrupo else None,
                    ativo=True,
                    versao=1,
                    criado_por=current_user.id,
                    atualizado_por=current_user.id
                )
                db.add(novo_modulo)
                db.flush()  # Garante que o ID seja gerado

                modulo_para_associar = novo_modulo
                criados += 1

            # Associa subcategorias ao módulo (se houver)
            if modulo_para_associar and subcategorias_associadas and grupo:
                # Limpa associações existentes
                modulo_para_associar.subcategorias = []

                for subcat_data in subcategorias_associadas:
                    subcat_slug = subcat_data.get("slug")
                    subcat_nome = subcat_data.get("nome")
                    subcat_group_slug = subcat_data.get("group_slug")

                    if not subcat_slug:
                        continue

                    # Determina o grupo da subcategoria
                    grupo_subcat = grupo
                    if subcat_group_slug and subcat_group_slug.lower() != grupo.slug:
                        cache_key = subcat_group_slug.lower()
                        if cache_key in grupos_cache:
                            grupo_subcat = grupos_cache[cache_key]
                        else:
                            grupo_subcat = _obter_ou_criar_grupo(db, subcat_group_slug)
                            grupos_cache[cache_key] = grupo_subcat

                    # Obtém ou cria a subcategoria
                    cache_key = f"{grupo_subcat.id}:{subcat_slug.lower()}"
                    if cache_key in subcategorias_cache:
                        subcategoria_obj = subcategorias_cache[cache_key]
                    else:
                        from admin.models_prompt_groups import PromptSubcategoria
                        subcat_existia = db.query(PromptSubcategoria).filter(
                            PromptSubcategoria.group_id == grupo_subcat.id,
                            PromptSubcategoria.slug == subcat_slug.lower()
                        ).first() is not None

                        subcategoria_obj = _obter_ou_criar_subcategoria(db, grupo_subcat, subcat_slug, subcat_nome)
                        subcategorias_cache[cache_key] = subcategoria_obj

                        if not subcat_existia:
                            subcategorias_criadas += 1

                    # Associa ao módulo
                    if subcategoria_obj not in modulo_para_associar.subcategorias:
                        modulo_para_associar.subcategorias.append(subcategoria_obj)

        except Exception as e:
            erros.append(f"Módulo {i+1}: {str(e)}")

    db.commit()

    return ImportarModulosResponse(
        total_recebidos=len(dados.modulos),
        criados=criados,
        atualizados=atualizados,
        ignorados=ignorados,
        grupos_criados=grupos_criados,
        subgrupos_criados=subgrupos_criados,
        subcategorias_criadas=subcategorias_criadas,
        erros=erros
    )


# ==========================================
# Endpoints: Associação Módulos x Tipos de Peça
# ==========================================

class ModuloTipoPecaItem(BaseModel):
    """Item de associação módulo-tipo de peça"""
    modulo_id: int
    ativo: bool = True


class ConfigurarModulosTipoPecaRequest(BaseModel):
    """Request para configurar módulos de um tipo de peça"""
    tipo_peca: str  # Ex: 'contestacao', 'recurso_apelacao'
    modulos: List[ModuloTipoPecaItem]  # Lista de módulos com status


class ModuloTipoPecaResponse(BaseModel):
    """Resposta com informações do módulo e status por tipo de peça"""
    modulo_id: int
    nome: str
    titulo: str
    categoria: Optional[str]
    subcategoria: Optional[str]
    ativo_global: bool  # Se o módulo está ativo globalmente
    ativo_tipo_peca: bool  # Se está ativo para este tipo de peça específico


@router.get("/modulos-por-tipo-peca/{tipo_peca}")
async def listar_modulos_por_tipo_peca(
    tipo_peca: str,
    group_id: Optional[int] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todos os módulos de conteúdo com status de ativação para um tipo de peça específico.
    Opcionalmente filtra por grupo.
    """
    # Busca todos os módulos de conteúdo ativos
    query = db.query(PromptModulo).filter(
        PromptModulo.tipo == "conteudo",
        PromptModulo.ativo == True
    )
    if group_id:
        query = query.filter(PromptModulo.group_id == group_id)
    modulos_conteudo = query.order_by(PromptModulo.categoria, PromptModulo.ordem).all()
    
    # Busca associações existentes para este tipo de peça
    associacoes = db.query(ModuloTipoPeca).filter(
        ModuloTipoPeca.tipo_peca == tipo_peca
    ).all()
    
    # Cria mapa de associações
    mapa_associacoes = {a.modulo_id: a.ativo for a in associacoes}
    
    # Monta resposta
    resultado = []
    for modulo in modulos_conteudo:
        # Se não há associação, considera ATIVO por padrão (retrocompatibilidade)
        ativo_tipo_peca = mapa_associacoes.get(modulo.id, True)
        
        resultado.append({
            "modulo_id": modulo.id,
            "nome": modulo.nome,
            "titulo": modulo.titulo,
            "categoria": modulo.categoria,
            "subcategoria": modulo.subcategoria,
            "condicao_ativacao": modulo.condicao_ativacao[:200] + "..." if modulo.condicao_ativacao and len(modulo.condicao_ativacao) > 200 else modulo.condicao_ativacao,
            "ativo_global": modulo.ativo,
            "ativo_tipo_peca": ativo_tipo_peca
        })
    
    return {
        "tipo_peca": tipo_peca,
        "total_modulos": len(resultado),
        "modulos": resultado
    }


@router.post("/configurar-modulos-tipo-peca")
async def configurar_modulos_tipo_peca(
    req: ConfigurarModulosTipoPecaRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Configura quais módulos de conteúdo estão ativos para um tipo de peça específico.
    Permite ativar/desativar módulos em lote para um tipo de peça.
    """
    verificar_permissao_prompts(current_user, "editar")
    
    atualizados = 0
    criados = 0
    
    for item in req.modulos:
        # Verifica se já existe associação
        associacao = db.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.modulo_id == item.modulo_id,
            ModuloTipoPeca.tipo_peca == req.tipo_peca
        ).first()
        
        if associacao:
            # Atualiza
            if associacao.ativo != item.ativo:
                associacao.ativo = item.ativo
                atualizados += 1
        else:
            # Cria nova associação
            nova_assoc = ModuloTipoPeca(
                modulo_id=item.modulo_id,
                tipo_peca=req.tipo_peca,
                ativo=item.ativo
            )
            db.add(nova_assoc)
            criados += 1
    
    db.commit()
    
    return {
        "success": True,
        "tipo_peca": req.tipo_peca,
        "criados": criados,
        "atualizados": atualizados,
        "mensagem": f"Configuração salva: {criados} associações criadas, {atualizados} atualizadas"
    }


@router.post("/ativar-todos-modulos/{tipo_peca}")
async def ativar_todos_modulos(
    tipo_peca: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Ativa todos os módulos de conteúdo para um tipo de peça.
    """
    verificar_permissao_prompts(current_user, "editar")
    
    # Busca todos os módulos de conteúdo ativos
    modulos = db.query(PromptModulo).filter(
        PromptModulo.tipo == "conteudo",
        PromptModulo.ativo == True
    ).all()
    
    for modulo in modulos:
        associacao = db.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.modulo_id == modulo.id,
            ModuloTipoPeca.tipo_peca == tipo_peca
        ).first()
        
        if associacao:
            associacao.ativo = True
        else:
            db.add(ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca,
                ativo=True
            ))
    
    db.commit()
    
    return {
        "success": True,
        "tipo_peca": tipo_peca,
        "modulos_ativados": len(modulos)
    }


@router.post("/desativar-todos-modulos/{tipo_peca}")
async def desativar_todos_modulos(
    tipo_peca: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Desativa todos os módulos de conteúdo para um tipo de peça.
    """
    verificar_permissao_prompts(current_user, "editar")
    
    # Busca todos os módulos de conteúdo ativos
    modulos = db.query(PromptModulo).filter(
        PromptModulo.tipo == "conteudo",
        PromptModulo.ativo == True
    ).all()
    
    for modulo in modulos:
        associacao = db.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.modulo_id == modulo.id,
            ModuloTipoPeca.tipo_peca == tipo_peca
        ).first()
        
        if associacao:
            associacao.ativo = False
        else:
            db.add(ModuloTipoPeca(
                modulo_id=modulo.id,
                tipo_peca=tipo_peca,
                ativo=False
            ))
    
    db.commit()

    return {
        "success": True,
        "tipo_peca": tipo_peca,
        "modulos_desativados": len(modulos)
    }


# ==========================================
# Endpoints: Regras Determinísticas por Tipo de Peça
# ==========================================

class RegraTipoPecaCreate(BaseModel):
    """Schema para criar/atualizar regra determinística específica por tipo de peça."""
    tipo_peca: str
    regra_deterministica: dict
    regra_texto_original: Optional[str] = None
    ativo: bool = True


class RegraTipoPecaResponse(BaseModel):
    """Schema de resposta para regra por tipo de peça."""
    id: int
    modulo_id: int
    tipo_peca: str
    regra_deterministica: dict
    regra_texto_original: Optional[str]
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


@router.get("/{modulo_id}/regras-tipo-peca")
async def listar_regras_tipo_peca(
    modulo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todas as regras determinísticas específicas por tipo de peça de um módulo.

    Retorna:
    - Lista de regras com informações de cada tipo de peça configurado
    - Tipos de peça disponíveis para configuração
    """
    # Verifica se módulo existe
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")

    # Busca regras existentes
    regras = db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.modulo_id == modulo_id
    ).order_by(RegraDeterministicaTipoPeca.tipo_peca).all()

    # Busca tipos de peça disponíveis (módulos do tipo "peca")
    tipos_peca = db.query(PromptModulo).filter(
        PromptModulo.tipo == "peca",
        PromptModulo.ativo == True
    ).order_by(PromptModulo.ordem).all()

    return {
        "modulo_id": modulo_id,
        "modulo_nome": modulo.nome,
        "modulo_titulo": modulo.titulo,
        "regra_global": {
            "primaria": modulo.regra_deterministica,
            "primaria_texto": modulo.regra_texto_original,
            "secundaria": modulo.regra_deterministica_secundaria,
            "secundaria_texto": modulo.regra_secundaria_texto_original,
            "fallback_habilitado": modulo.fallback_habilitado
        },
        "regras_tipo_peca": [
            {
                "id": r.id,
                "tipo_peca": r.tipo_peca,
                "regra_deterministica": r.regra_deterministica,
                "regra_texto_original": r.regra_texto_original,
                "ativo": r.ativo,
                "criado_em": to_iso_utc(r.criado_em),
                "atualizado_em": to_iso_utc(r.atualizado_em)
            }
            for r in regras
        ],
        "tipos_peca_disponiveis": [
            {"nome": tp.nome, "titulo": tp.titulo}
            for tp in tipos_peca
        ],
        # Validação de integridade: verifica variáveis inválidas nas regras
        "validacao_integridade": _validar_integridade_modulo(db, modulo_id)
    }


def _validar_integridade_modulo(db: Session, modulo_id: int) -> Optional[Dict]:
    """Helper para validar integridade de um módulo."""
    try:
        from sistemas.gerador_pecas.services_deterministic import RuleIntegrityValidator
        validator = RuleIntegrityValidator(db)
        validacao = validator.validar_modulo(modulo_id)
        return {
            "valido": validacao["valido"],
            "variaveis_invalidas": validacao["variaveis_invalidas"],
            "resumo": validacao["resumo"]
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Erro ao validar integridade: {e}")
        return None


@router.post("/{modulo_id}/regras-tipo-peca")
async def criar_regra_tipo_peca(
    modulo_id: int,
    regra: RegraTipoPecaCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Cria uma regra determinística específica para um tipo de peça.

    Cada módulo pode ter apenas UMA regra por tipo de peça.
    Se já existir, use PUT para atualizar.
    """
    verificar_permissao_prompts(current_user, "editar")

    # Verifica se módulo existe
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")

    # Verifica se já existe regra para este tipo de peça
    existente = db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.modulo_id == modulo_id,
        RegraDeterministicaTipoPeca.tipo_peca == regra.tipo_peca
    ).first()

    if existente:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe uma regra para o tipo de peça '{regra.tipo_peca}'. Use PUT para atualizar."
        )

    # Normaliza booleanos na regra
    regra_normalizada = normalizar_booleanos_regra(regra.regra_deterministica)

    # Cria nova regra
    nova_regra = RegraDeterministicaTipoPeca(
        modulo_id=modulo_id,
        tipo_peca=regra.tipo_peca,
        regra_deterministica=regra_normalizada,
        regra_texto_original=regra.regra_texto_original,
        ativo=regra.ativo,
        criado_por=current_user.id
    )

    db.add(nova_regra)

    # AUTO-CORREÇÃO: Se criou regra por tipo de peça, força modo_ativacao para 'deterministic'
    if modulo.modo_ativacao != 'deterministic':
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"[AUTO-CORREÇÃO] Módulo {modulo_id}: modo_ativacao alterado para 'deterministic' "
            f"porque regra por tipo de peça '{regra.tipo_peca}' foi criada"
        )
        modulo.modo_ativacao = 'deterministic'

    db.commit()
    db.refresh(nova_regra)

    return {
        "success": True,
        "id": nova_regra.id,
        "modulo_id": modulo_id,
        "tipo_peca": regra.tipo_peca,
        "modo_ativacao_atualizado": modulo.modo_ativacao == 'deterministic',
        "mensagem": f"Regra criada para tipo de peça '{regra.tipo_peca}'"
    }


@router.put("/regras-tipo-peca/{regra_id}")
async def atualizar_regra_tipo_peca(
    regra_id: int,
    dados: RegraTipoPecaCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Atualiza uma regra determinística específica por tipo de peça.
    """
    verificar_permissao_prompts(current_user, "editar")

    # Busca regra existente
    regra = db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.id == regra_id
    ).first()

    if not regra:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    # Normaliza booleanos na regra
    regra_normalizada = normalizar_booleanos_regra(dados.regra_deterministica)

    # Atualiza campos
    regra.regra_deterministica = regra_normalizada
    regra.regra_texto_original = dados.regra_texto_original
    regra.ativo = dados.ativo
    regra.atualizado_por = current_user.id
    regra.atualizado_em = datetime.utcnow()

    # Se mudou o tipo de peça, verifica se já existe outro
    if dados.tipo_peca != regra.tipo_peca:
        existente = db.query(RegraDeterministicaTipoPeca).filter(
            RegraDeterministicaTipoPeca.modulo_id == regra.modulo_id,
            RegraDeterministicaTipoPeca.tipo_peca == dados.tipo_peca,
            RegraDeterministicaTipoPeca.id != regra_id
        ).first()

        if existente:
            raise HTTPException(
                status_code=400,
                detail=f"Já existe uma regra para o tipo de peça '{dados.tipo_peca}'"
            )

        regra.tipo_peca = dados.tipo_peca

    # AUTO-CORREÇÃO: Se atualizou regra por tipo de peça, força modo_ativacao para 'deterministic'
    modulo = db.query(PromptModulo).filter(PromptModulo.id == regra.modulo_id).first()
    if modulo and modulo.modo_ativacao != 'deterministic':
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"[AUTO-CORREÇÃO] Módulo {regra.modulo_id}: modo_ativacao alterado para 'deterministic' "
            f"porque regra por tipo de peça '{regra.tipo_peca}' foi atualizada"
        )
        modulo.modo_ativacao = 'deterministic'

    db.commit()

    return {
        "success": True,
        "id": regra_id,
        "tipo_peca": regra.tipo_peca,
        "mensagem": "Regra atualizada com sucesso"
    }


@router.delete("/regras-tipo-peca/{regra_id}")
async def deletar_regra_tipo_peca(
    regra_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Remove uma regra determinística específica por tipo de peça.
    """
    verificar_permissao_prompts(current_user, "editar")

    # Busca regra existente
    regra = db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.id == regra_id
    ).first()

    if not regra:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    tipo_peca = regra.tipo_peca
    modulo_id = regra.modulo_id

    db.delete(regra)
    db.commit()

    return {
        "success": True,
        "modulo_id": modulo_id,
        "tipo_peca": tipo_peca,
        "mensagem": f"Regra para tipo de peça '{tipo_peca}' removida com sucesso"
    }


@router.patch("/regras-tipo-peca/{regra_id}/toggle")
async def toggle_regra_tipo_peca(
    regra_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Alterna o status ativo/inativo de uma regra por tipo de peça.
    """
    verificar_permissao_prompts(current_user, "editar")

    # Busca regra existente
    regra = db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.id == regra_id
    ).first()

    if not regra:
        raise HTTPException(status_code=404, detail="Regra não encontrada")

    regra.ativo = not regra.ativo
    regra.atualizado_por = current_user.id
    regra.atualizado_em = datetime.utcnow()

    db.commit()

    return {
        "success": True,
        "id": regra_id,
        "ativo": regra.ativo,
        "mensagem": f"Regra {'ativada' if regra.ativo else 'desativada'}"
    }


# ==========================================
# Endpoints: Ordem das Categorias
# ==========================================

class CategoriaOrdemBase(BaseModel):
    nome: str
    ordem: int = 0
    ativo: bool = True


class CategoriaOrdemCreate(CategoriaOrdemBase):
    pass


class CategoriaOrdemUpdate(BaseModel):
    ordem: Optional[int] = None
    ativo: Optional[bool] = None


class CategoriaOrdemResponse(CategoriaOrdemBase):
    id: int
    group_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/grupos/{group_id}/categorias-ordem")
async def listar_categorias_ordem(
    group_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista a ordem configurada das categorias para um grupo.
    Também retorna categorias existentes nos módulos que ainda não têm ordem configurada.
    """
    from admin.models_prompt_groups import CategoriaOrdem

    # Busca categorias com ordem configurada
    categorias_config = db.query(CategoriaOrdem).filter(
        CategoriaOrdem.group_id == group_id
    ).order_by(CategoriaOrdem.ordem).all()

    # Busca categorias existentes nos módulos de conteúdo deste grupo
    categorias_modulos = db.query(PromptModulo.categoria).distinct().filter(
        PromptModulo.group_id == group_id,
        PromptModulo.tipo == "conteudo",
        PromptModulo.ativo == True,
        PromptModulo.categoria.isnot(None),
        PromptModulo.categoria != ""
    ).all()
    categorias_existentes = {c[0] for c in categorias_modulos if c[0]}

    # Mapa de categorias configuradas
    config_map = {c.nome: c for c in categorias_config}

    # Monta resultado
    resultado = []
    ordem_atual = 0

    # Primeiro as configuradas (na ordem)
    for cat in categorias_config:
        resultado.append({
            "id": cat.id,
            "nome": cat.nome,
            "ordem": cat.ordem,
            "ativo": cat.ativo,
            "configurado": True,
            "tem_modulos": cat.nome in categorias_existentes
        })
        if cat.ordem >= ordem_atual:
            ordem_atual = cat.ordem + 1

    # Depois as não configuradas (ordem sugerida)
    for nome in sorted(categorias_existentes):
        if nome not in config_map:
            resultado.append({
                "id": None,
                "nome": nome,
                "ordem": ordem_atual,
                "ativo": True,
                "configurado": False,
                "tem_modulos": True
            })
            ordem_atual += 1

    return {
        "group_id": group_id,
        "categorias": resultado
    }


@router.post("/grupos/{group_id}/categorias-ordem")
async def salvar_categorias_ordem(
    group_id: int,
    categorias: List[CategoriaOrdemCreate],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Salva a ordem das categorias para um grupo.
    Cria ou atualiza as configurações de ordem.
    """
    verificar_permissao_prompts(current_user, "editar")
    from admin.models_prompt_groups import CategoriaOrdem

    # Verifica se o grupo existe
    grupo = db.query(PromptGroup).filter(PromptGroup.id == group_id).first()
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo nao encontrado")

    criados = 0
    atualizados = 0

    for cat_data in categorias:
        # Busca configuração existente
        existente = db.query(CategoriaOrdem).filter(
            CategoriaOrdem.group_id == group_id,
            CategoriaOrdem.nome == cat_data.nome
        ).first()

        if existente:
            existente.ordem = cat_data.ordem
            existente.ativo = cat_data.ativo
            atualizados += 1
        else:
            nova = CategoriaOrdem(
                group_id=group_id,
                nome=cat_data.nome,
                ordem=cat_data.ordem,
                ativo=cat_data.ativo
            )
            db.add(nova)
            criados += 1

    db.commit()

    return {
        "success": True,
        "criados": criados,
        "atualizados": atualizados,
        "message": f"Ordem das categorias salva: {criados} criadas, {atualizados} atualizadas"
    }


@router.delete("/grupos/{group_id}/categorias-ordem/{categoria_nome}")
async def deletar_categoria_ordem(
    group_id: int,
    categoria_nome: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Remove a configuração de ordem de uma categoria."""
    verificar_permissao_prompts(current_user, "excluir")
    from admin.models_prompt_groups import CategoriaOrdem

    config = db.query(CategoriaOrdem).filter(
        CategoriaOrdem.group_id == group_id,
        CategoriaOrdem.nome == categoria_nome
    ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Configuracao de categoria nao encontrada")

    db.delete(config)
    db.commit()

    return {"success": True, "message": f"Configuracao da categoria '{categoria_nome}' removida"}


# ==========================================
# Endpoints: Reordenação de Prompts (Drag & Drop)
# ==========================================

class ReordenarPromptItem(BaseModel):
    """Item para reordenação de prompt"""
    id: int
    ordem: int


class ReordenarPromptsRequest(BaseModel):
    """Request para reordenar múltiplos prompts"""
    prompts: List[ReordenarPromptItem]


@router.post("/prompts/reordenar")
async def reordenar_prompts(
    request: ReordenarPromptsRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Reordena múltiplos prompts de uma vez.
    Usado para drag & drop no frontend.
    """
    verificar_permissao_prompts(current_user, "editar")

    atualizados = []
    for item in request.prompts:
        modulo = db.query(PromptModulo).filter(PromptModulo.id == item.id).first()
        if modulo:
            modulo.ordem = item.ordem
            atualizados.append({"id": modulo.id, "ordem": modulo.ordem})

    db.commit()

    return {
        "success": True,
        "atualizados": len(atualizados),
        "prompts": atualizados
    }


@router.put("/prompts/{prompt_id}/ordem")
async def atualizar_ordem_prompt(
    prompt_id: int,
    nova_ordem: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Atualiza a ordem de um único prompt.
    """
    verificar_permissao_prompts(current_user, "editar")

    modulo = db.query(PromptModulo).filter(PromptModulo.id == prompt_id).first()
    if not modulo:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")

    modulo.ordem = nova_ordem
    db.commit()

    return {
        "success": True,
        "id": modulo.id,
        "ordem": modulo.ordem
    }


class ReordenarCategoriasPromptsRequest(BaseModel):
    """Request para reordenar categorias e seus prompts"""
    group_id: int
    categorias: List[dict]  # [{nome, ordem, prompts: [{id, ordem}]}]


@router.post("/prompts/reordenar-completo")
async def reordenar_prompts_completo(
    request: ReordenarCategoriasPromptsRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Reordena categorias e prompts dentro de cada categoria.
    Atualiza tanto a ordem das categorias quanto dos prompts individuais.

    IMPORTANTE: A subcategoria do prompt NÃO é alterada - ela é um atributo
    fixo do prompt que só pode ser alterado editando o prompt diretamente.
    """
    verificar_permissao_prompts(current_user, "editar")
    from admin.models_prompt_groups import CategoriaOrdem

    categorias_atualizadas = 0
    prompts_atualizados = 0

    for cat_data in request.categorias:
        nome_categoria = cat_data.get("nome")
        ordem_categoria = cat_data.get("ordem", 0)
        prompts = cat_data.get("prompts", [])

        # Atualiza ou cria ordem da categoria
        cat_ordem = db.query(CategoriaOrdem).filter(
            CategoriaOrdem.group_id == request.group_id,
            CategoriaOrdem.nome == nome_categoria
        ).first()

        if cat_ordem:
            cat_ordem.ordem = ordem_categoria
        else:
            cat_ordem = CategoriaOrdem(
                group_id=request.group_id,
                nome=nome_categoria,
                ordem=ordem_categoria,
                ativo=True
            )
            db.add(cat_ordem)
        categorias_atualizadas += 1

        # Atualiza ordem dos prompts dentro da categoria
        for prompt_data in prompts:
            prompt_id = prompt_data.get("id")
            prompt_ordem = prompt_data.get("ordem", 0)

            modulo = db.query(PromptModulo).filter(PromptModulo.id == prompt_id).first()
            if modulo:
                modulo.ordem = prompt_ordem
                prompts_atualizados += 1

    db.commit()

    return {
        "success": True,
        "categorias_atualizadas": categorias_atualizadas,
        "prompts_atualizados": prompts_atualizados
    }


# ==========================================
# Endpoints: Validação de Integridade de Variáveis
# ==========================================

@router.get("/{modulo_id}/validar-integridade")
async def validar_integridade_modulo(
    modulo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Valida integridade entre regras determinísticas e variáveis disponíveis.

    Verifica se todas as variáveis usadas nas regras do módulo:
    - Existem em algum JSON de extração (ExtractionVariable)
    - OU são variáveis de sistema (ProcessVariableDefinition)

    Retorna:
    - valido: bool - se todas as variáveis existem
    - variaveis_invalidas: lista de variáveis que não existem
    - resumo: estatísticas
    """
    from sistemas.gerador_pecas.services_deterministic import RuleIntegrityValidator

    validator = RuleIntegrityValidator(db)
    resultado = validator.validar_modulo(modulo_id)

    return resultado


@router.get("/validar-integridade/todos")
async def validar_integridade_todos_modulos(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Valida integridade de todos os módulos com regras determinísticas.

    Verifica todos os módulos ativos com modo_ativacao='deterministic'.

    Retorna:
    - valido: bool - se todos os módulos estão ok
    - total_modulos_verificados: int
    - total_modulos_invalidos: int
    - modulos_invalidos: lista de módulos com problemas
    """
    from sistemas.gerador_pecas.services_deterministic import RuleIntegrityValidator

    validator = RuleIntegrityValidator(db)
    resultado = validator.validar_todos_modulos()

    return resultado


@router.get("/variaveis-disponiveis")
async def listar_variaveis_disponiveis(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todas as variáveis disponíveis para uso em regras determinísticas.

    Organiza por fonte:
    - extracao: variáveis extraídas de PDFs (ExtractionVariable)
    - sistema: variáveis de processo derivadas do XML (ProcessVariableDefinition)

    Útil para:
    - Debug de regras
    - Interface de criação de regras
    - Validação visual
    """
    from sistemas.gerador_pecas.services_deterministic import RuleIntegrityValidator

    validator = RuleIntegrityValidator(db)
    resultado = validator.obter_variaveis_disponiveis()

    return resultado


# ==============================================================================
# ENDPOINTS PARA REGRA DE OURO: Verificação e correção de modo de ativação
# ==============================================================================

@router.get("/regra-de-ouro/verificar")
async def verificar_modos_ativacao(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Verifica todos os módulos para identificar modos de ativação inconsistentes.

    REGRA DE OURO: Se existe regra determinística, modo_ativacao DEVE ser 'deterministic'.

    Retorna:
    - Lista de módulos com inconsistências
    - Não faz alterações no banco (apenas verificação)
    """
    from sistemas.gerador_pecas.services_deterministic import corrigir_modos_ativacao_inconsistentes

    # Executa sem commit para apenas verificar
    resultado = corrigir_modos_ativacao_inconsistentes(db, commit=False)
    db.rollback()  # Garante que não houve alteração

    return {
        "verificados": resultado["verificados"],
        "inconsistentes": resultado["corrigidos"],
        "detalhes": resultado["detalhes"],
        "mensagem": (
            f"Encontrados {resultado['corrigidos']} módulos com modo de ativação inconsistente. "
            "Use POST /regra-de-ouro/corrigir para aplicar correções."
            if resultado["corrigidos"] > 0
            else "Todos os módulos estão com modo de ativação correto."
        )
    }


@router.post("/regra-de-ouro/corrigir")
async def corrigir_modos_ativacao(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Corrige TODOS os módulos com modo de ativação inconsistente.

    REGRA DE OURO: Se existe regra determinística, modo_ativacao DEVE ser 'deterministic'.

    Esta operação:
    - Verifica todos os módulos
    - Corrige automaticamente os inconsistentes
    - Faz commit das alterações

    IMPORTANTE: Esta correção é segura e pode ser executada múltiplas vezes.
    """
    from sistemas.gerador_pecas.services_deterministic import corrigir_modos_ativacao_inconsistentes

    resultado = corrigir_modos_ativacao_inconsistentes(db, commit=True)

    return {
        "verificados": resultado["verificados"],
        "corrigidos": resultado["corrigidos"],
        "detalhes": resultado["detalhes"],
        "mensagem": (
            f"Corrigidos {resultado['corrigidos']} módulos com sucesso."
            if resultado["corrigidos"] > 0
            else "Nenhuma correção necessária - todos os módulos já estavam corretos."
        )
    }


@router.get("/regra-de-ouro/status/{modulo_id}")
async def verificar_modo_modulo(
    modulo_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Verifica o modo de ativação correto para um módulo específico.

    Retorna:
    - Modo salvo no banco
    - Modo correto segundo a REGRA DE OURO
    - Se há inconsistência
    """
    from sistemas.gerador_pecas.services_deterministic import (
        resolve_activation_mode_from_db,
        tem_regras_deterministicas
    )

    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")

    modo_correto = resolve_activation_mode_from_db(
        db=db,
        modulo_id=modulo_id,
        modo_ativacao_salvo=modulo.modo_ativacao,
        regra_primaria=modulo.regra_deterministica,
        regra_secundaria=modulo.regra_deterministica_secundaria,
        fallback_habilitado=modulo.fallback_habilitado or False
    )

    # Verifica regras por tipo de peça
    regras_tipo_peca = db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.modulo_id == modulo_id,
        RegraDeterministicaTipoPeca.ativo == True
    ).all()

    return {
        "modulo_id": modulo_id,
        "nome": modulo.nome,
        "titulo": modulo.titulo,
        "modo_salvo": modulo.modo_ativacao,
        "modo_correto": modo_correto,
        "inconsistente": modulo.modo_ativacao != modo_correto,
        "tem_regra_primaria": bool(modulo.regra_deterministica),
        "tem_regra_secundaria": bool(modulo.regra_deterministica_secundaria and modulo.fallback_habilitado),
        "regras_tipo_peca": [
            {"tipo_peca": r.tipo_peca, "ativo": r.ativo}
            for r in regras_tipo_peca
        ]
    }

