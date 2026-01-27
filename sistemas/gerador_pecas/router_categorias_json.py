# sistemas/gerador_pecas/router_categorias_json.py
"""
Router para gerenciamento de categorias de formato de resumo JSON.

Permite criar, editar e excluir categorias que definem o formato JSON
de saída dos resumos de documentos baseados no código do documento TJ-MS.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, field_validator
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)

from database.connection import get_db
from auth.models import User
from auth.dependencies import get_current_active_user
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON, CategoriaResumoJSONHistorico
from admin.perf_context import perf_ctx

router = APIRouter(prefix="/categorias-resumo-json", tags=["Categorias Resumo JSON"])


# ==========================================
# Schemas
# ==========================================

class CategoriaResumoJSONBase(BaseModel):
    nome: str
    titulo: str
    descricao: Optional[str] = None
    codigos_documento: List[int] = []
    formato_json: str  # JSON string com o formato esperado
    instrucoes_extracao: Optional[str] = None
    is_residual: bool = False
    ativo: bool = True
    ordem: int = 0
    # Campos de namespace
    namespace_prefix: Optional[str] = None  # Prefixo para variáveis (ex: "peticao", "nat")
    tipos_logicos_peca: Optional[List[str]] = None  # Tipos possíveis (ex: ["petição inicial", "contestação"])
    # Fonte de verdade (classificação de tipo lógico)
    fonte_verdade_tipo: Optional[str] = None  # Tipo lógico fonte de verdade (ex: "petição inicial")
    fonte_verdade_codigo: Optional[str] = None  # Código específico (ex: "9500")
    requer_classificacao: bool = False  # Se deve classificar antes de extrair
    # Fonte especial (alternativa a códigos)
    source_type: str = "code"  # "code" ou "special"
    source_special_type: Optional[str] = None  # Ex: "peticao_inicial"

    @field_validator('formato_json')
    @classmethod
    def validar_formato_json(cls, v):
        """Valida se o formato_json é um JSON válido"""
        try:
            json.loads(v)
            return v
        except json.JSONDecodeError as e:
            raise ValueError(f"formato_json deve ser um JSON válido: {e}")


class CategoriaResumoJSONCreate(CategoriaResumoJSONBase):
    pass


class CategoriaResumoJSONUpdate(BaseModel):
    titulo: Optional[str] = None
    descricao: Optional[str] = None
    codigos_documento: Optional[List[int]] = None
    formato_json: Optional[str] = None
    instrucoes_extracao: Optional[str] = None
    is_residual: Optional[bool] = None
    ativo: Optional[bool] = None
    ordem: Optional[int] = None
    # Campos de namespace
    namespace_prefix: Optional[str] = None
    tipos_logicos_peca: Optional[List[str]] = None
    # Fonte de verdade
    fonte_verdade_tipo: Optional[str] = None
    fonte_verdade_codigo: Optional[str] = None
    requer_classificacao: Optional[bool] = None
    # Fonte especial
    source_type: Optional[str] = None
    source_special_type: Optional[str] = None
    # Origem do JSON
    json_gerado_por_ia: Optional[bool] = None
    motivo: str  # Obrigatório para rastrear alterações
    # Sincronização de variáveis (SEGURANÇA: desativado por padrão)
    sincronizar_variaveis: bool = False  # Se True, desativa variáveis órfãs

    @field_validator('formato_json')
    @classmethod
    def validar_formato_json(cls, v):
        """Valida se o formato_json é um JSON válido (se fornecido)"""
        if v is None:
            return v
        try:
            json.loads(v)
            return v
        except json.JSONDecodeError as e:
            raise ValueError(f"formato_json deve ser um JSON válido: {e}")


class CategoriaResumoJSONResponse(BaseModel):
    id: int
    nome: str
    titulo: str
    descricao: Optional[str]
    codigos_documento: List[int]
    formato_json: str
    instrucoes_extracao: Optional[str]
    is_residual: bool
    ativo: bool
    ordem: int
    # Campos de namespace
    namespace_prefix: Optional[str] = None
    namespace: Optional[str] = None  # Namespace efetivo (calculado)
    tipos_logicos_peca: Optional[List[str]] = None
    # Fonte de verdade
    fonte_verdade_tipo: Optional[str] = None
    fonte_verdade_codigo: Optional[str] = None
    requer_classificacao: bool = False
    tem_fonte_verdade: bool = False  # Propriedade calculada
    # Fonte especial
    source_type: str = "code"
    source_special_type: Optional[str] = None
    usa_fonte_especial: bool = False  # Propriedade calculada
    # Origem do JSON
    json_gerado_por_ia: bool = False  # Se JSON foi gerado por IA
    json_gerado_em: Optional[datetime] = None
    json_gerado_por: Optional[int] = None
    # Auditoria
    criado_por: Optional[int]
    criado_em: datetime
    atualizado_por: Optional[int]
    atualizado_em: Optional[datetime]

    class Config:
        from_attributes = True


class CategoriaHistoricoResponse(BaseModel):
    id: int
    categoria_id: int
    versao: int
    codigos_documento: Optional[List[int]]
    formato_json: str
    instrucoes_extracao: Optional[str]
    alterado_por: Optional[int]
    alterado_em: datetime
    motivo: Optional[str]
    
    class Config:
        from_attributes = True


# ==========================================
# Funções auxiliares
# ==========================================

def verificar_permissao(user: User):
    """Verifica se usuário tem permissão para gerenciar categorias"""
    if not user.tem_permissao("editar_prompts"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para gerenciar categorias de resumo JSON"
        )


def buscar_categoria_por_codigo(db: Session, codigo_documento: int) -> Optional[CategoriaResumoJSON]:
    """
    Busca a categoria ativa que contém o código de documento especificado.
    Se não encontrar, retorna a categoria residual.
    """
    # Busca categoria específica para o código
    categorias = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.ativo == True,
        CategoriaResumoJSON.is_residual == False
    ).all()
    
    for cat in categorias:
        if codigo_documento in (cat.codigos_documento or []):
            return cat
    
    # Se não achou, retorna a residual
    residual = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.ativo == True,
        CategoriaResumoJSON.is_residual == True
    ).first()
    
    return residual


def obter_todas_categorias_ativas(db: Session) -> List[CategoriaResumoJSON]:
    """Retorna todas as categorias ativas ordenadas"""
    return db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.ativo == True
    ).order_by(CategoriaResumoJSON.ordem).all()


# ==========================================
# Endpoints de Listagem
# ==========================================

@router.get("", response_model=List[CategoriaResumoJSONResponse])
async def listar_categorias(
    apenas_ativos: bool = True,
    apenas_com_variaveis: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todas as categorias de formato de resumo JSON"""
    perf_ctx.set_action("listar_categorias")
    query = db.query(CategoriaResumoJSON)

    if apenas_ativos:
        query = query.filter(CategoriaResumoJSON.ativo == True)

    # Filtra apenas categorias que possuem variáveis de extração
    if apenas_com_variaveis:
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable
        subquery = db.query(ExtractionVariable.categoria_id).filter(
            ExtractionVariable.categoria_id.isnot(None)
        ).distinct().subquery()
        query = query.filter(CategoriaResumoJSON.id.in_(subquery))

    categorias = query.order_by(CategoriaResumoJSON.ordem, CategoriaResumoJSON.nome).all()
    return categorias


@router.get("/codigos-disponiveis")
async def listar_codigos_disponiveis(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todos os códigos de documento do TJ-MS e em qual categoria estão.
    Útil para ver quais códigos já estão atribuídos.
    """
    from sistemas.gerador_pecas.agente_tjms import CATEGORIAS_MAP
    
    # Busca todas as categorias ativas
    categorias = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.ativo == True
    ).all()
    
    # Monta mapa de código -> categoria
    codigo_para_categoria = {}
    for cat in categorias:
        for codigo in (cat.codigos_documento or []):
            codigo_para_categoria[codigo] = {
                "categoria_id": cat.id,
                "categoria_nome": cat.nome,
                "categoria_titulo": cat.titulo
            }
    
    # Retorna lista de códigos conhecidos com suas categorias
    resultado = []
    for codigo_str, descricao in CATEGORIAS_MAP.items():
        codigo = int(codigo_str)
        info = {
            "codigo": codigo,
            "descricao": descricao,
            "categoria": codigo_para_categoria.get(codigo)
        }
        resultado.append(info)
    
    # Adiciona códigos que estão em categorias mas não no mapa
    codigos_no_mapa = set(int(c) for c in CATEGORIAS_MAP.keys())
    for cat in categorias:
        for codigo in (cat.codigos_documento or []):
            if codigo not in codigos_no_mapa:
                resultado.append({
                    "codigo": codigo,
                    "descricao": f"Código {codigo} (não mapeado)",
                    "categoria": codigo_para_categoria.get(codigo)
                })
    
    return sorted(resultado, key=lambda x: x["codigo"])


@router.get("/fontes-especiais")
async def listar_fontes_especiais(
    current_user: User = Depends(get_current_active_user)
):
    """
    Lista as fontes especiais disponíveis para categorias.

    Fontes especiais permitem identificar documentos por regras lógicas
    em vez de códigos de documento (ex: Petição Inicial = primeiro doc 9500/500).
    """
    from sistemas.gerador_pecas.services_source_resolver import get_available_special_sources

    return get_available_special_sources()


# ==========================================
# Endpoints CRUD
# ==========================================

@router.get("/{categoria_id}", response_model=CategoriaResumoJSONResponse)
async def obter_categoria(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém uma categoria específica"""
    perf_ctx.set_action("obter_categoria")

    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == categoria_id
    ).first()

    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    return categoria


@router.post("", response_model=CategoriaResumoJSONResponse, status_code=status.HTTP_201_CREATED)
async def criar_categoria(
    categoria_data: CategoriaResumoJSONCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cria uma nova categoria de formato de resumo JSON"""
    perf_ctx.set_action("criar_categoria")
    verificar_permissao(current_user)
    
    # Verifica se já existe com mesmo nome
    existente = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.nome == categoria_data.nome
    ).first()
    
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Já existe uma categoria com o nome '{categoria_data.nome}'"
        )
    
    # Se está criando como residual, desativa outras residuais
    if categoria_data.is_residual:
        db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.is_residual == True
        ).update({"is_residual": False, "atualizado_por": current_user.id})
    
    # Verifica se algum código já está em outra categoria
    if categoria_data.codigos_documento:
        categorias_existentes = db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.ativo == True
        ).all()
        
        for cat in categorias_existentes:
            codigos_conflito = set(categoria_data.codigos_documento) & set(cat.codigos_documento or [])
            if codigos_conflito:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Os códigos {list(codigos_conflito)} já pertencem à categoria '{cat.nome}'"
                )
    
    categoria = CategoriaResumoJSON(
        **categoria_data.model_dump(),
        criado_por=current_user.id,
        atualizado_por=current_user.id
    )
    
    db.add(categoria)
    db.commit()
    db.refresh(categoria)
    
    return categoria


@router.put("/{categoria_id}", response_model=CategoriaResumoJSONResponse)
async def atualizar_categoria(
    categoria_id: int,
    categoria_data: CategoriaResumoJSONUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Atualiza uma categoria (cria registro no histórico)"""
    perf_ctx.set_action("atualizar_categoria")
    verificar_permissao(current_user)
    
    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == categoria_id
    ).first()
    
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    
    # Calcula versão para histórico
    ultimo_historico = db.query(CategoriaResumoJSONHistorico).filter(
        CategoriaResumoJSONHistorico.categoria_id == categoria_id
    ).order_by(CategoriaResumoJSONHistorico.versao.desc()).first()
    
    versao = (ultimo_historico.versao + 1) if ultimo_historico else 1
    
    # Salva versão atual no histórico
    historico = CategoriaResumoJSONHistorico(
        categoria_id=categoria.id,
        versao=versao,
        codigos_documento=categoria.codigos_documento,
        formato_json=categoria.formato_json,
        instrucoes_extracao=categoria.instrucoes_extracao,
        alterado_por=current_user.id,
        motivo=categoria_data.motivo
    )
    db.add(historico)
    
    # Se está marcando como residual, desmarca outras
    if categoria_data.is_residual:
        db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.is_residual == True,
            CategoriaResumoJSON.id != categoria_id
        ).update({"is_residual": False, "atualizado_por": current_user.id})
    
    # Verifica conflitos de códigos
    if categoria_data.codigos_documento is not None:
        categorias_existentes = db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.ativo == True,
            CategoriaResumoJSON.id != categoria_id
        ).all()
        
        for cat in categorias_existentes:
            codigos_conflito = set(categoria_data.codigos_documento) & set(cat.codigos_documento or [])
            if codigos_conflito:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Os códigos {list(codigos_conflito)} já pertencem à categoria '{cat.nome}'"
                )
    
    # Atualiza categoria
    update_data = categoria_data.model_dump(exclude_unset=True, exclude={"motivo"})
    for field, value in update_data.items():
        setattr(categoria, field, value)
    
    # Se marcou como gerado por IA, salva timestamp
    if categoria_data.json_gerado_por_ia:
        categoria.json_gerado_em = datetime.utcnow()
        categoria.json_gerado_por = current_user.id

    categoria.atualizado_por = current_user.id
    categoria.atualizado_em = datetime.utcnow()

    # Sincroniza variáveis APENAS se explicitamente solicitado (flag de segurança)
    # IMPORTANTE: Por padrão NÃO desativa variáveis ao atualizar JSON
    # Use "Aplicar JSON nas Perguntas" para sincronização completa
    if categoria_data.formato_json is not None and categoria_data.sincronizar_variaveis:
        try:
            import json
            from .models_extraction import ExtractionVariable, ExtractionQuestion

            schema = json.loads(categoria_data.formato_json)

            # Extrai slugs do novo JSON
            slugs_no_json = set()
            for slug, campo_info in schema.items():
                if isinstance(campo_info, dict):
                    slugs_no_json.add(slug)

            # Busca todas as variáveis ativas da categoria
            variaveis_categoria = db.query(ExtractionVariable).filter(
                ExtractionVariable.categoria_id == categoria_id,
                ExtractionVariable.ativo == True
            ).all()

            # Desativa variáveis que não estão mais no JSON (órfãs)
            # SEGURANÇA: Só executa se sincronizar_variaveis=True
            for variavel in variaveis_categoria:
                if variavel.slug not in slugs_no_json:
                    variavel.ativo = False
                    variavel.atualizado_em = datetime.utcnow()
                    logger.info(f"Variável órfã desativada: slug={variavel.slug} (removida do JSON)")

                    # Desativa a pergunta associada, se existir
                    if variavel.source_question_id:
                        pergunta = db.query(ExtractionQuestion).filter(
                            ExtractionQuestion.id == variavel.source_question_id
                        ).first()
                        if pergunta and pergunta.ativo:
                            pergunta.ativo = False
                            pergunta.atualizado_por = current_user.id
                            pergunta.atualizado_em = datetime.utcnow()
                            logger.info(f"Pergunta órfã desativada: id={pergunta.id}")

            # Atualiza variáveis existentes no JSON
            for slug, campo_info in schema.items():
                if isinstance(campo_info, dict):
                    variavel = db.query(ExtractionVariable).filter(
                        ExtractionVariable.slug == slug,
                        ExtractionVariable.categoria_id == categoria_id
                    ).first()

                    if variavel:
                        tipo_json = campo_info.get("type")
                        descricao_json = campo_info.get("description")

                        if tipo_json and variavel.tipo != tipo_json:
                            variavel.tipo = tipo_json
                            variavel.atualizado_em = datetime.utcnow()

                        if descricao_json and variavel.descricao != descricao_json:
                            variavel.descricao = descricao_json
                            variavel.atualizado_em = datetime.utcnow()

        except Exception as e:
            logger.warning(f"Não foi possível sincronizar variáveis com JSON: {e}")

    db.commit()
    db.refresh(categoria)

    return categoria


@router.delete("/{categoria_id}")
async def desativar_categoria(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Desativa uma categoria (soft delete)"""
    verificar_permissao(current_user)
    
    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == categoria_id
    ).first()
    
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    
    if categoria.is_residual:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não é possível desativar a categoria residual. Defina outra como residual primeiro."
        )
    
    categoria.ativo = False
    categoria.atualizado_por = current_user.id
    db.commit()
    
    return {"message": f"Categoria '{categoria.titulo}' desativada com sucesso"}


# ==========================================
# Endpoints de Histórico
# ==========================================

@router.get("/{categoria_id}/historico", response_model=List[CategoriaHistoricoResponse])
async def listar_historico(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista histórico de versões de uma categoria"""
    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == categoria_id
    ).first()
    
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    
    historico = db.query(CategoriaResumoJSONHistorico).filter(
        CategoriaResumoJSONHistorico.categoria_id == categoria_id
    ).order_by(CategoriaResumoJSONHistorico.versao.desc()).all()
    
    return historico


# ==========================================
# Endpoint para testar formato
# ==========================================

@router.post("/testar-formato")
async def testar_formato(
    formato_json: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    Testa se um formato JSON é válido e retorna sua estrutura parsed.
    Útil para validar o formato antes de salvar.
    """
    try:
        parsed = json.loads(formato_json)
        return {
            "valido": True,
            "estrutura": parsed,
            "campos": list(parsed.keys()) if isinstance(parsed, dict) else None
        }
    except json.JSONDecodeError as e:
        return {
            "valido": False,
            "erro": str(e),
            "posicao": e.pos
        }


# ==========================================
# Endpoints para Info de Perguntas/Variáveis
# ==========================================

@router.get("/{categoria_id}/info-extracao")
async def info_extracao(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retorna informações sobre as perguntas e variáveis de uma categoria.

    Inclui:
    - Número de perguntas configuradas
    - Se JSON foi gerado por IA
    - Número de variáveis criadas
    """
    perf_ctx.set_action("info_extracao_categoria")
    categoria = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.id == categoria_id
    ).first()
    
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    
    from .models_extraction import ExtractionQuestion, ExtractionVariable
    
    # Conta perguntas ativas
    perguntas_count = db.query(ExtractionQuestion).filter(
        ExtractionQuestion.categoria_id == categoria_id,
        ExtractionQuestion.ativo == True
    ).count()
    
    # Conta variáveis
    variaveis_count = db.query(ExtractionVariable).filter(
        ExtractionVariable.categoria_id == categoria_id,
        ExtractionVariable.ativo == True
    ).count()
    
    return {
        "perguntas_count": perguntas_count,
        "variaveis_count": variaveis_count,
        "json_gerado_por_ia": categoria.json_gerado_por_ia,
        "json_gerado_em": categoria.json_gerado_em.isoformat() if categoria.json_gerado_em else None
    }


# ==========================================
# Endpoints para Blacklist de Códigos
# ==========================================

class CodigosIgnoradosUpdate(BaseModel):
    """Schema para atualizar a lista de códigos ignorados"""
    codigos: List[int]


@router.get("/config/codigos-ignorados")
async def get_codigos_ignorados(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retorna a lista de códigos de documento ignorados na extração JSON.

    Documentos com estes códigos não terão resumo JSON extraído.
    """
    from admin.models import ConfiguracaoIA

    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "gerador_pecas",
        ConfiguracaoIA.chave == "codigos_ignorar_extracao_json"
    ).first()

    codigos = []
    if config and config.valor:
        try:
            codigos = json.loads(config.valor)
            if not isinstance(codigos, list):
                codigos = []
        except json.JSONDecodeError:
            codigos = []

    return {
        "codigos": codigos,
        "descricao": config.descricao if config else "Lista de códigos de documento TJ-MS a ignorar na extração de JSON"
    }


@router.put("/config/codigos-ignorados")
async def update_codigos_ignorados(
    dados: CodigosIgnoradosUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Atualiza a lista de códigos de documento ignorados na extração JSON.

    Args:
        dados: Lista de códigos inteiros a ignorar
    """
    from admin.models import ConfiguracaoIA

    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "gerador_pecas",
        ConfiguracaoIA.chave == "codigos_ignorar_extracao_json"
    ).first()

    # Remove duplicatas e ordena
    codigos_unicos = sorted(set(dados.codigos))
    valor_json = json.dumps(codigos_unicos)

    if config:
        config.valor = valor_json
    else:
        # Cria configuração se não existir
        config = ConfiguracaoIA(
            sistema="gerador_pecas",
            chave="codigos_ignorar_extracao_json",
            valor=valor_json,
            tipo_valor="json",
            descricao="Lista de códigos de documento TJ-MS a ignorar na extração de JSON (ex: [9508, 60, 61])"
        )
        db.add(config)

    db.commit()

    logger.info(f"[BLACKLIST] Códigos ignorados atualizados por {current_user.username}: {codigos_unicos}")

    return {
        "success": True,
        "codigos": codigos_unicos,
        "mensagem": f"{len(codigos_unicos)} código(s) configurado(s) para ignorar"
    }


# ==========================================
# Endpoints de Consistencia de Slugs
# ==========================================

class ConsistenciaCategoriaSlugsResponse(BaseModel):
    """Schema de resposta para verificacao de consistencia de slugs da categoria"""
    consistente: bool
    categoria_id: int
    categoria_nome: str
    total_slugs_json: int = 0
    total_variaveis_ativas: int = 0
    slugs_orfaos_json: List[str] = []
    slugs_orfaos_variaveis: List[str] = []
    mensagem: str = ""
    erro: Optional[str] = None


@router.get("/{categoria_id}/consistencia-slugs", response_model=ConsistenciaCategoriaSlugsResponse)
async def verificar_consistencia_slugs(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Verifica consistencia entre o JSON da categoria e as variaveis de extracao.

    Este endpoint DEVE ser usado pelo frontend para verificar se o JSON esta
    realmente atualizado antes de mostrar "Atualizado" ao usuario.

    Retorna:
    - consistente: True se nao ha divergencias
    - slugs_orfaos_json: slugs no JSON que nao tem variavel correspondente
    - slugs_orfaos_variaveis: variaveis ativas que nao estao no JSON

    IMPORTANTE: Se consistente=False, o sistema NAO deve dizer que esta "Atualizado".
    """
    from .services_slug_rename import SlugConsistencyChecker

    checker = SlugConsistencyChecker(db)
    resultado = checker.verificar_categoria(categoria_id)

    if resultado.get("erro"):
        raise HTTPException(status_code=400, detail=resultado["erro"])

    return ConsistenciaCategoriaSlugsResponse(
        consistente=resultado["consistente"],
        categoria_id=resultado["categoria_id"],
        categoria_nome=resultado["categoria_nome"],
        total_slugs_json=resultado["total_slugs_json"],
        total_variaveis_ativas=resultado["total_variaveis_ativas"],
        slugs_orfaos_json=resultado["slugs_orfaos_json"],
        slugs_orfaos_variaveis=resultado["slugs_orfaos_variaveis"],
        mensagem=resultado["mensagem"]
    )


class RepararConsistenciaResponse(BaseModel):
    """Schema de resposta para reparo de consistencia"""
    success: bool
    categoria_id: int
    correcoes_aplicadas: int = 0
    correcoes: List[str] = []
    erro: Optional[str] = None


@router.post("/{categoria_id}/reparar-consistencia", response_model=RepararConsistenciaResponse)
async def reparar_consistencia_slugs(
    categoria_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Repara inconsistencias entre o JSON da categoria e as variaveis.

    Este endpoint corrige automaticamente:
    - Remove do JSON slugs que nao tem variavel correspondente
    - Adiciona ao JSON variaveis ativas que estao faltando

    ATENCAO: Esta operacao modifica o JSON da categoria.
    Recomenda-se verificar consistencia antes com GET /{categoria_id}/consistencia-slugs.
    """
    verificar_permissao(current_user)

    from .services_slug_rename import SlugConsistencyChecker

    checker = SlugConsistencyChecker(db)
    resultado = checker.reparar_categoria(categoria_id, user_id=current_user.id)

    if not resultado.get("success"):
        raise HTTPException(status_code=400, detail=resultado.get("erro", "Erro ao reparar"))

    if resultado.get("correcoes_aplicadas", 0) > 0:
        db.commit()
        logger.info(
            f"[CONSISTENCIA] Categoria {categoria_id} reparada por {current_user.username}: "
            f"{resultado['correcoes_aplicadas']} correcoes"
        )
    else:
        logger.info(f"[CONSISTENCIA] Categoria {categoria_id} ja estava consistente")

    return RepararConsistenciaResponse(
        success=True,
        categoria_id=categoria_id,
        correcoes_aplicadas=resultado.get("correcoes_aplicadas", 0),
        correcoes=resultado.get("correcoes", [])
    )


class RepararTodasResponse(BaseModel):
    """Schema de resposta para reparo de todas as categorias"""
    success: bool
    categorias_verificadas: int = 0
    categorias_reparadas: int = 0
    total_correcoes: int = 0
    detalhes: List[Dict[str, Any]] = []


@router.post("/reparar-todas-consistencias", response_model=RepararTodasResponse)
async def reparar_todas_consistencias(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Repara inconsistencias de TODAS as categorias ativas.

    Util para migracao/limpeza de dados legados.
    Apenas administradores podem executar esta operacao.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores podem reparar todas as categorias"
        )

    from .services_slug_rename import SlugConsistencyChecker

    categorias = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.ativo == True
    ).all()

    checker = SlugConsistencyChecker(db)
    detalhes = []
    categorias_reparadas = 0
    total_correcoes = 0

    for categoria in categorias:
        resultado = checker.reparar_categoria(categoria.id, user_id=current_user.id)

        if resultado.get("correcoes_aplicadas", 0) > 0:
            categorias_reparadas += 1
            total_correcoes += resultado["correcoes_aplicadas"]
            detalhes.append({
                "categoria_id": categoria.id,
                "categoria_nome": categoria.nome,
                "correcoes": resultado.get("correcoes", [])
            })

    if total_correcoes > 0:
        db.commit()
        logger.info(
            f"[CONSISTENCIA] Reparo em massa por {current_user.username}: "
            f"{categorias_reparadas} categorias, {total_correcoes} correcoes"
        )

    return RepararTodasResponse(
        success=True,
        categorias_verificadas=len(categorias),
        categorias_reparadas=categorias_reparadas,
        total_correcoes=total_correcoes,
        detalhes=detalhes
    )
