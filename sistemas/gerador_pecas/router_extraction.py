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
from sqlalchemy import func
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
    db.commit()
    db.refresh(pergunta)

    logger.info(f"Pergunta de extração criada: id={pergunta.id}, categoria={categoria.nome}")

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

    db.commit()
    db.refresh(pergunta)

    categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == pergunta.categoria_id).first()

    logger.info(f"Pergunta de extração atualizada: id={pergunta.id}")

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
    for field, value in update_data.items():
        setattr(variavel, field, value)

    variavel.atualizado_em = datetime.utcnow()

    db.commit()
    db.refresh(variavel)

    categoria = None
    if variavel.categoria_id:
        categoria = db.query(CategoriaResumoJSON).filter(CategoriaResumoJSON.id == variavel.categoria_id).first()

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
