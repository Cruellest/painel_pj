# sistemas/gerador_pecas/router_extraction.py
"""
Router para funcionalidades de extração baseada em IA.

Endpoints para:
- Perguntas de extração (modo IA)
- Modelos de extração (gerados por IA ou manuais)
- Variáveis normalizadas do sistema
- Uso de variáveis em prompts
"""

import logging
from typing import List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel, Field

from database.connection import get_db
from auth.dependencies import get_current_active_user
from auth.models import User

from .models_extraction import (
    ExtractionQuestion, ExtractionModel, ExtractionVariable,
    PromptVariableUsage, PromptActivationLog, ExtractionQuestionType,
    DependencyOperator
)
from .models_resumo_json import CategoriaResumoJSON
from .services_extraction import ExtractionSchemaGenerator
from .services_dependencies import (
    DependencyInferenceService, DependencyEvaluator, DependencyGraphBuilder
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# SCHEMAS PYDANTIC
# ============================================================================

# --- Perguntas de Extração ---

class ExtractionQuestionBase(BaseModel):
    """Schema base para perguntas de extração"""
    pergunta: str = Field(..., description="Pergunta em linguagem natural")
    nome_variavel_sugerido: Optional[str] = Field(None, description="Nome de variável sugerido (opcional)")
    tipo_sugerido: Optional[str] = Field(None, description="Tipo de dado sugerido (opcional)")
    opcoes_sugeridas: Optional[List[str]] = Field(None, description="Opções sugeridas para múltipla escolha (opcional)")
    descricao: Optional[str] = Field(None, description="Descrição adicional (opcional)")
    # Dependências condicionais
    depends_on_variable: Optional[str] = Field(None, description="Slug da variável da qual esta pergunta depende")
    dependency_operator: Optional[str] = Field(None, description="Operador da dependência (equals, not_equals, exists, etc.)")
    dependency_value: Optional[Any] = Field(None, description="Valor da condição de dependência")
    dependency_inferred: bool = Field(False, description="Se a dependência foi inferida por IA")
    ativo: bool = Field(True, description="Se a pergunta está ativa")
    ordem: int = Field(0, description="Ordem de exibição")


class ExtractionQuestionCreate(ExtractionQuestionBase):
    """Schema para criação de pergunta"""
    categoria_id: int = Field(..., description="ID da categoria de documento")


class ExtractionQuestionUpdate(BaseModel):
    """Schema para atualização de pergunta"""
    pergunta: Optional[str] = None
    nome_variavel_sugerido: Optional[str] = None
    tipo_sugerido: Optional[str] = None
    opcoes_sugeridas: Optional[List[str]] = None
    descricao: Optional[str] = None
    # Dependências condicionais
    depends_on_variable: Optional[str] = None
    dependency_operator: Optional[str] = None
    dependency_value: Optional[Any] = None
    dependency_inferred: Optional[bool] = None
    ativo: Optional[bool] = None
    ordem: Optional[int] = None


class ExtractionQuestionResponse(ExtractionQuestionBase):
    """Schema de resposta para pergunta"""
    id: int
    categoria_id: int
    categoria_nome: Optional[str] = None
    criado_por: Optional[int] = None
    criado_em: datetime
    atualizado_em: datetime

    class Config:
        from_attributes = True


# --- Modelos de Extração ---

class ExtractionModelBase(BaseModel):
    """Schema base para modelo de extração"""
    modo: str = Field("manual", description="Modo: ai_generated ou manual")
    schema_json: dict = Field(..., description="Schema JSON de extração")
    mapeamento_variaveis: Optional[dict] = Field(None, description="Mapeamento de perguntas para variáveis")


class ExtractionModelCreate(ExtractionModelBase):
    """Schema para criação de modelo"""
    categoria_id: int = Field(..., description="ID da categoria de documento")


class ExtractionModelResponse(ExtractionModelBase):
    """Schema de resposta para modelo"""
    id: int
    categoria_id: int
    categoria_nome: Optional[str] = None
    versao: int
    ativo: bool
    criado_por: Optional[int] = None
    criado_em: datetime

    class Config:
        from_attributes = True


class GenerateSchemaRequest(BaseModel):
    """Schema para requisição de geração de schema"""
    categoria_id: int = Field(..., description="ID da categoria de documento")


class GenerateSchemaResponse(BaseModel):
    """Schema de resposta para geração de schema"""
    success: bool
    schema_json: Optional[dict] = None
    mapeamento_variaveis: Optional[dict] = None
    variaveis_criadas: Optional[List[dict]] = None
    erro: Optional[str] = None


# --- Sincronização de JSON (sem IA) ---

class SyncJsonResponse(BaseModel):
    """Schema de resposta para sincronização de JSON sem IA"""
    success: bool
    schema_json: Optional[dict] = None
    variaveis_adicionadas: int = 0
    variaveis_adicionadas_lista: Optional[List[str]] = None
    perguntas_incompletas: Optional[List[dict]] = None
    mensagem: Optional[str] = None
    erro: Optional[str] = None


# --- Criação em Lote de Perguntas (com análise de dependências por IA) ---

class BulkQuestionInput(BaseModel):
    """Uma pergunta no formato de entrada para criação em lote"""
    pergunta: str = Field(..., description="Texto da pergunta em linguagem natural")
    nome_variavel_sugerido: Optional[str] = Field(None, description="Nome sugerido para a variável")
    tipo_sugerido: Optional[str] = Field(None, description="Tipo sugerido (text, number, boolean, etc)")
    opcoes_sugeridas: Optional[List[str]] = Field(None, description="Opções para tipo choice")


class BulkQuestionsCreate(BaseModel):
    """Schema para criação em lote de perguntas com análise de dependências"""
    categoria_id: int = Field(..., description="ID da categoria de documento")
    perguntas: List[BulkQuestionInput] = Field(..., min_length=1, description="Lista de perguntas a criar")
    analisar_dependencias: bool = Field(True, description="Se deve usar IA para analisar dependências entre perguntas")


class BulkQuestionResult(BaseModel):
    """Resultado da criação de uma pergunta no lote"""
    index: int
    pergunta_texto: str
    id: Optional[int] = None
    slug_sugerido: Optional[str] = None
    depends_on_variable: Optional[str] = None
    dependency_operator: Optional[str] = None
    dependency_value: Optional[Any] = None
    erro: Optional[str] = None


class BulkQuestionsResponse(BaseModel):
    """Resposta da criação em lote de perguntas"""
    success: bool
    total_enviadas: int
    total_criadas: int
    total_com_dependencias: int
    perguntas: List[BulkQuestionResult]
    grafo_dependencias: Optional[dict] = None
    erro: Optional[str] = None


# --- Variáveis Normalizadas ---

class ExtractionVariableBase(BaseModel):
    """Schema base para variável de extração"""
    slug: str = Field(..., description="Identificador técnico único")
    label: str = Field(..., description="Nome de exibição")
    descricao: Optional[str] = Field(None, description="Descrição da variável")
    tipo: str = Field(..., description="Tipo de dado")
    opcoes: Optional[List[str]] = Field(None, description="Opções para tipo choice/list")
    # Fonte de verdade individual (override do grupo)
    fonte_verdade_codigo: Optional[str] = Field(None, description="Código específico de documento (ex: 9500)")
    fonte_verdade_tipo: Optional[str] = Field(None, description="Tipo de documento fonte de verdade para esta variável")
    fonte_verdade_override: bool = Field(False, description="Se usa fonte de verdade específica")


class ExtractionVariableCreate(ExtractionVariableBase):
    """Schema para criação de variável"""
    categoria_id: Optional[int] = Field(None, description="ID da categoria de documento")


class ExtractionVariableUpdate(BaseModel):
    """Schema para atualização de variável"""
    label: Optional[str] = None
    descricao: Optional[str] = None
    tipo: Optional[str] = None
    opcoes: Optional[List[str]] = None
    fonte_verdade_codigo: Optional[str] = None
    fonte_verdade_tipo: Optional[str] = None
    fonte_verdade_override: Optional[bool] = None
    ativo: Optional[bool] = None


class ExtractionVariableResponse(ExtractionVariableBase):
    """Schema de resposta para variável"""
    id: int
    categoria_id: Optional[int] = None
    categoria_nome: Optional[str] = None
    source_question_id: Optional[int] = None
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
    uso_count: int = Field(0, description="Quantidade de prompts que usam esta variável")
    # Campos de dependência para visualização
    is_conditional: bool = Field(False, description="Se a variável é condicional")
    depends_on_variable: Optional[str] = Field(None, description="Slug da variável da qual depende")
    depth: int = Field(0, description="Profundidade na árvore de dependências (para recuo)")
    ordem: int = Field(0, description="Ordem da pergunta de origem")
    em_uso_json: bool = Field(False, description="Se está em uso no JSON da categoria")

    class Config:
        from_attributes = True


class VariableUsageResponse(BaseModel):
    """Schema de resposta para uso de variável em prompt"""
    prompt_id: int
    prompt_nome: str
    prompt_titulo: str
    modo_ativacao: Optional[str] = None
    criado_em: datetime

    class Config:
        from_attributes = True


class VariableDetailResponse(ExtractionVariableResponse):
    """Schema de resposta detalhada para variável com usos"""
    prompt_usages: List[VariableUsageResponse] = Field([], description="Lista de prompts que usam esta variável")


# ============================================================================
# ENDPOINTS - PERGUNTAS DE EXTRAÇÃO
# ============================================================================


def _slugify(texto: str) -> str:
    """
    Converte texto em slug válido para variável.

    Exemplo: "O parecer analisou medicamento?" -> "o_parecer_analisou_medicamento"
    """
    import re
    import unicodedata

    # Remove acentos
    texto = unicodedata.normalize('NFKD', texto)
    texto = texto.encode('ascii', 'ignore').decode('ascii')

    # Converte para minúsculas
    texto = texto.lower()

    # Remove caracteres especiais, mantém apenas letras, números e espaços
    texto = re.sub(r'[^a-z0-9\s]', '', texto)

    # Substitui espaços por underscores
    texto = re.sub(r'\s+', '_', texto.strip())

    # Remove underscores múltiplos
    texto = re.sub(r'_+', '_', texto)

    # Limita tamanho
    return texto[:100]


def _get_unique_slug(db: Session, base_slug: str, exclude_question_id: int = None) -> str:
    """
    Garante que o slug seja único, adicionando sufixo se necessário.

    Args:
        db: Sessão do banco
        base_slug: Slug base
        exclude_question_id: ID da pergunta a excluir da verificação (para updates)

    Returns:
        Slug único
    """
    slug = base_slug
    contador = 1

    while True:
        query = db.query(ExtractionVariable).filter(ExtractionVariable.slug == slug)

        # Se for update, exclui a variável da própria pergunta
        if exclude_question_id:
            query = query.filter(
                or_(
                    ExtractionVariable.source_question_id != exclude_question_id,
                    ExtractionVariable.source_question_id.is_(None)
                )
            )

        existente = query.first()

        if not existente:
            return slug

        contador += 1
        slug = f"{base_slug}_{contador}"


def ensure_variable_for_question(
    db: Session,
    pergunta: ExtractionQuestion,
    categoria: "CategoriaResumoJSON"
) -> Optional[ExtractionVariable]:
    """
    Garante que existe uma variável correspondente à pergunta.

    Esta função:
    1. Verifica se a pergunta tem os campos mínimos (texto, tipo)
    2. Determina o slug (usa nome_variavel_sugerido se existir, senão gera a partir do texto)
    3. Verifica se já existe uma variável com esse slug
    4. Se existir e pertencer a outra pergunta, usa sufixo para unicidade
    5. Se não existir, cria uma nova variável
    6. Atualiza a pergunta com o slug se foi gerado

    Args:
        db: Sessão do banco de dados
        pergunta: Pergunta de extração
        categoria: Categoria da pergunta

    Returns:
        ExtractionVariable criada/atualizada ou None se pergunta incompleta
    """
    # Verifica campos mínimos
    if not pergunta.pergunta or not pergunta.pergunta.strip():
        return None

    if not pergunta.tipo_sugerido or not pergunta.tipo_sugerido.strip():
        return None

    # Determina o slug
    if pergunta.nome_variavel_sugerido and pergunta.nome_variavel_sugerido.strip():
        slug_base = pergunta.nome_variavel_sugerido.strip()
    else:
        # Gera slug a partir do texto da pergunta
        slug_base = _slugify(pergunta.pergunta)
        if not slug_base:
            slug_base = f"variavel_{pergunta.id or 'nova'}"

    # Verifica se já existe variável vinculada a esta pergunta
    variavel_existente = db.query(ExtractionVariable).filter(
        ExtractionVariable.source_question_id == pergunta.id
    ).first() if pergunta.id else None

    if variavel_existente:
        # Atualiza variável existente
        slug_antigo = variavel_existente.slug
        novo_slug = slug_base

        # Se mudou o slug, verifica unicidade
        if slug_antigo != novo_slug:
            novo_slug = _get_unique_slug(db, novo_slug, exclude_question_id=pergunta.id)

        variavel_existente.slug = novo_slug
        variavel_existente.label = pergunta.pergunta[:200] if pergunta.pergunta else slug_base
        variavel_existente.tipo = pergunta.tipo_sugerido.lower()
        variavel_existente.descricao = pergunta.descricao
        variavel_existente.opcoes = pergunta.opcoes_sugeridas
        variavel_existente.categoria_id = categoria.id

        # Atualiza dependências
        if pergunta.depends_on_variable:
            variavel_existente.is_conditional = True
            variavel_existente.depends_on_variable = pergunta.depends_on_variable
            variavel_existente.dependency_config = {
                "operator": pergunta.dependency_operator or "equals",
                "value": pergunta.dependency_value
            } if pergunta.dependency_operator else None
        else:
            variavel_existente.is_conditional = False
            variavel_existente.depends_on_variable = None
            variavel_existente.dependency_config = None

        variavel_existente.atualizado_em = datetime.utcnow()

        # Atualiza nome_variavel_sugerido da pergunta se mudou
        if pergunta.nome_variavel_sugerido != novo_slug:
            pergunta.nome_variavel_sugerido = novo_slug

        logger.info(f"Variável atualizada: {variavel_existente.slug} (pergunta_id={pergunta.id})")
        return variavel_existente

    # Verifica se existe variável com o mesmo slug (de outra pergunta ou manual)
    variavel_mesmo_slug = db.query(ExtractionVariable).filter(
        ExtractionVariable.slug == slug_base
    ).first()

    if variavel_mesmo_slug:
        # Já existe variável com esse slug
        if variavel_mesmo_slug.source_question_id is None:
            # Variável manual sem pergunta vinculada - vincula a esta pergunta
            variavel_mesmo_slug.source_question_id = pergunta.id
            variavel_mesmo_slug.categoria_id = categoria.id
            variavel_mesmo_slug.label = pergunta.pergunta[:200] if pergunta.pergunta else slug_base
            variavel_mesmo_slug.tipo = pergunta.tipo_sugerido.lower()
            variavel_mesmo_slug.descricao = pergunta.descricao or variavel_mesmo_slug.descricao
            variavel_mesmo_slug.opcoes = pergunta.opcoes_sugeridas or variavel_mesmo_slug.opcoes
            variavel_mesmo_slug.atualizado_em = datetime.utcnow()

            # Atualiza nome_variavel_sugerido da pergunta
            if pergunta.nome_variavel_sugerido != slug_base:
                pergunta.nome_variavel_sugerido = slug_base

            logger.info(f"Variável existente vinculada: {variavel_mesmo_slug.slug} (pergunta_id={pergunta.id})")
            return variavel_mesmo_slug
        else:
            # Variável já vinculada a outra pergunta - usa sufixo
            slug_unico = _get_unique_slug(db, slug_base, exclude_question_id=pergunta.id)
            slug_base = slug_unico

    # Cria nova variável
    variavel = ExtractionVariable(
        slug=slug_base,
        label=pergunta.pergunta[:200] if pergunta.pergunta else slug_base,
        descricao=pergunta.descricao,
        tipo=pergunta.tipo_sugerido.lower(),
        categoria_id=categoria.id,
        opcoes=pergunta.opcoes_sugeridas,
        source_question_id=pergunta.id,
        is_conditional=bool(pergunta.depends_on_variable),
        depends_on_variable=pergunta.depends_on_variable,
        dependency_config={
            "operator": pergunta.dependency_operator or "equals",
            "value": pergunta.dependency_value
        } if pergunta.depends_on_variable and pergunta.dependency_operator else None,
        ativo=True
    )

    db.add(variavel)
    db.flush()  # Para obter o ID

    # Atualiza nome_variavel_sugerido da pergunta se foi gerado
    if pergunta.nome_variavel_sugerido != slug_base:
        pergunta.nome_variavel_sugerido = slug_base

    logger.info(f"Variável criada: {variavel.slug} (id={variavel.id}, pergunta_id={pergunta.id})")

    return variavel


@router.get("/categorias/{categoria_id}/perguntas", response_model=List[ExtractionQuestionResponse])
async def listar_perguntas_categoria(
    categoria_id: int,
    apenas_ativos: bool = Query(True, description="Filtrar apenas ativos"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lista todas as perguntas de extração de uma categoria"""
    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    query = db.query(ExtractionQuestion).filter(ExtractionQuestion.categoria_id == categoria_id)

    if apenas_ativos:
        query = query.filter(ExtractionQuestion.ativo == True)

    perguntas = query.order_by(ExtractionQuestion.ordem, ExtractionQuestion.id).all()

    # Monta resposta com nome da categoria
    resultado = []
    for p in perguntas:
        resp = ExtractionQuestionResponse(
            id=p.id,
            categoria_id=p.categoria_id,
            categoria_nome=categoria.nome,
            pergunta=p.pergunta,
            nome_variavel_sugerido=p.nome_variavel_sugerido,
            tipo_sugerido=p.tipo_sugerido,
            opcoes_sugeridas=p.opcoes_sugeridas,
            descricao=p.descricao,
            depends_on_variable=p.depends_on_variable,
            dependency_operator=p.dependency_operator,
            dependency_value=p.dependency_value,
            dependency_inferred=p.dependency_inferred,
            ativo=p.ativo,
            ordem=p.ordem,
            criado_por=p.criado_por,
            criado_em=p.criado_em,
            atualizado_em=p.atualizado_em
        )
        resultado.append(resp)

    return resultado


@router.post("/perguntas", response_model=ExtractionQuestionResponse, status_code=201)
async def criar_pergunta(
    data: ExtractionQuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Cria uma nova pergunta de extração"""
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para criar perguntas")

    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == data.categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Cria a pergunta
    pergunta = ExtractionQuestion(
        categoria_id=data.categoria_id,
        pergunta=data.pergunta,
        nome_variavel_sugerido=data.nome_variavel_sugerido,
        tipo_sugerido=data.tipo_sugerido,
        opcoes_sugeridas=data.opcoes_sugeridas,
        descricao=data.descricao,
        depends_on_variable=data.depends_on_variable,
        dependency_operator=data.dependency_operator,
        dependency_value=data.dependency_value,
        dependency_inferred=data.dependency_inferred,
        ativo=data.ativo,
        ordem=data.ordem,
        criado_por=current_user.id
    )
    db.add(pergunta)
    db.flush()  # Obtém ID antes de criar variável

    # Cria/atualiza variável correspondente (se pergunta tiver campos mínimos)
    variavel = ensure_variable_for_question(db, pergunta, categoria)

    db.commit()
    db.refresh(pergunta)

    logger.info(f"Pergunta de extração criada: id={pergunta.id}, categoria={categoria.nome}"
                f"{f', variavel={variavel.slug}' if variavel else ''}")

    return ExtractionQuestionResponse(
        id=pergunta.id,
        categoria_id=pergunta.categoria_id,
        categoria_nome=categoria.nome,
        pergunta=pergunta.pergunta,
        nome_variavel_sugerido=pergunta.nome_variavel_sugerido,
        tipo_sugerido=pergunta.tipo_sugerido,
        opcoes_sugeridas=pergunta.opcoes_sugeridas,
        descricao=pergunta.descricao,
        depends_on_variable=pergunta.depends_on_variable,
        dependency_operator=pergunta.dependency_operator,
        dependency_value=pergunta.dependency_value,
        dependency_inferred=pergunta.dependency_inferred,
        ativo=pergunta.ativo,
        ordem=pergunta.ordem,
        criado_por=pergunta.criado_por,
        criado_em=pergunta.criado_em,
        atualizado_em=pergunta.atualizado_em
    )


@router.post("/perguntas/lote", response_model=BulkQuestionsResponse, status_code=201)
async def criar_perguntas_lote(
    data: BulkQuestionsCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Cria múltiplas perguntas de extração de uma vez.
    
    Se analisar_dependencias=True:
    1. Envia todas as perguntas para a IA (Gemini)
    2. A IA analisa relações de dependência entre elas
    3. Cria as perguntas na ordem correta (respeitando dependências)
    4. Retorna as perguntas criadas com suas dependências inferidas
    
    Exemplo de uso:
    - Envie: ["O medicamento é incorporado ao SUS?", "Qual alternativa terapêutica foi tentada?"]
    - IA detecta: A segunda pergunta só faz sentido se o medicamento NÃO é incorporado
    - Resultado: Segunda pergunta depende da primeira com condição "equals: false"
    """
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para criar perguntas")

    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == data.categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    perguntas_resultado = []
    total_criadas = 0
    total_com_dependencias = 0
    grafo_dependencias = None

    try:
        # Se deve analisar dependências com IA
        dependencias_map = {}
        if data.analisar_dependencias and len(data.perguntas) > 1:
            from .services_dependencies import DependencyInferenceService
            
            service = DependencyInferenceService(db)
            resultado_analise = await service.analisar_dependencias_batch(
                perguntas=[p.pergunta for p in data.perguntas],
                nomes_variaveis=[p.nome_variavel_sugerido for p in data.perguntas],
                categoria_nome=categoria.nome
            )
            
            if resultado_analise.get("success"):
                dependencias_map = resultado_analise.get("dependencias", {})
                grafo_dependencias = resultado_analise.get("grafo")
        
        # Conta perguntas existentes para definir ordem
        perguntas_existentes = db.query(ExtractionQuestion).filter(
            ExtractionQuestion.categoria_id == data.categoria_id
        ).count()
        
        # Cria as perguntas na ordem, aplicando dependências se houver
        for i, p in enumerate(data.perguntas):
            try:
                # Busca dependência inferida para esta pergunta
                dep_info = dependencias_map.get(str(i), {})
                depends_on = dep_info.get("depends_on_variable")
                dep_operator = dep_info.get("operator", "equals") if depends_on else None
                dep_value = dep_info.get("value") if depends_on else None
                
                pergunta = ExtractionQuestion(
                    categoria_id=data.categoria_id,
                    pergunta=p.pergunta,
                    nome_variavel_sugerido=p.nome_variavel_sugerido,
                    tipo_sugerido=p.tipo_sugerido,
                    opcoes_sugeridas=p.opcoes_sugeridas,
                    depends_on_variable=depends_on,
                    dependency_operator=dep_operator,
                    dependency_value=dep_value,
                    dependency_inferred=bool(depends_on),
                    ativo=True,
                    ordem=perguntas_existentes + i,
                    criado_por=current_user.id
                )
                db.add(pergunta)
                db.flush()  # Obtém o ID antes do commit
                
                perguntas_resultado.append(BulkQuestionResult(
                    index=i,
                    pergunta_texto=p.pergunta,
                    id=pergunta.id,
                    slug_sugerido=p.nome_variavel_sugerido,
                    depends_on_variable=depends_on,
                    dependency_operator=dep_operator,
                    dependency_value=dep_value
                ))
                
                total_criadas += 1
                if depends_on:
                    total_com_dependencias += 1
                    
            except Exception as e:
                logger.error(f"Erro ao criar pergunta {i}: {e}")
                perguntas_resultado.append(BulkQuestionResult(
                    index=i,
                    pergunta_texto=p.pergunta,
                    erro=str(e)
                ))
        
        db.commit()
        
        logger.info(f"Criadas {total_criadas} perguntas em lote para categoria {categoria.nome}")
        
        return BulkQuestionsResponse(
            success=True,
            total_enviadas=len(data.perguntas),
            total_criadas=total_criadas,
            total_com_dependencias=total_com_dependencias,
            perguntas=perguntas_resultado,
            grafo_dependencias=grafo_dependencias
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Erro na criação em lote: {e}")
        return BulkQuestionsResponse(
            success=False,
            total_enviadas=len(data.perguntas),
            total_criadas=0,
            total_com_dependencias=0,
            perguntas=[],
            erro=str(e)
        )


# ============================================================================
# ORDENAÇÃO DE PERGUNTAS POR IA
# ============================================================================

class PerguntaOrdenarItem(BaseModel):
    """Item para ordenação de pergunta"""
    id: Optional[int] = None
    pergunta: str
    tipo_sugerido: Optional[str] = None
    nome_variavel_sugerido: Optional[str] = None
    depends_on_variable: Optional[str] = None  # Slug da variável da qual depende


class OrdenarPerguntasRequest(BaseModel):
    """Request para ordenar perguntas com IA"""
    categoria_nome: str
    perguntas: List[PerguntaOrdenarItem]


class PosicionarPerguntaRequest(BaseModel):
    """Request para posicionar uma nova pergunta"""
    categoria_nome: str
    nova_pergunta: PerguntaOrdenarItem
    perguntas_existentes: List[dict]


@router.post("/perguntas/ordenar-ia")
async def ordenar_perguntas_ia(
    data: OrdenarPerguntasRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Reordena todas as perguntas usando IA para determinar a ordem mais lógica.
    Usa gemini-3-flash-preview para análise semântica.
    """
    from services.gemini_service import gemini_service

    if len(data.perguntas) < 2:
        return {"success": False, "erro": "Necessário pelo menos 2 perguntas para ordenar"}

    # Monta prompt para IA com informações de dependência
    perguntas_texto = "\n".join([
        f"- {p.pergunta}" +
        (f" (tipo: {p.tipo_sugerido})" if p.tipo_sugerido else "") +
        (f" [CONDICIONAL: depende de '{p.depends_on_variable}']" if p.depends_on_variable else "")
        for p in data.perguntas
    ])

    prompt = f"""Você é um especialista em extração de dados de documentos jurídicos.

TAREFA: Reordenar as perguntas de extração para a categoria "{data.categoria_nome}" na ordem mais lógica.

REGRA CENTRAL DE ORDENAÇÃO (MUITO IMPORTANTE):
⚠️ Perguntas condicionais NÃO devem ser jogadas todas para o final.
A regra correta é:
- Cada pergunta CONDICIONAL deve ficar LOGO ABAIXO da sua pergunta âncora (a pergunta da qual depende)
- A estrutura deve seguir este padrão:
  * Pergunta âncora (pergunta principal)
  * Suas perguntas condicionais imediatas (logo abaixo)
  * Próxima pergunta âncora
  * Condicionais dela (logo abaixo)
  * E assim por diante...
- Apenas perguntas realmente residuais ou finais ficam no final do fluxo

CRITÉRIOS ADICIONAIS DE ORDENAÇÃO:
1. Informações de identificação primeiro (partes, número do processo, tipo de ação, datas)
2. Informações gerais/estruturais antes de específicas
3. Para perguntas âncora: seguir fluxo lógico de leitura do documento
4. Para perguntas condicionais: sempre imediatamente após sua âncora
5. Valores monetários e cálculos geralmente no final
6. Não separar uma pergunta condicional da sua âncora - elas devem estar adjacentes

EXEMPLO CONCEITUAL:
- "Existe pedido de tutela de urgência?" (âncora)
- "Quais são os detalhes da tutela?" (condicional - logo abaixo)
- "Existe pedido alternativo?" (âncora)
- "Qual é o pedido alternativo?" (condicional - logo abaixo)
- "Qual o valor da causa?" (pergunta final)

PERGUNTAS PARA ORDENAR:
{perguntas_texto}

RESPONDA APENAS com um JSON válido no formato:
{{"ordered_question_ids": ["pergunta exata 1", "pergunta exata 2", ...]}}

REGRAS DE RESPOSTA:
- Use EXATAMENTE o texto das perguntas fornecidas, sem modificar
- Não adicione, remova ou modifique perguntas
- Não inclua markdown, apenas JSON puro
- O campo deve ser "ordered_question_ids" com array de strings"""

    try:
        response = await gemini_service.generate(
            prompt=prompt,
            system_prompt="Você reordena perguntas de extração de dados. Responda APENAS com JSON válido.",
            model="gemini-3-flash-preview",
            temperature=0.1
        )

        if not response.success:
            return {"success": False, "erro": f"Erro na IA: {response.error}"}

        # Parseia resposta
        import json
        import re

        content = response.content.strip()
        # Remove markdown se houver
        if content.startswith("```"):
            content = re.sub(r'^```\w*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)

        resultado = json.loads(content)
        # Suporta ambos os formatos: "ordered_question_ids" (novo) e "ordem" (legado)
        ordem = resultado.get("ordered_question_ids", resultado.get("ordem", []))

        # Mapeia perguntas originais para a nova ordem
        pergunta_map = {p.pergunta.strip().lower(): p for p in data.perguntas}
        ordem_final = []

        for pergunta_texto in ordem:
            p = pergunta_map.get(pergunta_texto.strip().lower())
            if p:
                ordem_final.append({
                    "id": p.id,
                    "pergunta": p.pergunta
                })

        # Adiciona perguntas que não foram incluídas na ordem (fallback)
        incluidas = {o["pergunta"].strip().lower() for o in ordem_final}
        for p in data.perguntas:
            if p.pergunta.strip().lower() not in incluidas:
                ordem_final.append({
                    "id": p.id,
                    "pergunta": p.pergunta
                })

        logger.info(f"Perguntas reordenadas por IA para categoria '{data.categoria_nome}'")

        return {
            "success": True,
            "ordem": ordem_final
        }

    except Exception as e:
        logger.error(f"Erro ao ordenar perguntas com IA: {e}")
        return {"success": False, "erro": str(e)}


@router.post("/perguntas/posicionar-ia")
async def posicionar_pergunta_ia(
    data: PosicionarPerguntaRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Determina a melhor posição para uma nova pergunta usando IA.
    Usa gemini-3-flash-preview para análise semântica.
    """
    from services.gemini_service import gemini_service

    if not data.perguntas_existentes:
        return {"success": True, "posicao": 0}

    # Monta lista de perguntas existentes com suas posições
    perguntas_existentes = "\n".join([
        f"{i}. {p.get('pergunta', '')}"
        for i, p in enumerate(data.perguntas_existentes)
    ])

    prompt = f"""Você é um especialista em extração de dados de documentos jurídicos.

TAREFA: Determinar a melhor posição para inserir uma NOVA pergunta na lista existente.

CATEGORIA: {data.categoria_nome}

NOVA PERGUNTA: {data.nova_pergunta.pergunta}
{f"Tipo sugerido: {data.nova_pergunta.tipo_sugerido}" if data.nova_pergunta.tipo_sugerido else ""}

PERGUNTAS EXISTENTES (ordenadas):
{perguntas_existentes}

REGRA CENTRAL:
- Se a nova pergunta é CONDICIONAL (depende de outra), deve ficar LOGO APÓS a pergunta âncora
- Se a nova pergunta é uma ÂNCORA (pode ter condicionais), considere onde ela se encaixa no fluxo

CRITÉRIOS DE POSICIONAMENTO:
1. Identificação primeiro (partes, número, tipo de ação, datas)
2. Informações gerais/estruturais antes de específicas
3. Se condicional: imediatamente após sua âncora (pergunta da qual depende)
4. Valores monetários e cálculos geralmente no final
5. Mantenha o fluxo lógico de leitura do documento

RESPONDA APENAS com um JSON: {{"posicao": N}}
Onde N é o índice onde inserir (0 = primeira posição, antes de todas).
Se a posição sugerida estiver fora dos limites (0 a {len(data.perguntas_existentes)}), será ajustada automaticamente."""

    try:
        response = await gemini_service.generate(
            prompt=prompt,
            system_prompt="Você posiciona perguntas de extração. Responda APENAS com JSON válido.",
            model="gemini-3-flash-preview",
            temperature=0.1
        )

        if not response.success:
            return {"success": False, "posicao": len(data.perguntas_existentes)}

        # Parseia resposta
        import json
        import re

        content = response.content.strip()
        if content.startswith("```"):
            content = re.sub(r'^```\w*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)

        resultado = json.loads(content)
        posicao = resultado.get("posicao", len(data.perguntas_existentes))

        # Garante que posição está dentro dos limites
        posicao = max(0, min(posicao, len(data.perguntas_existentes)))

        logger.info(f"IA posicionou nova pergunta em {posicao} para categoria '{data.categoria_nome}'")

        return {
            "success": True,
            "posicao": posicao
        }

    except Exception as e:
        logger.error(f"Erro ao posicionar pergunta com IA: {e}")
        return {"success": False, "posicao": len(data.perguntas_existentes)}


@router.get("/perguntas/{pergunta_id}", response_model=ExtractionQuestionResponse)
async def obter_pergunta(
    pergunta_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtém uma pergunta específica"""
    pergunta = db.query(ExtractionQuestion).filter(ExtractionQuestion.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")

    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == pergunta.categoria_id).first()

    return ExtractionQuestionResponse(
        id=pergunta.id,
        categoria_id=pergunta.categoria_id,
        categoria_nome=categoria.nome if categoria else None,
        pergunta=pergunta.pergunta,
        nome_variavel_sugerido=pergunta.nome_variavel_sugerido,
        tipo_sugerido=pergunta.tipo_sugerido,
        opcoes_sugeridas=pergunta.opcoes_sugeridas,
        descricao=pergunta.descricao,
        depends_on_variable=pergunta.depends_on_variable,
        dependency_operator=pergunta.dependency_operator,
        dependency_value=pergunta.dependency_value,
        dependency_inferred=pergunta.dependency_inferred,
        fonte_verdade_tipo=pergunta.fonte_verdade_tipo,
        fonte_verdade_override=pergunta.fonte_verdade_override,
        ativo=pergunta.ativo,
        ordem=pergunta.ordem,
        criado_por=pergunta.criado_por,
        criado_em=pergunta.criado_em,
        atualizado_em=pergunta.atualizado_em
    )


@router.put("/perguntas/{pergunta_id}", response_model=ExtractionQuestionResponse)
async def atualizar_pergunta(
    pergunta_id: int,
    data: ExtractionQuestionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualiza uma pergunta existente"""
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para editar perguntas")

    pergunta = db.query(ExtractionQuestion).filter(ExtractionQuestion.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")

    # Atualiza campos fornecidos
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(pergunta, field, value)

    pergunta.atualizado_por = current_user.id
    pergunta.atualizado_em = datetime.utcnow()

    # Busca categoria para criar/atualizar variável
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == pergunta.categoria_id).first()

    # Cria/atualiza variável correspondente (se pergunta tiver campos mínimos)
    variavel = ensure_variable_for_question(db, pergunta, categoria) if categoria else None

    db.commit()
    db.refresh(pergunta)

    logger.info(f"Pergunta de extração atualizada: id={pergunta.id}"
                f"{f', variavel={variavel.slug}' if variavel else ''}")

    return ExtractionQuestionResponse(
        id=pergunta.id,
        categoria_id=pergunta.categoria_id,
        categoria_nome=categoria.nome if categoria else None,
        pergunta=pergunta.pergunta,
        nome_variavel_sugerido=pergunta.nome_variavel_sugerido,
        tipo_sugerido=pergunta.tipo_sugerido,
        opcoes_sugeridas=pergunta.opcoes_sugeridas,
        descricao=pergunta.descricao,
        depends_on_variable=pergunta.depends_on_variable,
        dependency_operator=pergunta.dependency_operator,
        dependency_value=pergunta.dependency_value,
        dependency_inferred=pergunta.dependency_inferred,
        ativo=pergunta.ativo,
        ordem=pergunta.ordem,
        criado_por=pergunta.criado_por,
        criado_em=pergunta.criado_em,
        atualizado_em=pergunta.atualizado_em
    )


# --- Schema para atualização de ordem em lote ---
class OrdemPerguntaItem(BaseModel):
    """Item para atualização de ordem de uma pergunta"""
    id: int = Field(..., description="ID da pergunta")
    ordem: int = Field(..., description="Nova ordem (0-indexed)")


class AtualizarOrdemLoteRequest(BaseModel):
    """Request para atualizar ordem de múltiplas perguntas de uma vez"""
    categoria_id: int = Field(..., description="ID da categoria (para validação)")
    perguntas: List[OrdemPerguntaItem] = Field(..., min_length=1, description="Lista de perguntas com nova ordem")


class AtualizarOrdemLoteResponse(BaseModel):
    """Response da atualização em lote"""
    success: bool
    atualizadas: int
    message: str


@router.put("/perguntas/ordem-lote", response_model=AtualizarOrdemLoteResponse)
async def atualizar_ordem_perguntas_lote(
    data: AtualizarOrdemLoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Atualiza a ordem de múltiplas perguntas em uma única requisição.

    PERFORMANCE: Este endpoint substitui N requisições PUT individuais por uma única
    requisição batch, reduzindo drasticamente a latência em conexões de alta latência.

    Exemplo de uso:
    ```json
    {
        "categoria_id": 1,
        "perguntas": [
            {"id": 10, "ordem": 0},
            {"id": 15, "ordem": 1},
            {"id": 12, "ordem": 2}
        ]
    }
    ```
    """
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para editar perguntas")

    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == data.categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Extrai IDs para buscar todas as perguntas de uma vez
    ids_perguntas = [p.id for p in data.perguntas]

    # Busca todas as perguntas em uma única query
    perguntas_db = db.query(ExtractionQuestion).filter(
        ExtractionQuestion.id.in_(ids_perguntas),
        ExtractionQuestion.categoria_id == data.categoria_id
    ).all()

    # Cria mapa id -> pergunta para acesso O(1)
    perguntas_map = {p.id: p for p in perguntas_db}

    # Valida que todas as perguntas existem e pertencem à categoria
    ids_encontrados = set(perguntas_map.keys())
    ids_solicitados = set(ids_perguntas)
    ids_faltantes = ids_solicitados - ids_encontrados

    if ids_faltantes:
        raise HTTPException(
            status_code=404,
            detail=f"Perguntas não encontradas ou não pertencem à categoria: {list(ids_faltantes)}"
        )

    # Atualiza ordem de todas as perguntas
    now = datetime.utcnow()
    atualizadas = 0

    for item in data.perguntas:
        pergunta = perguntas_map[item.id]
        if pergunta.ordem != item.ordem:  # Só atualiza se mudou
            pergunta.ordem = item.ordem
            pergunta.atualizado_por = current_user.id
            pergunta.atualizado_em = now
            atualizadas += 1

    # Commit único para todas as mudanças
    db.commit()

    logger.info(f"Ordem de {atualizadas} perguntas atualizada em lote para categoria {categoria.nome}")

    return AtualizarOrdemLoteResponse(
        success=True,
        atualizadas=atualizadas,
        message=f"{atualizadas} perguntas reordenadas com sucesso"
    )


@router.delete("/perguntas/{pergunta_id}")
async def excluir_pergunta(
    pergunta_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Desativa uma pergunta (soft delete)"""
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para excluir perguntas")

    pergunta = db.query(ExtractionQuestion).filter(ExtractionQuestion.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")

    pergunta.ativo = False
    pergunta.atualizado_por = current_user.id
    pergunta.atualizado_em = datetime.utcnow()

    db.commit()

    logger.info(f"Pergunta de extração desativada: id={pergunta_id}")

    return {"success": True, "message": "Pergunta desativada com sucesso"}


# ============================================================================
# ENDPOINTS - MODELOS DE EXTRAÇÃO
# ============================================================================

@router.get("/categorias/{categoria_id}/modelo", response_model=Optional[ExtractionModelResponse])
async def obter_modelo_categoria(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtém o modelo de extração ativo de uma categoria"""
    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Busca o modelo ativo mais recente
    modelo = db.query(ExtractionModel).filter(
        ExtractionModel.categoria_id == categoria_id,
        ExtractionModel.ativo == True
    ).order_by(ExtractionModel.versao.desc()).first()

    if not modelo:
        return None

    return ExtractionModelResponse(
        id=modelo.id,
        categoria_id=modelo.categoria_id,
        categoria_nome=categoria.nome,
        modo=modelo.modo,
        schema_json=modelo.schema_json,
        mapeamento_variaveis=modelo.mapeamento_variaveis,
        versao=modelo.versao,
        ativo=modelo.ativo,
        criado_por=modelo.criado_por,
        criado_em=modelo.criado_em
    )


@router.post("/categorias/{categoria_id}/gerar-schema", response_model=GenerateSchemaResponse)
async def gerar_schema_ia(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Gera um modelo de extração JSON usando IA a partir das perguntas da categoria.

    Este endpoint:
    1. Coleta todas as perguntas ativas da categoria
    2. Envia para o Gemini 3 Flash Preview para gerar o schema
    3. Cria variáveis normalizadas a partir do mapeamento
    4. Salva o modelo de extração
    """
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para gerar schema")

    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Busca perguntas ativas da categoria
    perguntas = db.query(ExtractionQuestion).filter(
        ExtractionQuestion.categoria_id == categoria_id,
        ExtractionQuestion.ativo == True
    ).order_by(ExtractionQuestion.ordem, ExtractionQuestion.id).all()

    if not perguntas:
        raise HTTPException(status_code=400, detail="Nenhuma pergunta ativa encontrada para esta categoria")

    # Gera o schema usando o serviço de IA
    generator = ExtractionSchemaGenerator(db)
    try:
        resultado = await generator.gerar_schema(
            categoria_id=categoria_id,
            categoria_nome=categoria.nome,
            perguntas=perguntas,
            user_id=current_user.id
        )

        if not resultado.get("success"):
            return GenerateSchemaResponse(
                success=False,
                erro=resultado.get("erro", "Erro desconhecido na geração do schema")
            )

        return GenerateSchemaResponse(
            success=True,
            schema_json=resultado.get("schema_json"),
            mapeamento_variaveis=resultado.get("mapeamento_variaveis"),
            variaveis_criadas=resultado.get("variaveis_criadas")
        )

    except Exception as e:
        logger.error(f"Erro ao gerar schema: {e}")
        return GenerateSchemaResponse(
            success=False,
            erro=str(e)
        )


@router.post("/categorias/{categoria_id}/sincronizar-json", response_model=SyncJsonResponse)
async def sincronizar_json_sem_ia(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Sincroniza o JSON da categoria com as perguntas cadastradas, SEM usar IA.

    Este endpoint:
    1. Carrega todas as perguntas ativas da categoria (ordenadas)
    2. Carrega o JSON atual da categoria
    3. Valida que perguntas tenham slug e tipo definidos
    4. Faz merge das perguntas no JSON (adiciona novas, preserva existentes)
    5. Ordena o JSON conforme a ordem das perguntas
    6. Retorna o JSON atualizado (não salva automaticamente)

    Regras:
    - Não remove campos existentes do JSON
    - Não sobrescreve valores já definidos
    - Só adiciona perguntas "prontas" (com slug e tipo)
    - Preserva a ordem das perguntas como fonte da verdade
    """
    import json

    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para sincronizar JSON")

    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Busca perguntas ativas da categoria, ordenadas
    perguntas = db.query(ExtractionQuestion).filter(
        ExtractionQuestion.categoria_id == categoria_id,
        ExtractionQuestion.ativo == True
    ).order_by(ExtractionQuestion.ordem, ExtractionQuestion.id).all()

    if not perguntas:
        return SyncJsonResponse(
            success=True,
            schema_json={},
            variaveis_adicionadas=0,
            mensagem="Nenhuma pergunta ativa encontrada para esta categoria"
        )

    # Carrega JSON atual da categoria
    try:
        json_atual = json.loads(categoria.formato_json) if categoria.formato_json else {}
    except json.JSONDecodeError:
        json_atual = {}

    # Valida perguntas e identifica incompletas
    perguntas_incompletas = []
    perguntas_validas = []

    for p in perguntas:
        slug = p.nome_variavel_sugerido
        tipo = p.tipo_sugerido

        if not slug or not slug.strip():
            perguntas_incompletas.append({
                "id": p.id,
                "pergunta": p.pergunta[:100] + "..." if len(p.pergunta) > 100 else p.pergunta,
                "problema": "Falta nome/slug da variável"
            })
            continue

        if not tipo or not tipo.strip():
            perguntas_incompletas.append({
                "id": p.id,
                "pergunta": p.pergunta[:100] + "..." if len(p.pergunta) > 100 else p.pergunta,
                "slug": slug,
                "problema": "Falta tipo da variável"
            })
            continue

        perguntas_validas.append(p)

    # Se há perguntas incompletas, retorna erro
    if perguntas_incompletas:
        return SyncJsonResponse(
            success=False,
            perguntas_incompletas=perguntas_incompletas,
            erro=f"Não foi possível atualizar: {len(perguntas_incompletas)} pergunta(s) incompleta(s)"
        )

    # Faz merge: cria novo JSON ordenado conforme perguntas
    json_novo = {}
    variaveis_adicionadas = []

    for p in perguntas_validas:
        slug = p.nome_variavel_sugerido.strip()
        tipo = p.tipo_sugerido.strip().lower()

        if slug in json_atual:
            # Campo já existe - preserva configuração existente
            json_novo[slug] = json_atual[slug]
        else:
            # Campo novo - cria com defaults mínimos
            config = {
                "type": tipo,
                "description": p.pergunta
            }

            # Adiciona dependências se configuradas
            if p.depends_on_variable:
                config["conditional"] = True
                config["depends_on"] = p.depends_on_variable

                if p.dependency_operator:
                    config["dependency_operator"] = p.dependency_operator

                if p.dependency_value is not None:
                    config["dependency_value"] = p.dependency_value

            # Adiciona opções se tipo choice e há opções
            if tipo == "choice" and p.opcoes_sugeridas:
                config["options"] = p.opcoes_sugeridas

            json_novo[slug] = config
            variaveis_adicionadas.append(slug)

    # Adiciona campos do JSON original que não estão nas perguntas (preserva campos manuais)
    for chave, valor in json_atual.items():
        if chave not in json_novo:
            json_novo[chave] = valor

    # Monta resposta
    if variaveis_adicionadas:
        mensagem = f"JSON atualizado: {len(variaveis_adicionadas)} variável(is) adicionada(s)"
    else:
        mensagem = "Nada para atualizar - todas as perguntas já estão no JSON"

    logger.info(f"Sincronização JSON categoria {categoria_id}: {len(variaveis_adicionadas)} adicionadas")

    return SyncJsonResponse(
        success=True,
        schema_json=json_novo,
        variaveis_adicionadas=len(variaveis_adicionadas),
        variaveis_adicionadas_lista=variaveis_adicionadas if variaveis_adicionadas else None,
        mensagem=mensagem
    )


@router.post("/modelos", response_model=ExtractionModelResponse, status_code=201)
async def criar_modelo_manual(
    data: ExtractionModelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Cria um modelo de extração manual"""
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para criar modelos")

    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == data.categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Desativa modelos anteriores da categoria
    db.query(ExtractionModel).filter(
        ExtractionModel.categoria_id == data.categoria_id,
        ExtractionModel.ativo == True
    ).update({"ativo": False})

    # Calcula próxima versão
    max_versao = db.query(func.max(ExtractionModel.versao)).filter(
        ExtractionModel.categoria_id == data.categoria_id
    ).scalar() or 0

    # Cria o modelo
    modelo = ExtractionModel(
        categoria_id=data.categoria_id,
        modo=data.modo,
        schema_json=data.schema_json,
        mapeamento_variaveis=data.mapeamento_variaveis,
        versao=max_versao + 1,
        ativo=True,
        criado_por=current_user.id
    )
    db.add(modelo)
    db.commit()
    db.refresh(modelo)

    logger.info(f"Modelo de extração criado: id={modelo.id}, categoria={categoria.nome}, modo={modelo.modo}")

    return ExtractionModelResponse(
        id=modelo.id,
        categoria_id=modelo.categoria_id,
        categoria_nome=categoria.nome,
        modo=modelo.modo,
        schema_json=modelo.schema_json,
        mapeamento_variaveis=modelo.mapeamento_variaveis,
        versao=modelo.versao,
        ativo=modelo.ativo,
        criado_por=modelo.criado_por,
        criado_em=modelo.criado_em
    )


# ============================================================================
# ENDPOINTS - VARIÁVEIS NORMALIZADAS
# ============================================================================

@router.get("/variaveis", response_model=List[ExtractionVariableResponse])
async def listar_variaveis(
    categoria_id: Optional[int] = Query(None, description="Filtrar por categoria"),
    source_question_id: Optional[int] = Query(None, description="Filtrar por pergunta de origem"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo"),
    busca: Optional[str] = Query(None, description="Buscar por slug ou label"),
    apenas_ativos: bool = Query(True, description="Filtrar apenas ativos"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Lista todas as variáveis normalizadas do sistema"""
    query = db.query(ExtractionVariable)

    if categoria_id:
        query = query.filter(ExtractionVariable.categoria_id == categoria_id)

    if source_question_id:
        query = query.filter(ExtractionVariable.source_question_id == source_question_id)

    if tipo:
        query = query.filter(ExtractionVariable.tipo == tipo)

    if busca:
        busca_like = f"%{busca}%"
        query = query.filter(
            (ExtractionVariable.slug.ilike(busca_like)) |
            (ExtractionVariable.label.ilike(busca_like))
        )

    if apenas_ativos:
        query = query.filter(ExtractionVariable.ativo == True)

    total = query.count()
    
    # Ordena por categoria, depois pela ordem da pergunta de origem
    variaveis = query.outerjoin(
        ExtractionQuestion,
        ExtractionVariable.source_question_id == ExtractionQuestion.id
    ).order_by(
        ExtractionVariable.categoria_id,
        ExtractionQuestion.ordem.nulls_last(),
        ExtractionVariable.slug
    ).offset(offset).limit(limit).all()

    # Busca contagem de uso e informações de dependência para cada variável
    resultado = []
    
    # Mapa de slug para profundidade (para calcular recuo)
    depth_map = {}
    
    def calcular_profundidade(var_slug: str, visitados: set = None) -> int:
        if visitados is None:
            visitados = set()
        if var_slug in depth_map:
            return depth_map[var_slug]
        if var_slug in visitados:
            return 0  # Evita ciclos
        
        # Busca a variável
        var = db.query(ExtractionVariable).filter(ExtractionVariable.slug == var_slug).first()
        if not var or not var.depends_on_variable:
            depth_map[var_slug] = 0
            return 0
        
        visitados.add(var_slug)
        parent_depth = calcular_profundidade(var.depends_on_variable, visitados)
        depth_map[var_slug] = parent_depth + 1
        return depth_map[var_slug]
    
    for v in variaveis:
        uso_count = db.query(PromptVariableUsage).filter(
            PromptVariableUsage.variable_slug == v.slug
        ).count()

        categoria = None
        em_uso_json = False
        if v.categoria_id:
            categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == v.categoria_id).first()
            if categoria and categoria.json_gerado_por_ia:
                em_uso_json = True
        
        # Busca info da pergunta de origem para ordem e dependência
        ordem = 0
        is_conditional = v.is_conditional
        depends_on = v.depends_on_variable
        
        if v.source_question_id:
            pergunta = db.query(ExtractionQuestion).filter(
                ExtractionQuestion.id == v.source_question_id
            ).first()
            if pergunta:
                ordem = pergunta.ordem or 0
                if pergunta.depends_on_variable:
                    is_conditional = True
                    depends_on = pergunta.depends_on_variable
        
        # Calcula profundidade para recuo
        depth = calcular_profundidade(v.slug) if depends_on else 0

        resp = ExtractionVariableResponse(
            id=v.id,
            slug=v.slug,
            label=v.label,
            descricao=v.descricao,
            tipo=v.tipo,
            categoria_id=v.categoria_id,
            categoria_nome=categoria.nome if categoria else None,
            opcoes=v.opcoes,
            fonte_verdade_codigo=v.fonte_verdade_codigo,
            fonte_verdade_tipo=v.fonte_verdade_tipo,
            fonte_verdade_override=v.fonte_verdade_override,
            source_question_id=v.source_question_id,
            ativo=v.ativo,
            criado_em=v.criado_em,
            atualizado_em=v.atualizado_em,
            uso_count=uso_count,
            is_conditional=is_conditional,
            depends_on_variable=depends_on,
            depth=depth,
            ordem=ordem,
            em_uso_json=em_uso_json
        )
        resultado.append(resp)

    return resultado


@router.get("/variaveis/resumo")
async def resumo_variaveis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna um resumo das variáveis do sistema.

    Inclui:
    - Total de variáveis
    - Distribuição por tipo
    - Variáveis mais usadas
    - Variáveis não utilizadas
    """
    try:
        # Total de variáveis
        total = db.query(ExtractionVariable).filter(ExtractionVariable.ativo == True).count()

        # Por tipo
        tipos = db.query(
            ExtractionVariable.tipo,
            func.count(ExtractionVariable.id)
        ).filter(
            ExtractionVariable.ativo == True
        ).group_by(ExtractionVariable.tipo).all()

        distribuicao_tipos = {t[0]: t[1] for t in tipos}

        # Variáveis com uso em prompts (regras determinísticas)
        # Nota: usamos query apenas pelo ID para evitar erro de DISTINCT em colunas JSON no PostgreSQL
        variaveis_com_uso_prompts = db.query(ExtractionVariable.id).join(
            PromptVariableUsage,
            PromptVariableUsage.variable_slug == ExtractionVariable.slug
        ).filter(
            ExtractionVariable.ativo == True
        ).distinct().count()

        # Variáveis em uso no JSON de categorias com json_gerado_por_ia=True
        variaveis_em_uso_json = db.query(ExtractionVariable.id).join(
            CategoriaResumoJSON,
            ExtractionVariable.categoria_id == CategoriaResumoJSON.id
        ).filter(
            ExtractionVariable.ativo == True,
            CategoriaResumoJSON.json_gerado_por_ia == True
        ).distinct().count()

        # Total de variáveis em uso (união dos dois conjuntos)
        # Para evitar contagem dupla, usamos uma abordagem diferente
        variaveis_ids_em_uso = set()

        # IDs de variáveis usadas em prompts
        ids_prompts = db.query(ExtractionVariable.id).join(
            PromptVariableUsage,
            PromptVariableUsage.variable_slug == ExtractionVariable.slug
        ).filter(ExtractionVariable.ativo == True).distinct().all()
        variaveis_ids_em_uso.update(id[0] for id in ids_prompts)

        # IDs de variáveis em uso no JSON
        ids_json = db.query(ExtractionVariable.id).join(
            CategoriaResumoJSON,
            ExtractionVariable.categoria_id == CategoriaResumoJSON.id
        ).filter(
            ExtractionVariable.ativo == True,
            CategoriaResumoJSON.json_gerado_por_ia == True
        ).distinct().all()
        variaveis_ids_em_uso.update(id[0] for id in ids_json)

        variaveis_com_uso = len(variaveis_ids_em_uso)

        # Variáveis mais usadas (top 10)
        mais_usadas_query = db.query(
            PromptVariableUsage.variable_slug,
            func.count(PromptVariableUsage.id).label('uso_count')
        ).group_by(
            PromptVariableUsage.variable_slug
        ).order_by(
            func.count(PromptVariableUsage.id).desc()
        ).limit(10).all()

        mais_usadas = []
        for slug, count in mais_usadas_query:
            variavel = db.query(ExtractionVariable).filter(
                ExtractionVariable.slug == slug
            ).first()
            if variavel:
                mais_usadas.append({
                    "slug": slug,
                    "label": variavel.label,
                    "tipo": variavel.tipo,
                    "uso_count": count
                })

        return {
            "total": total,
            "distribuicao_tipos": distribuicao_tipos,
            "variaveis_com_uso": variaveis_com_uso,
            "variaveis_sem_uso": total - variaveis_com_uso,
            "mais_usadas": mais_usadas
        }
    except Exception as e:
        logger.error(f"Erro ao carregar resumo de variáveis: {e}")
        # Retorna valores default em caso de erro
        return {
            "total": 0,
            "distribuicao_tipos": {},
            "variaveis_com_uso": 0,
            "variaveis_sem_uso": 0,
            "mais_usadas": []
        }


@router.get("/variaveis/{variavel_id}", response_model=VariableDetailResponse)
async def obter_variavel(
    variavel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Obtém detalhes de uma variável com lista de usos"""
    variavel = db.query(ExtractionVariable).filter(ExtractionVariable.id == variavel_id).first()
    if not variavel:
        raise HTTPException(status_code=404, detail="Variável não encontrada")

    categoria = None
    if variavel.categoria_id:
        categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == variavel.categoria_id).first()

    # Busca usos da variável
    from admin.models_prompts import PromptModulo

    usages = db.query(PromptVariableUsage).filter(
        PromptVariableUsage.variable_slug == variavel.slug
    ).all()

    prompt_usages = []
    for usage in usages:
        prompt = db.query(PromptModulo).filter(PromptModulo.id == usage.prompt_id).first()
        if prompt:
            prompt_usages.append(VariableUsageResponse(
                prompt_id=prompt.id,
                prompt_nome=prompt.nome,
                prompt_titulo=prompt.titulo,
                modo_ativacao=prompt.modo_ativacao,
                criado_em=usage.criado_em
            ))

    uso_count = len(prompt_usages)

    return VariableDetailResponse(
        id=variavel.id,
        slug=variavel.slug,
        label=variavel.label,
        descricao=variavel.descricao,
        tipo=variavel.tipo,
        categoria_id=variavel.categoria_id,
        categoria_nome=categoria.nome if categoria else None,
        opcoes=variavel.opcoes,
        source_question_id=variavel.source_question_id,
        ativo=variavel.ativo,
        criado_em=variavel.criado_em,
        atualizado_em=variavel.atualizado_em,
        uso_count=uso_count,
        prompt_usages=prompt_usages
    )


@router.post("/variaveis", response_model=ExtractionVariableResponse, status_code=201)
async def criar_variavel(
    data: ExtractionVariableCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Cria uma nova variável manualmente"""
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para criar variáveis")

    # Verifica se slug já existe
    existing = db.query(ExtractionVariable).filter(ExtractionVariable.slug == data.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Slug '{data.slug}' já existe")

    # Verifica se a categoria existe
    categoria = None
    if data.categoria_id:
        categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == data.categoria_id).first()
        if not categoria:
            raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Cria a variável
    variavel = ExtractionVariable(
        slug=data.slug,
        label=data.label,
        descricao=data.descricao,
        tipo=data.tipo,
        categoria_id=data.categoria_id,
        opcoes=data.opcoes,
        ativo=True
    )
    db.add(variavel)
    db.commit()
    db.refresh(variavel)

    logger.info(f"Variável criada: slug={variavel.slug}")

    return ExtractionVariableResponse(
        id=variavel.id,
        slug=variavel.slug,
        label=variavel.label,
        descricao=variavel.descricao,
        tipo=variavel.tipo,
        categoria_id=variavel.categoria_id,
        categoria_nome=categoria.nome if categoria else None,
        opcoes=variavel.opcoes,
        source_question_id=variavel.source_question_id,
        ativo=variavel.ativo,
        criado_em=variavel.criado_em,
        atualizado_em=variavel.atualizado_em,
        uso_count=0
    )


@router.put("/variaveis/{variavel_id}", response_model=ExtractionVariableResponse)
async def atualizar_variavel(
    variavel_id: int,
    data: ExtractionVariableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Atualiza uma variável existente"""
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para editar variáveis")

    variavel = db.query(ExtractionVariable).filter(ExtractionVariable.id == variavel_id).first()
    if not variavel:
        raise HTTPException(status_code=404, detail="Variável não encontrada")

    # Atualiza campos fornecidos
    update_data = data.model_dump(exclude_unset=True)

    # Guarda valores antigos para detectar mudanças relevantes
    tipo_antigo = variavel.tipo
    descricao_antiga = variavel.descricao

    for field, value in update_data.items():
        setattr(variavel, field, value)

    variavel.atualizado_em = datetime.utcnow()

    # Se tipo ou descrição mudou, atualiza o JSON da categoria
    categoria = None
    if variavel.categoria_id:
        categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == variavel.categoria_id).first()

        # Sincroniza JSON da categoria se tipo ou descrição mudou
        if categoria and categoria.formato_json and (variavel.tipo != tipo_antigo or variavel.descricao != descricao_antiga):
            try:
                import json
                schema = json.loads(categoria.formato_json)

                # Atualiza o campo correspondente ao slug da variável
                if variavel.slug in schema:
                    schema[variavel.slug]["type"] = variavel.tipo
                    if variavel.descricao:
                        schema[variavel.slug]["description"] = variavel.descricao

                    categoria.formato_json = json.dumps(schema, ensure_ascii=False, indent=2)
                    logger.info(f"JSON da categoria {categoria.id} atualizado para refletir mudança na variável {variavel.slug}")
            except Exception as e:
                logger.warning(f"Não foi possível atualizar JSON da categoria: {e}")

    db.commit()
    db.refresh(variavel)

    uso_count = db.query(PromptVariableUsage).filter(
        PromptVariableUsage.variable_slug == variavel.slug
    ).count()

    logger.info(f"Variável atualizada: slug={variavel.slug}")

    return ExtractionVariableResponse(
        id=variavel.id,
        slug=variavel.slug,
        label=variavel.label,
        descricao=variavel.descricao,
        tipo=variavel.tipo,
        categoria_id=variavel.categoria_id,
        categoria_nome=categoria.nome if categoria else None,
        opcoes=variavel.opcoes,
        fonte_verdade_codigo=variavel.fonte_verdade_codigo,
        fonte_verdade_tipo=variavel.fonte_verdade_tipo,
        fonte_verdade_override=variavel.fonte_verdade_override,
        source_question_id=variavel.source_question_id,
        ativo=variavel.ativo,
        criado_em=variavel.criado_em,
        atualizado_em=variavel.atualizado_em,
        uso_count=uso_count
    )


@router.get("/variaveis/{variavel_id}/dependentes")
async def obter_variaveis_dependentes(
    variavel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Retorna variáveis e perguntas que dependem desta variável"""
    variavel = db.query(ExtractionVariable).filter(ExtractionVariable.id == variavel_id).first()
    if not variavel:
        raise HTTPException(status_code=404, detail="Variável não encontrada")

    # Busca variáveis que dependem desta
    variaveis_dependentes = db.query(ExtractionVariable).filter(
        ExtractionVariable.depends_on_variable == variavel.slug,
        ExtractionVariable.ativo == True
    ).all()

    # Busca perguntas que dependem desta variável
    perguntas_dependentes = db.query(ExtractionQuestion).filter(
        ExtractionQuestion.depends_on_variable == variavel.slug,
        ExtractionQuestion.ativo == True
    ).all()

    return {
        "variavel_slug": variavel.slug,
        "variaveis_dependentes": [
            {"id": v.id, "slug": v.slug, "label": v.label}
            for v in variaveis_dependentes
        ],
        "perguntas_dependentes": [
            {"id": p.id, "pergunta": p.pergunta[:50] + "..." if len(p.pergunta) > 50 else p.pergunta}
            for p in perguntas_dependentes
        ],
        "total_dependentes": len(variaveis_dependentes) + len(perguntas_dependentes)
    }


@router.delete("/variaveis/{variavel_id}")
async def excluir_variavel(
    variavel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Desativa uma variável (soft delete)"""
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para excluir variáveis")

    variavel = db.query(ExtractionVariable).filter(ExtractionVariable.id == variavel_id).first()
    if not variavel:
        raise HTTPException(status_code=404, detail="Variável não encontrada")

    # Verifica se está em uso em prompts
    uso_count = db.query(PromptVariableUsage).filter(
        PromptVariableUsage.variable_slug == variavel.slug
    ).count()

    if uso_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Variável está em uso por {uso_count} prompt(s). Remova os usos antes de desativar."
        )

    # Busca variáveis que dependem desta e remove a dependência
    variaveis_dependentes = db.query(ExtractionVariable).filter(
        ExtractionVariable.depends_on_variable == variavel.slug
    ).all()

    for v in variaveis_dependentes:
        v.depends_on_variable = None
        v.dependency_operator = None
        v.dependency_value = None
        v.atualizado_em = datetime.utcnow()

    # Busca perguntas que dependem desta e remove a dependência
    perguntas_dependentes = db.query(ExtractionQuestion).filter(
        ExtractionQuestion.depends_on_variable == variavel.slug
    ).all()

    for p in perguntas_dependentes:
        p.depends_on_variable = None
        p.dependency_operator = None
        p.dependency_value = None
        p.dependency_inferred = False
        p.atualizado_em = datetime.utcnow()

    # Desativa a variável
    variavel.ativo = False
    variavel.atualizado_em = datetime.utcnow()

    db.commit()

    logger.info(f"Variável desativada: slug={variavel.slug}, dependências removidas: {len(variaveis_dependentes)} variáveis, {len(perguntas_dependentes)} perguntas")

    return {
        "success": True,
        "message": "Variável desativada com sucesso",
        "dependencias_removidas": {
            "variaveis": len(variaveis_dependentes),
            "perguntas": len(perguntas_dependentes)
        }
    }


@router.post("/variaveis/{variavel_id}/reativar")
async def reativar_variavel(
    variavel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Reativa uma variável desativada"""
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para reativar variáveis")

    variavel = db.query(ExtractionVariable).filter(ExtractionVariable.id == variavel_id).first()
    if not variavel:
        raise HTTPException(status_code=404, detail="Variável não encontrada")

    variavel.ativo = True
    variavel.atualizado_em = datetime.utcnow()

    db.commit()

    logger.info(f"Variável reativada: slug={variavel.slug}")

    return {"success": True, "message": "Variável reativada com sucesso"}


@router.delete("/variaveis/{variavel_id}/permanente")
async def excluir_variavel_permanente(
    variavel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Exclui permanentemente uma variável (hard delete)"""
    # Verifica permissão - apenas admin
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem excluir permanentemente")

    variavel = db.query(ExtractionVariable).filter(ExtractionVariable.id == variavel_id).first()
    if not variavel:
        raise HTTPException(status_code=404, detail="Variável não encontrada")

    # Verifica se está em uso
    uso_count = db.query(PromptVariableUsage).filter(
        PromptVariableUsage.variable_slug == variavel.slug
    ).count()

    if uso_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Variável está em uso por {uso_count} prompt(s). Remova os usos antes de excluir."
        )

    # Remove dependências de variáveis que dependem desta
    variaveis_dependentes = db.query(ExtractionVariable).filter(
        ExtractionVariable.depends_on_variable == variavel.slug
    ).all()

    for v in variaveis_dependentes:
        v.depends_on_variable = None
        v.dependency_operator = None
        v.dependency_value = None
        v.atualizado_em = datetime.utcnow()

    # Remove dependências de perguntas que dependem desta
    perguntas_dependentes = db.query(ExtractionQuestion).filter(
        ExtractionQuestion.depends_on_variable == variavel.slug
    ).all()

    for p in perguntas_dependentes:
        p.depends_on_variable = None
        p.dependency_operator = None
        p.dependency_value = None
        p.dependency_inferred = False
        p.atualizado_em = datetime.utcnow()

    slug = variavel.slug
    db.delete(variavel)
    db.commit()

    logger.info(f"Variável excluída permanentemente: slug={slug}, dependências removidas: {len(variaveis_dependentes)} variáveis, {len(perguntas_dependentes)} perguntas")

    return {
        "success": True,
        "message": "Variável excluída permanentemente",
        "dependencias_removidas": {
            "variaveis": len(variaveis_dependentes),
            "perguntas": len(perguntas_dependentes)
        }
    }


# ============================================================================
# ENDPOINTS - TIPOS DE DADOS DISPONÍVEIS
# ============================================================================

@router.get("/tipos-variaveis")
async def listar_tipos_variaveis(
    current_user: User = Depends(get_current_active_user)
):
    """Lista os tipos de dados disponíveis para variáveis"""
    return [
        {"value": "text", "label": "Texto", "description": "Texto livre"},
        {"value": "number", "label": "Número", "description": "Valor numérico"},
        {"value": "date", "label": "Data", "description": "Data no formato YYYY-MM-DD"},
        {"value": "boolean", "label": "Sim/Não", "description": "Valor booleano"},
        {"value": "choice", "label": "Escolha Única", "description": "Uma opção entre várias"},
        {"value": "list", "label": "Lista", "description": "Lista de valores"},
        {"value": "currency", "label": "Valor Monetário", "description": "Valor em reais (R$)"}
    ]


# ============================================================================
# ENDPOINTS - REGRAS DETERMINÍSTICAS
# ============================================================================

class GenerateDeterministicRuleRequest(BaseModel):
    """Schema para requisição de geração de regra determinística"""
    condicao_texto: str = Field(..., description="Condição em linguagem natural")
    contexto: Optional[str] = Field(None, description="Contexto adicional (tipo de peça, grupo, etc)")


class SugestaoVariavel(BaseModel):
    """Sugestão para criar variável faltante"""
    slug: str = Field(..., description="Slug da variável sugerida")
    label_sugerido: str = Field(..., description="Label sugerido para a variável")
    tipo_sugerido: str = Field(..., description="Tipo sugerido (text, boolean, number, etc)")


class GenerateDeterministicRuleResponse(BaseModel):
    """Schema de resposta para geração de regra determinística"""
    success: bool
    regra: Optional[dict] = Field(None, description="AST JSON da regra")
    variaveis_usadas: Optional[List[str]] = Field(None, description="Lista de variáveis usadas na regra")
    regra_texto_original: Optional[str] = Field(None, description="Texto original da condição")
    erro: Optional[str] = None
    detalhes: Optional[List[str]] = Field(None, description="Detalhes do erro")
    variaveis_faltantes: Optional[List[str]] = Field(None, description="Variáveis mencionadas que não existem")
    sugestoes_variaveis: Optional[List[SugestaoVariavel]] = Field(None, description="Sugestões para criar variáveis faltantes")


class ValidateDeterministicRuleRequest(BaseModel):
    """Schema para validação de regra determinística"""
    regra: dict = Field(..., description="AST JSON da regra")


class ValidateDeterministicRuleResponse(BaseModel):
    """Schema de resposta para validação de regra"""
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    variaveis_faltantes: List[str] = []


class EvaluateDeterministicRuleRequest(BaseModel):
    """Schema para avaliação de regra determinística"""
    regra: dict = Field(..., description="AST JSON da regra")
    dados: dict = Field(..., description="Dados para avaliação")


class EvaluateDeterministicRuleResponse(BaseModel):
    """Schema de resposta para avaliação de regra"""
    resultado: bool
    erro: Optional[str] = None


@router.post("/regras-deterministicas/gerar", response_model=GenerateDeterministicRuleResponse)
async def gerar_regra_deterministica(
    data: GenerateDeterministicRuleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Gera uma regra determinística (AST JSON) a partir de uma condição em linguagem natural.

    Este endpoint:
    1. Recebe a condição em texto
    2. Busca as variáveis disponíveis no sistema
    3. Usa o Gemini 3 Flash Preview para converter em AST
    4. Valida se todas as variáveis usadas existem
    5. Retorna a regra estruturada
    """
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para gerar regras")

    from .services_deterministic import DeterministicRuleGenerator

    try:
        generator = DeterministicRuleGenerator(db)
        resultado = await generator.gerar_regra(
            condicao_texto=data.condicao_texto,
            contexto=data.contexto
        )

        if not resultado.get("success"):
            # Converte sugestões para o formato do schema
            sugestoes_raw = resultado.get("sugestoes_variaveis", [])
            sugestoes = [
                SugestaoVariavel(
                    slug=s.get("slug", ""),
                    label_sugerido=s.get("label_sugerido", ""),
                    tipo_sugerido=s.get("tipo_sugerido", "text")
                )
                for s in sugestoes_raw
            ] if sugestoes_raw else None

            return GenerateDeterministicRuleResponse(
                success=False,
                erro=resultado.get("erro"),
                detalhes=resultado.get("detalhes"),
                variaveis_faltantes=resultado.get("variaveis_faltantes"),
                sugestoes_variaveis=sugestoes
            )

        return GenerateDeterministicRuleResponse(
            success=True,
            regra=resultado.get("regra"),
            variaveis_usadas=resultado.get("variaveis_usadas"),
            regra_texto_original=resultado.get("regra_texto_original")
        )

    except Exception as e:
        logger.error(f"Erro ao gerar regra determinística: {e}")
        return GenerateDeterministicRuleResponse(
            success=False,
            erro=str(e)
        )


@router.post("/regras-deterministicas/validar", response_model=ValidateDeterministicRuleResponse)
async def validar_regra_deterministica(
    data: ValidateDeterministicRuleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Valida uma regra determinística (AST JSON).

    Verifica:
    - Estrutura do AST
    - Operadores válidos
    - Existência das variáveis referenciadas
    """
    from .services_deterministic import DeterministicRuleGenerator

    try:
        generator = DeterministicRuleGenerator(db)
        variaveis = generator._buscar_variaveis_disponiveis()
        resultado = generator._validar_regra(data.regra, variaveis)

        return ValidateDeterministicRuleResponse(
            valid=resultado.get("valid", False),
            errors=resultado.get("errors", []),
            warnings=[],
            variaveis_faltantes=resultado.get("variaveis_faltantes", [])
        )

    except Exception as e:
        logger.error(f"Erro ao validar regra: {e}")
        return ValidateDeterministicRuleResponse(
            valid=False,
            errors=[str(e)],
            warnings=[],
            variaveis_faltantes=[]
        )


@router.post("/regras-deterministicas/avaliar", response_model=EvaluateDeterministicRuleResponse)
async def avaliar_regra_deterministica(
    data: EvaluateDeterministicRuleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Avalia uma regra determinística com dados fornecidos.

    Útil para testar regras antes de salvá-las.
    """
    from .services_deterministic import DeterministicRuleEvaluator

    try:
        evaluator = DeterministicRuleEvaluator()
        resultado = evaluator.avaliar(data.regra, data.dados)

        return EvaluateDeterministicRuleResponse(
            resultado=resultado
        )

    except Exception as e:
        logger.error(f"Erro ao avaliar regra: {e}")
        return EvaluateDeterministicRuleResponse(
            resultado=False,
            erro=str(e)
        )


# ============================================================================
# ENDPOINTS - DEPENDÊNCIAS ENTRE PERGUNTAS
# ============================================================================

class DependencyConfig(BaseModel):
    """Schema para configuração de dependência"""
    depends_on: str = Field(..., description="Slug da variável da qual depende")
    operator: str = Field("equals", description="Operador: equals, not_equals, in_list, exists, etc.")
    value: Optional[Any] = Field(None, description="Valor esperado para a condição")


class SetDependencyRequest(BaseModel):
    """Schema para definir dependência em uma pergunta"""
    depends_on_variable: str = Field(..., description="Slug da variável da qual depende")
    dependency_operator: str = Field("equals", description="Operador de comparação")
    dependency_value: Optional[Any] = Field(None, description="Valor esperado")


class InferDependenciesRequest(BaseModel):
    """Schema para requisição de inferência de dependências"""
    categoria_id: int = Field(..., description="ID da categoria")


class InferDependenciesResponse(BaseModel):
    """Schema de resposta para inferência de dependências"""
    success: bool
    dependencias_inferidas: List[dict] = []
    grafo: Optional[dict] = None
    erro: Optional[str] = None


class ApplyDependenciesRequest(BaseModel):
    """Schema para aplicação de dependências inferidas"""
    categoria_id: int = Field(..., description="ID da categoria")
    dependencias: List[dict] = Field(..., description="Lista de dependências a aplicar")


class ApplyDependenciesResponse(BaseModel):
    """Schema de resposta para aplicação de dependências"""
    success: bool
    perguntas_atualizadas: List[dict] = []
    erro: Optional[str] = None


class DependencyGraphResponse(BaseModel):
    """Schema de resposta para grafo de dependências"""
    nodes: List[dict] = []
    edges: List[dict] = []
    hierarchy: dict = {}
    root_questions: List[dict] = []


class DependentQuestionsResponse(BaseModel):
    """Schema de resposta para perguntas dependentes"""
    perguntas: List[dict] = []


class SyncPerguntaTipo(BaseModel):
    """Dados para sincronizar tipo de uma pergunta"""
    pergunta_id: int = Field(..., description="ID da pergunta")
    tipo: str = Field(..., description="Tipo inferido pela IA")
    opcoes: Optional[List[str]] = Field(None, description="Opções se tipo for choice/list")


class SyncTiposRequest(BaseModel):
    """Request para sincronizar tipos das perguntas com o schema gerado"""
    categoria_id: int = Field(..., description="ID da categoria")
    mapeamento_variaveis: dict = Field(..., description="Mapeamento de pergunta_id para info da variável")


class SyncTiposResponse(BaseModel):
    """Response da sincronização de tipos"""
    success: bool = True
    perguntas_atualizadas: int = 0
    detalhes: List[dict] = []
    erro: Optional[str] = None


@router.get("/operadores-dependencia")
async def listar_operadores_dependencia(
    current_user: User = Depends(get_current_active_user)
):
    """Lista os operadores disponíveis para dependências"""
    return [
        {"value": "equals", "label": "Igual a", "description": "Valor exato"},
        {"value": "not_equals", "label": "Diferente de", "description": "Valor diferente"},
        {"value": "in_list", "label": "Está na lista", "description": "Um dos valores"},
        {"value": "not_in_list", "label": "Não está na lista", "description": "Nenhum dos valores"},
        {"value": "exists", "label": "Existe", "description": "Variável tem valor"},
        {"value": "not_exists", "label": "Não existe", "description": "Variável não tem valor"},
        {"value": "greater_than", "label": "Maior que", "description": "Para números"},
        {"value": "less_than", "label": "Menor que", "description": "Para números"}
    ]


@router.post("/dependencias/inferir", response_model=InferDependenciesResponse)
async def inferir_dependencias(
    data: InferDependenciesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Infere dependências entre perguntas de uma categoria usando IA.

    Este endpoint:
    1. Analisa todas as perguntas ativas da categoria
    2. Usa o Gemini para identificar dependências condicionais
    3. Retorna as dependências inferidas e um grafo de visualização
    """
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para inferir dependências")

    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == data.categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    try:
        service = DependencyInferenceService(db)
        resultado = await service.inferir_dependencias(data.categoria_id)

        if not resultado.get("success"):
            return InferDependenciesResponse(
                success=False,
                erro=resultado.get("erro")
            )

        return InferDependenciesResponse(
            success=True,
            dependencias_inferidas=resultado.get("dependencias_inferidas", []),
            grafo=resultado.get("grafo")
        )

    except Exception as e:
        logger.error(f"Erro ao inferir dependências: {e}")
        return InferDependenciesResponse(
            success=False,
            erro=str(e)
        )


@router.post("/dependencias/aplicar", response_model=ApplyDependenciesResponse)
async def aplicar_dependencias(
    data: ApplyDependenciesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Aplica dependências inferidas às perguntas.

    Este endpoint:
    1. Recebe a lista de dependências a aplicar
    2. Atualiza as perguntas com as dependências
    3. Retorna quais perguntas foram atualizadas
    """
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para aplicar dependências")

    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == data.categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    try:
        service = DependencyInferenceService(db)
        resultado = await service.aplicar_dependencias(data.categoria_id, data.dependencias)

        if not resultado.get("success"):
            return ApplyDependenciesResponse(
                success=False,
                erro=resultado.get("erro")
            )

        return ApplyDependenciesResponse(
            success=True,
            perguntas_atualizadas=resultado.get("perguntas_atualizadas", [])
        )

    except Exception as e:
        logger.error(f"Erro ao aplicar dependências: {e}")
        return ApplyDependenciesResponse(
            success=False,
            erro=str(e)
        )


@router.put("/perguntas/{pergunta_id}/dependencia")
async def definir_dependencia_pergunta(
    pergunta_id: int,
    data: SetDependencyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Define manualmente a dependência de uma pergunta.
    """
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para editar perguntas")

    pergunta = db.query(ExtractionQuestion).filter(ExtractionQuestion.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")

    # Valida operador
    operadores_validos = [e.value for e in DependencyOperator]
    if data.dependency_operator not in operadores_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Operador inválido. Use um de: {', '.join(operadores_validos)}"
        )

    # Atualiza dependência
    pergunta.depends_on_variable = data.depends_on_variable
    pergunta.dependency_operator = data.dependency_operator
    pergunta.dependency_value = data.dependency_value
    pergunta.dependency_inferred = False  # Definido manualmente
    pergunta.atualizado_por = current_user.id
    pergunta.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(pergunta)

    logger.info(f"Dependência definida para pergunta {pergunta_id}: {data.depends_on_variable}")

    return {
        "success": True,
        "pergunta_id": pergunta.id,
        "depends_on_variable": pergunta.depends_on_variable,
        "dependency_operator": pergunta.dependency_operator,
        "dependency_value": pergunta.dependency_value,
        "dependency_summary": pergunta.dependency_summary
    }


@router.delete("/perguntas/{pergunta_id}/dependencia")
async def remover_dependencia_pergunta(
    pergunta_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Remove a dependência de uma pergunta.
    """
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para editar perguntas")

    pergunta = db.query(ExtractionQuestion).filter(ExtractionQuestion.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")

    # Remove dependência
    pergunta.depends_on_variable = None
    pergunta.dependency_operator = None
    pergunta.dependency_value = None
    pergunta.dependency_config = None
    pergunta.dependency_inferred = False
    pergunta.atualizado_por = current_user.id
    pergunta.atualizado_em = datetime.utcnow()

    db.commit()

    logger.info(f"Dependência removida da pergunta {pergunta_id}")

    return {"success": True, "message": "Dependência removida com sucesso"}


@router.get("/categorias/{categoria_id}/grafo-dependencias", response_model=DependencyGraphResponse)
async def obter_grafo_dependencias(
    categoria_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna o grafo de dependências de uma categoria para visualização.

    Inclui:
    - Nós (perguntas/variáveis)
    - Arestas (dependências)
    - Hierarquia (árvore de dependências)
    - Perguntas raiz (sem dependência)
    """
    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    try:
        builder = DependencyGraphBuilder(db)
        grafo = builder.construir_grafo_categoria(categoria_id)

        return DependencyGraphResponse(
            nodes=grafo.get("nodes", []),
            edges=grafo.get("edges", []),
            hierarchy=grafo.get("hierarchy", {}),
            root_questions=grafo.get("root_questions", [])
        )

    except Exception as e:
        logger.error(f"Erro ao construir grafo: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/variaveis/{variable_slug}/dependentes", response_model=DependentQuestionsResponse)
async def obter_perguntas_dependentes(
    variable_slug: str,
    categoria_id: int = Query(..., description="ID da categoria"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna todas as perguntas que dependem de uma variável específica.
    """
    # Verifica se a categoria existe
    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    try:
        builder = DependencyGraphBuilder(db)
        perguntas = builder.obter_perguntas_dependentes(variable_slug, categoria_id)

        return DependentQuestionsResponse(perguntas=perguntas)

    except Exception as e:
        logger.error(f"Erro ao buscar dependentes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/perguntas/{pergunta_id}/cadeia-dependencias")
async def obter_cadeia_dependencias(
    pergunta_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna a cadeia completa de dependências de uma pergunta.

    Exemplo: ["medicamento", "registro_anvisa", "incorporado_sus"]
    """
    pergunta = db.query(ExtractionQuestion).filter(ExtractionQuestion.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")

    try:
        builder = DependencyGraphBuilder(db)
        cadeia = builder.obter_cadeia_dependencias(pergunta_id)

        return {
            "pergunta_id": pergunta_id,
            "cadeia": cadeia,
            "profundidade": len(cadeia)
        }

    except Exception as e:
        logger.error(f"Erro ao obter cadeia: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dependencias/avaliar-visibilidade")
async def avaliar_visibilidade_pergunta(
    pergunta_id: int = Query(..., description="ID da pergunta"),
    dados: dict = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Avalia se uma pergunta deve estar visível com base nos dados fornecidos.

    Útil para testar condições de visibilidade no frontend.
    """
    pergunta = db.query(ExtractionQuestion).filter(ExtractionQuestion.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")

    if dados is None:
        dados = {}

    try:
        evaluator = DependencyEvaluator()
        visivel = evaluator.avaliar_visibilidade(pergunta, dados)

        return {
            "pergunta_id": pergunta_id,
            "visivel": visivel,
            "is_conditional": pergunta.is_conditional,
            "dependency_summary": pergunta.dependency_summary
        }

    except Exception as e:
        logger.error(f"Erro ao avaliar visibilidade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/perguntas/sync-tipos", response_model=SyncTiposResponse)
async def sincronizar_tipos_perguntas(
    data: SyncTiposRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Sincroniza tipos, slugs e opções das perguntas com o mapeamento gerado pela IA.

    Chamado após "Aceitar e Usar" o JSON gerado pela IA para:
    1. Atualizar nome_variavel_sugerido (slug) das perguntas que não tinham
    2. Atualizar tipo_sugerido das perguntas que estavam como "ia_decide"
    3. Atualizar opcoes_sugeridas quando a IA definir options
    """
    # Verifica permissão
    if current_user.role != "admin" and not current_user.tem_permissao("edit_prompts"):
        raise HTTPException(status_code=403, detail="Sem permissão para editar perguntas")

    try:
        perguntas_atualizadas = 0
        detalhes = []

        # Busca namespace da categoria
        categoria = db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.id == data.categoria_id
        ).first()
        namespace = categoria.namespace if categoria else ""

        # Mapeamento de tipos da IA para tipos do modelo
        tipo_mapping = {
            "text": "text",
            "string": "text",
            "number": "number",
            "integer": "number",
            "float": "number",
            "date": "date",
            "datetime": "date",
            "boolean": "boolean",
            "bool": "boolean",
            "choice": "choice",
            "enum": "choice",
            "list": "list",
            "array": "list",
            "currency": "currency",
            "money": "currency"
        }

        for pergunta_id_str, info in data.mapeamento_variaveis.items():
            try:
                pergunta_id = int(pergunta_id_str)
            except ValueError:
                continue

            pergunta = db.query(ExtractionQuestion).filter(
                ExtractionQuestion.id == pergunta_id,
                ExtractionQuestion.categoria_id == data.categoria_id
            ).first()

            if not pergunta:
                continue

            alteracoes = {}

            # Atualiza slug (nome_variavel_sugerido) se não tinha
            slug_ia = info.get("slug")
            if slug_ia and not pergunta.nome_variavel_sugerido:
                # Remove namespace se presente para armazenar slug base
                slug_base = slug_ia
                if namespace and slug_ia.startswith(f"{namespace}_"):
                    slug_base = slug_ia[len(namespace) + 1:]
                pergunta.nome_variavel_sugerido = slug_base
                alteracoes["slug"] = slug_base

            # Só atualiza tipo se estava como "ia_decide" ou vazio
            tipo_ia = info.get("tipo") or info.get("type")
            tipo_normalizado = tipo_mapping.get(tipo_ia, tipo_ia) if tipo_ia else None

            if tipo_normalizado and (not pergunta.tipo_sugerido or pergunta.tipo_sugerido == "ia_decide"):
                pergunta.tipo_sugerido = tipo_normalizado
                alteracoes["tipo"] = tipo_normalizado

            # Atualiza opções se a IA definiu e a pergunta não tinha
            opcoes_ia = info.get("options") or info.get("opcoes")
            if opcoes_ia and isinstance(opcoes_ia, list):
                # Se não tinha opções ou estava vazio, usa as da IA
                if not pergunta.opcoes_sugeridas or len(pergunta.opcoes_sugeridas) == 0:
                    pergunta.opcoes_sugeridas = opcoes_ia
                    alteracoes["opcoes"] = opcoes_ia

            if alteracoes:
                pergunta.atualizado_por = current_user.id
                pergunta.atualizado_em = datetime.utcnow()
                perguntas_atualizadas += 1
                detalhes.append({
                    "pergunta_id": pergunta_id,
                    "pergunta": pergunta.pergunta[:50],
                    "alteracoes": alteracoes
                })

        db.commit()

        logger.info(f"Tipos sincronizados: {perguntas_atualizadas} perguntas atualizadas")

        return SyncTiposResponse(
            success=True,
            perguntas_atualizadas=perguntas_atualizadas,
            detalhes=detalhes
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Erro ao sincronizar tipos: {e}")
        return SyncTiposResponse(
            success=False,
            erro=str(e)
        )
