# sistemas/gerador_pecas/router_teste_ativacao.py
"""
Router para ambiente de teste de ativação de prompts modulares.

Este módulo implementa a interface de teste/simulação de ativação de módulos,
permitindo validar regras determinísticas com variáveis geradas via IA
ou configuradas manualmente.

IMPORTANTE: Usa exatamente o código de produção (avaliar_ativacao_prompt)
para garantir fidelidade aos resultados reais.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.connection import get_db
from auth.models import User
from auth.dependencies import get_current_active_user

from sistemas.gerador_pecas.models_teste_ativacao import CenarioTesteAtivacao
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
from sistemas.gerador_pecas.models_extraction import ExtractionVariable
from sistemas.gerador_pecas.services_process_variables import ProcessVariableResolver
from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca
from admin.models_prompt_groups import PromptGroup

# Código de produção para avaliação de ativação
from sistemas.gerador_pecas.services_deterministic import (
    avaliar_ativacao_prompt,
    pode_avaliar_regra,
    DeterministicRuleEvaluator
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teste-ativacao", tags=["Teste de Ativacao de Modulos"])


# ==========================
# Schemas
# ==========================

class GerarVariaveisRequest(BaseModel):
    """Request para gerar variáveis a partir de descrição textual"""
    descricao_situacao: str = Field(..., description="Descrição textual da situação processual")
    categorias_ids: List[int] = Field(default=[], description="IDs das categorias para filtrar variáveis")
    tipo_peca: Optional[str] = Field(None, description="Tipo de peça (ex: contestacao)")


class GerarVariaveisResponse(BaseModel):
    """Response com variáveis geradas via IA"""
    variaveis_extracao: Dict[str, Any]
    variaveis_processo: Dict[str, Any]
    sucesso: bool
    erro: Optional[str] = None


class SimularRequest(BaseModel):
    """Request para simular ativação de módulos"""
    variaveis_extracao: Dict[str, Any] = Field(default={}, description="Variáveis extraídas de documentos")
    variaveis_processo: Dict[str, Any] = Field(default={}, description="Variáveis do processo")
    tipo_peca: str = Field(..., description="Tipo de peça (ex: contestacao)")
    categorias_ids: List[int] = Field(default=[], description="IDs das categorias para filtrar módulos")


class ModuloResultado(BaseModel):
    """Resultado da avaliação de um módulo"""
    id: int
    nome: str
    titulo: str
    grupo: Optional[str] = None
    subgrupo: Optional[str] = None
    ativado: Optional[bool]
    modo: str  # deterministic, deterministic_tipo_peca, llm
    regra_usada: Optional[str] = None  # global_primaria, especifica_contestacao, secundaria
    detalhes: Optional[str] = None
    variaveis_avaliadas: List[str] = []
    variaveis_faltantes: List[str] = []  # Variáveis que faltam para avaliar a regra
    condicao_falha: Optional[str] = None
    valores_usados: Dict[str, Any] = {}


class SimularResponse(BaseModel):
    """Response da simulação de ativação"""
    modulos_ativados: List[ModuloResultado]
    modulos_nao_ativados: List[ModuloResultado]
    modulos_indeterminados: List[ModuloResultado]  # Quando modo = llm ou variável não existe
    totais: Dict[str, int]
    variaveis_consolidadas: Dict[str, Any]
    configuracao: Dict[str, Any]


class CenarioCreate(BaseModel):
    """Schema para criação de cenário"""
    nome: str = Field(..., max_length=200)
    descricao_situacao: Optional[str] = None
    variaveis_extracao: Dict[str, Any] = Field(default={})
    variaveis_processo: Dict[str, Any] = Field(default={})
    tipo_peca: Optional[str] = None
    categorias_selecionadas: List[int] = Field(default=[])
    modulos_esperados_ativados: List[int] = Field(default=[])


class CenarioResponse(BaseModel):
    """Schema de resposta para cenário"""
    id: int
    nome: str
    descricao_situacao: Optional[str]
    variaveis_extracao: Dict[str, Any]
    variaveis_processo: Dict[str, Any]
    tipo_peca: Optional[str]
    categorias_selecionadas: List[int]
    modulos_esperados_ativados: List[int]
    criado_em: Optional[str]
    atualizado_em: Optional[str]


# ==========================
# Funções auxiliares
# ==========================

def verificar_permissao(user: User):
    """Verifica se usuário tem permissão para testar módulos"""
    if not user.tem_permissao("editar_prompts"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para testar ativação de módulos"
        )


def carregar_modulos_para_tipo_peca(db: Session, tipo_peca: str, categorias_ids: List[int] = None) -> List[PromptModulo]:
    """
    Carrega módulos de conteúdo disponíveis para um tipo de peça.

    Args:
        db: Sessão do banco
        tipo_peca: Tipo de peça (ex: contestacao)
        categorias_ids: IDs das categorias para filtrar (opcional)

    Returns:
        Lista de módulos de conteúdo ativos
    """
    query = db.query(PromptModulo).filter(
        PromptModulo.tipo == "conteudo",
        PromptModulo.ativo == True
    )

    # Ordena por grupo e ordem
    query = query.order_by(PromptModulo.group_id, PromptModulo.ordem)

    return query.all()


# ==========================
# Endpoints
# ==========================

@router.get("/categorias-extracao")
async def listar_categorias_extracao(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista categorias de extração ativas com suas variáveis.
    """
    verificar_permissao(current_user)

    categorias = db.query(CategoriaResumoJSON).filter(
        CategoriaResumoJSON.ativo == True
    ).order_by(CategoriaResumoJSON.ordem, CategoriaResumoJSON.nome).all()

    resultado = []
    for cat in categorias:
        # Busca variáveis associadas a esta categoria
        variaveis = db.query(ExtractionVariable).filter(
            ExtractionVariable.categoria_id == cat.id,
            ExtractionVariable.ativo == True
        ).all()

        resultado.append({
            "id": cat.id,
            "nome": cat.nome,
            "titulo": cat.titulo,
            "descricao": cat.descricao,
            "variaveis": [
                {
                    "slug": v.slug,
                    "label": v.label,
                    "tipo": v.tipo,
                    "descricao": v.descricao
                }
                for v in variaveis
            ]
        })

    return resultado


@router.get("/tipos-peca")
async def listar_tipos_peca(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista tipos de peça disponíveis.
    """
    verificar_permissao(current_user)

    from sistemas.gerador_pecas.models_config_pecas import TipoPeca

    tipos = db.query(TipoPeca).filter(TipoPeca.ativo == True).order_by(TipoPeca.ordem).all()

    logger.info(f"[TIPOS-PECA] Encontrados {len(tipos)} tipos de peca ativos")

    return [
        {
            "id": t.id,
            "slug": t.nome,  # 'nome' é o identificador (ex: 'contestacao')
            "nome": t.titulo,  # 'titulo' é o nome legível (ex: 'Contestação')
            "descricao": t.descricao
        }
        for t in tipos
    ]


@router.get("/variaveis-processo")
async def listar_variaveis_processo(
    current_user: User = Depends(get_current_active_user)
):
    """
    Lista definições de variáveis derivadas do processo.
    """
    verificar_permissao(current_user)

    definitions = ProcessVariableResolver.get_all_definitions()

    return [
        {
            "slug": d.slug,
            "label": d.label,
            "tipo": d.tipo,
            "descricao": d.descricao
        }
        for d in definitions
    ]


@router.post("/gerar-variaveis", response_model=GerarVariaveisResponse)
async def gerar_variaveis(
    request: GerarVariaveisRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Gera variáveis de extração e processo a partir de descrição textual via IA.

    A IA analisa a descrição da situação processual e gera valores para
    as variáveis relevantes.
    """
    verificar_permissao(current_user)

    from services.gemini_service import gemini_service, get_thinking_level

    try:
        # Coleta todas as variáveis disponíveis
        variaveis_extracao_disponiveis = []

        # Variáveis de extração (de documentos)
        query = db.query(ExtractionVariable).filter(ExtractionVariable.ativo == True)
        if request.categorias_ids:
            query = query.filter(ExtractionVariable.categoria_id.in_(request.categorias_ids))

        for v in query.all():
            variaveis_extracao_disponiveis.append({
                "slug": v.slug,
                "label": v.label,
                "tipo": v.tipo,
                "descricao": v.descricao,
                "categoria": v.categoria.titulo if v.categoria else None
            })

        # Variáveis de processo
        variaveis_processo_disponiveis = [
            {
                "slug": d.slug,
                "label": d.label,
                "tipo": d.tipo,
                "descricao": d.descricao
            }
            for d in ProcessVariableResolver.get_all_definitions()
        ]

        # Monta prompt para IA
        prompt = f"""Você é um assistente especializado em direito administrativo e processual.

Analise a seguinte descrição de uma situação processual e gere valores para as variáveis listadas.

## Descrição da Situação
{request.descricao_situacao}

## Variáveis de Extração (de documentos)
{json.dumps(variaveis_extracao_disponiveis, indent=2, ensure_ascii=False)}

## Variáveis de Processo
{json.dumps(variaveis_processo_disponiveis, indent=2, ensure_ascii=False)}

## Instruções
1. Analise a descrição e identifique quais variáveis podem ser preenchidas
2. Para variáveis boolean, use true/false
3. Para variáveis number, use valores numéricos
4. Para variáveis text, use strings
5. Para variáveis enum, use uma das opções se mencionadas
6. Se uma variável não pode ser determinada pela descrição, omita-a ou use null
7. Seja conservador: só preencha variáveis que podem ser claramente inferidas

## Formato de Resposta
Responda APENAS com um JSON válido no seguinte formato:
```json
{{
  "variaveis_extracao": {{
    "slug_variavel": valor,
    ...
  }},
  "variaveis_processo": {{
    "slug_variavel": valor,
    ...
  }}
}}
```
"""

        thinking_level = get_thinking_level(db, "gerador_pecas")

        response = await gemini_service.generate(
            prompt=prompt,
            model="gemini-3-flash-preview",
            temperature=0.1,
            max_tokens=4000,
            thinking_level=thinking_level
        )

        if not response.success:
            return GerarVariaveisResponse(
                variaveis_extracao={},
                variaveis_processo={},
                sucesso=False,
                erro=response.error
            )

        # Extrai JSON da resposta
        content = response.content

        # Tenta encontrar JSON na resposta
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Tenta parsear diretamente
            json_str = content

        try:
            resultado = json.loads(json_str)
            return GerarVariaveisResponse(
                variaveis_extracao=resultado.get("variaveis_extracao", {}),
                variaveis_processo=resultado.get("variaveis_processo", {}),
                sucesso=True
            )
        except json.JSONDecodeError as e:
            logger.error(f"Erro ao parsear JSON da IA: {e}")
            return GerarVariaveisResponse(
                variaveis_extracao={},
                variaveis_processo={},
                sucesso=False,
                erro=f"Erro ao parsear resposta da IA: {str(e)}"
            )

    except Exception as e:
        logger.error(f"Erro ao gerar variáveis: {e}")
        return GerarVariaveisResponse(
            variaveis_extracao={},
            variaveis_processo={},
            sucesso=False,
            erro=str(e)
        )


@router.post("/simular", response_model=SimularResponse)
async def simular_ativacao(
    request: SimularRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Simula a ativação de módulos usando EXATAMENTE o código de produção.

    CRITICO: Esta função usa avaliar_ativacao_prompt() de produção
    para garantir fidelidade aos resultados reais.
    """
    verificar_permissao(current_user)

    # Import de modelos necessários para debug
    from admin.models_prompts import RegraDeterministicaTipoPeca

    # Consolida variáveis
    dados_consolidados = {
        **request.variaveis_extracao,
        **request.variaveis_processo
    }

    logger.info(f"[SIMULAR] Tipo de peça: {request.tipo_peca}")
    logger.info(f"[SIMULAR] Variáveis consolidadas ({len(dados_consolidados)}): {list(dados_consolidados.keys())}")

    # Carrega módulos
    modulos = carregar_modulos_para_tipo_peca(db, request.tipo_peca, request.categorias_ids)
    logger.info(f"[SIMULAR] Total de módulos carregados: {len(modulos)}")

    # Carrega grupos para exibição
    grupos = {g.id: g.name for g in db.query(PromptGroup).all()}

    modulos_ativados = []
    modulos_nao_ativados = []
    modulos_indeterminados = []

    for modulo in modulos:
        # ================================================================
        # DEBUG: Informações do módulo antes da avaliação
        # ================================================================
        # Busca regras específicas por tipo de peça
        regras_tipo_peca = db.query(RegraDeterministicaTipoPeca).filter(
            RegraDeterministicaTipoPeca.modulo_id == modulo.id,
            RegraDeterministicaTipoPeca.ativo == True
        ).all()

        tem_regra_global = bool(modulo.regra_deterministica and isinstance(modulo.regra_deterministica, dict) and modulo.regra_deterministica.get("type"))
        tem_regra_especifica = any(r.regra_deterministica for r in regras_tipo_peca)
        regra_especifica_tipo_atual = next(
            (r for r in regras_tipo_peca if r.tipo_peca == request.tipo_peca),
            None
        )

        logger.info(
            f"[SIMULAR] Módulo {modulo.id} ({modulo.nome}): "
            f"modo_ativacao={modulo.modo_ativacao}, "
            f"tem_regra_global={tem_regra_global}, "
            f"tem_regra_especifica={tem_regra_especifica}, "
            f"regras_tipo_peca=[{', '.join(r.tipo_peca for r in regras_tipo_peca)}], "
            f"tem_regra_para_{request.tipo_peca}={regra_especifica_tipo_atual is not None}"
        )

        if regra_especifica_tipo_atual:
            logger.info(f"[SIMULAR] Módulo {modulo.id}: Regra específica {request.tipo_peca} = {regra_especifica_tipo_atual.regra_deterministica}")

        # ================================================================
        # USA EXATAMENTE O CODIGO DE PRODUCAO - NAO DUPLICAR!
        # ================================================================
        resultado = avaliar_ativacao_prompt(
            prompt_id=modulo.id,
            modo_ativacao=modulo.modo_ativacao,
            regra_deterministica=modulo.regra_deterministica,
            dados_extracao=dados_consolidados,
            db=db,
            regra_secundaria=modulo.regra_deterministica_secundaria,
            fallback_habilitado=modulo.fallback_habilitado,
            tipo_peca=request.tipo_peca
        )

        logger.info(f"[SIMULAR] Módulo {modulo.id} resultado: {resultado}")

        # Monta resultado do módulo
        grupo_nome = grupos.get(modulo.group_id) if modulo.group_id else None

        # Extrai variáveis usadas na avaliação
        variaveis_avaliadas = []
        valores_usados = {}

        if resultado.get("regras_avaliadas"):
            for regra in resultado["regras_avaliadas"]:
                vars_regra = regra.get("variaveis", [])
                variaveis_avaliadas.extend(vars_regra)
                for v in vars_regra:
                    if v in dados_consolidados:
                        valores_usados[v] = dados_consolidados[v]

        # Adiciona info de debug nos detalhes
        debug_info = ""
        if tem_regra_global or tem_regra_especifica:
            debug_info = f" [DEBUG: global={tem_regra_global}, especifica_{request.tipo_peca}={regra_especifica_tipo_atual is not None}]"

        # Extrai variáveis faltantes do resultado
        variaveis_faltantes = resultado.get("variaveis_faltantes", [])

        modulo_resultado = ModuloResultado(
            id=modulo.id,
            nome=modulo.nome,
            titulo=modulo.titulo,
            grupo=grupo_nome,
            subgrupo=None,
            ativado=resultado.get("ativar"),
            modo=resultado.get("modo", "unknown"),
            regra_usada=resultado.get("regra_usada"),
            detalhes=(resultado.get("detalhes") or "") + debug_info,
            variaveis_avaliadas=list(set(variaveis_avaliadas)),
            variaveis_faltantes=variaveis_faltantes,
            condicao_falha=None if resultado.get("ativar") else resultado.get("detalhes"),
            valores_usados=valores_usados
        )

        if resultado.get("ativar") is True:
            modulos_ativados.append(modulo_resultado)
        elif resultado.get("ativar") is False:
            modulos_nao_ativados.append(modulo_resultado)
        else:
            # ativar é None - modo LLM ou variável não existe
            modulos_indeterminados.append(modulo_resultado)

    return SimularResponse(
        modulos_ativados=modulos_ativados,
        modulos_nao_ativados=modulos_nao_ativados,
        modulos_indeterminados=modulos_indeterminados,
        totais={
            "total": len(modulos),
            "ativados": len(modulos_ativados),
            "nao_ativados": len(modulos_nao_ativados),
            "indeterminados": len(modulos_indeterminados)
        },
        variaveis_consolidadas=dados_consolidados,
        configuracao={
            "tipo_peca": request.tipo_peca,
            "categorias_ids": request.categorias_ids,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


@router.post("/cenarios", response_model=CenarioResponse)
async def criar_cenario(
    cenario: CenarioCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Salva um cenário de teste para reutilização.
    """
    verificar_permissao(current_user)

    novo_cenario = CenarioTesteAtivacao(
        usuario_id=current_user.id,
        nome=cenario.nome,
        descricao_situacao=cenario.descricao_situacao,
        variaveis_extracao=cenario.variaveis_extracao,
        variaveis_processo=cenario.variaveis_processo,
        tipo_peca=cenario.tipo_peca,
        categorias_selecionadas=cenario.categorias_selecionadas,
        modulos_esperados_ativados=cenario.modulos_esperados_ativados
    )

    db.add(novo_cenario)
    db.commit()
    db.refresh(novo_cenario)

    return CenarioResponse(**novo_cenario.to_dict())


@router.get("/cenarios", response_model=List[CenarioResponse])
async def listar_cenarios(
    tipo_peca: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista cenários de teste do usuário.
    """
    verificar_permissao(current_user)

    query = db.query(CenarioTesteAtivacao).filter(
        CenarioTesteAtivacao.usuario_id == current_user.id
    )

    if tipo_peca:
        query = query.filter(CenarioTesteAtivacao.tipo_peca == tipo_peca)

    cenarios = query.order_by(CenarioTesteAtivacao.atualizado_em.desc()).all()

    return [CenarioResponse(**c.to_dict()) for c in cenarios]


@router.get("/cenarios/{cenario_id}", response_model=CenarioResponse)
async def obter_cenario(
    cenario_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obtém um cenário específico.
    """
    verificar_permissao(current_user)

    cenario = db.query(CenarioTesteAtivacao).filter(
        CenarioTesteAtivacao.id == cenario_id,
        CenarioTesteAtivacao.usuario_id == current_user.id
    ).first()

    if not cenario:
        raise HTTPException(status_code=404, detail="Cenário não encontrado")

    return CenarioResponse(**cenario.to_dict())


@router.put("/cenarios/{cenario_id}", response_model=CenarioResponse)
async def atualizar_cenario(
    cenario_id: int,
    dados: CenarioCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Atualiza um cenário existente.
    """
    verificar_permissao(current_user)

    cenario = db.query(CenarioTesteAtivacao).filter(
        CenarioTesteAtivacao.id == cenario_id,
        CenarioTesteAtivacao.usuario_id == current_user.id
    ).first()

    if not cenario:
        raise HTTPException(status_code=404, detail="Cenário não encontrado")

    cenario.nome = dados.nome
    cenario.descricao_situacao = dados.descricao_situacao
    cenario.variaveis_extracao = dados.variaveis_extracao
    cenario.variaveis_processo = dados.variaveis_processo
    cenario.tipo_peca = dados.tipo_peca
    cenario.categorias_selecionadas = dados.categorias_selecionadas
    cenario.modulos_esperados_ativados = dados.modulos_esperados_ativados

    db.commit()
    db.refresh(cenario)

    return CenarioResponse(**cenario.to_dict())


@router.delete("/cenarios/{cenario_id}")
async def excluir_cenario(
    cenario_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Remove um cenário de teste.
    """
    verificar_permissao(current_user)

    cenario = db.query(CenarioTesteAtivacao).filter(
        CenarioTesteAtivacao.id == cenario_id,
        CenarioTesteAtivacao.usuario_id == current_user.id
    ).first()

    if not cenario:
        raise HTTPException(status_code=404, detail="Cenário não encontrado")

    db.delete(cenario)
    db.commit()

    return {"excluido": True}


@router.get("/debug/modulo/{modulo_id}")
async def debug_modulo(
    modulo_id: int,
    tipo_peca: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Endpoint de DEBUG para investigar um módulo específico.

    Retorna informações detalhadas sobre:
    - Configuração do módulo
    - Regras determinísticas (global e por tipo de peça)
    - Modo de ativação calculado
    """
    verificar_permissao(current_user)

    from admin.models_prompts import RegraDeterministicaTipoPeca
    from sistemas.gerador_pecas.services_deterministic import (
        resolve_activation_mode_from_db,
        tem_regras_deterministicas,
        _extrair_variaveis_regra
    )

    # Busca o módulo
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    if not modulo:
        raise HTTPException(status_code=404, detail="Módulo não encontrado")

    # Busca regras específicas por tipo de peça
    regras_tipo_peca = db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.modulo_id == modulo_id
    ).all()

    # Regra específica para o tipo atual
    regra_tipo_atual = next(
        (r for r in regras_tipo_peca if r.tipo_peca == tipo_peca and r.ativo),
        None
    )

    # Resolve modo de ativação
    modo_calculado = resolve_activation_mode_from_db(
        db=db,
        modulo_id=modulo_id,
        modo_ativacao_salvo=modulo.modo_ativacao,
        regra_primaria=modulo.regra_deterministica,
        regra_secundaria=modulo.regra_deterministica_secundaria,
        fallback_habilitado=modulo.fallback_habilitado
    )

    # Verifica se tem regras
    regras_tipo_peca_dicts = [
        {"regra_deterministica": r.regra_deterministica, "tipo_peca": r.tipo_peca}
        for r in regras_tipo_peca if r.ativo and r.regra_deterministica
    ]

    tem_regras = tem_regras_deterministicas(
        regra_primaria=modulo.regra_deterministica,
        regra_secundaria=modulo.regra_deterministica_secundaria,
        fallback_habilitado=modulo.fallback_habilitado,
        regras_tipo_peca=regras_tipo_peca_dicts
    )

    # Extrai variáveis necessárias
    vars_global = []
    vars_especifica = []

    if modulo.regra_deterministica:
        try:
            vars_global = list(_extrair_variaveis_regra(modulo.regra_deterministica))
        except Exception as e:
            vars_global = [f"ERRO: {e}"]

    if regra_tipo_atual and regra_tipo_atual.regra_deterministica:
        try:
            vars_especifica = list(_extrair_variaveis_regra(regra_tipo_atual.regra_deterministica))
        except Exception as e:
            vars_especifica = [f"ERRO: {e}"]

    return {
        "modulo": {
            "id": modulo.id,
            "nome": modulo.nome,
            "titulo": modulo.titulo,
            "tipo": modulo.tipo,
            "ativo": modulo.ativo,
            "modo_ativacao_salvo": modulo.modo_ativacao,
            "modo_ativacao_calculado": modo_calculado,
            "fallback_habilitado": modulo.fallback_habilitado
        },
        "regra_global": {
            "existe": bool(modulo.regra_deterministica),
            "ast": modulo.regra_deterministica,
            "texto_original": modulo.regra_texto_original,
            "variaveis_necessarias": vars_global
        },
        "regra_secundaria": {
            "existe": bool(modulo.regra_deterministica_secundaria),
            "ast": modulo.regra_deterministica_secundaria,
            "fallback_habilitado": modulo.fallback_habilitado
        },
        "regras_tipo_peca": [
            {
                "tipo_peca": r.tipo_peca,
                "ativo": r.ativo,
                "ast": r.regra_deterministica,
                "texto_original": r.regra_texto_original
            }
            for r in regras_tipo_peca
        ],
        "regra_para_tipo_atual": {
            "tipo_peca": tipo_peca,
            "existe": regra_tipo_atual is not None,
            "ativa": regra_tipo_atual.ativo if regra_tipo_atual else None,
            "ast": regra_tipo_atual.regra_deterministica if regra_tipo_atual else None,
            "variaveis_necessarias": vars_especifica
        },
        "analise": {
            "tem_alguma_regra_deterministica": tem_regras,
            "modo_que_sera_usado": modo_calculado,
            "sera_avaliado_deterministicamente": modo_calculado == "deterministic",
            "regra_que_sera_usada": (
                f"especifica_{tipo_peca}" if regra_tipo_atual and regra_tipo_atual.ativo
                else "global" if modulo.regra_deterministica
                else "nenhuma"
            )
        }
    }


@router.get("/cenarios-predefinidos")
async def listar_cenarios_predefinidos(
    current_user: User = Depends(get_current_active_user)
):
    """
    Lista cenários pré-definidos de exemplo.
    """
    verificar_permissao(current_user)

    # Cenários de exemplo para facilitar testes
    return [
        {
            "nome": "Medicamento nao incorporado SUS",
            "descricao_situacao": "Acao para Pembrolizumabe (melanoma). Nao incorporado ao SUS. Valor R$ 450.000. Estado no polo passivo.",
            "tipo_peca": "contestacao",
            "variaveis_extracao": {
                "peticao_inicial_medicamento_incorporado_sus": False,
                "pareceres_analisou_medicamento": True,
                "pareceres_patologia_diversa_incorporada": False
            },
            "variaveis_processo": {
                "valor_causa_numerico": 450000.0,
                "valor_causa_superior_210sm": True,
                "estado_polo_passivo": True
            }
        },
        {
            "nome": "Cirurgia - 3 orcamentos",
            "descricao_situacao": "Artroplastia de quadril. 3 orcamentos. NAT confirmou. SUS oferece. Valor R$ 85.000.",
            "tipo_peca": "contestacao",
            "variaveis_extracao": {
                "pareceres_analisou_cirurgia": True,
                "pareceres_cirurgia_ofertada_sus": True,
                "peticao_inicial_quantidade_orcamentos": 3
            },
            "variaveis_processo": {
                "valor_causa_numerico": 85000.0,
                "valor_causa_inferior_60sm": True,
                "estado_polo_passivo": True
            }
        },
        {
            "nome": "Medicamento experimental",
            "descricao_situacao": "Pedido de medicamento em fase experimental (fase 2 de estudos clinicos). Valor R$ 200.000.",
            "tipo_peca": "contestacao",
            "variaveis_extracao": {
                "pareceres_medicamento_experimental": True,
                "pareceres_fase_estudos_clinicos": "fase_2"
            },
            "variaveis_processo": {
                "valor_causa_numerico": 200000.0,
                "estado_polo_passivo": True
            }
        },
        {
            "nome": "Tratamento ofertado pelo SUS",
            "descricao_situacao": "Autor solicita tratamento que ja e oferecido pelo SUS. Valor da causa R$ 30.000.",
            "tipo_peca": "contestacao",
            "variaveis_extracao": {
                "pareceres_tratamento_ofertado_sus": True
            },
            "variaveis_processo": {
                "valor_causa_numerico": 30000.0,
                "valor_causa_inferior_60sm": True,
                "estado_polo_passivo": True
            }
        }
    ]


class RelatorioAtivacaoRequest(BaseModel):
    """Request para gerar relatório de ativação de um módulo"""
    modulo_id: int
    tipo_peca: str
    variaveis_fornecidas: Dict[str, Any] = Field(default={})
    resultado_avaliacao: Dict[str, Any] = Field(default={})


class RelatorioAtivacaoResponse(BaseModel):
    """Response com relatório gerado via LLM"""
    relatorio: str
    sucesso: bool
    erro: Optional[str] = None


@router.post("/relatorio-ativacao", response_model=RelatorioAtivacaoResponse)
async def gerar_relatorio_ativacao(
    request: RelatorioAtivacaoRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Gera um relatório detalhado via LLM explicando por que um módulo
    não foi ativado ou ficou indeterminado.

    O relatório inclui:
    - Variáveis fornecidas pelo usuário
    - Condições de ativação do módulo
    - Análise de por que não ativou
    - Sugestões para ativação
    """
    verificar_permissao(current_user)

    from services.gemini_service import gemini_service
    from sistemas.gerador_pecas.services_deterministic import _extrair_variaveis_regra

    try:
        # Busca o módulo
        modulo = db.query(PromptModulo).filter(PromptModulo.id == request.modulo_id).first()
        if not modulo:
            return RelatorioAtivacaoResponse(
                relatorio="",
                sucesso=False,
                erro="Módulo não encontrado"
            )

        # Busca regras específicas por tipo de peça
        regras_tipo_peca = db.query(RegraDeterministicaTipoPeca).filter(
            RegraDeterministicaTipoPeca.modulo_id == modulo.id
        ).all()

        # Regra específica para o tipo atual
        regra_tipo_atual = next(
            (r for r in regras_tipo_peca if r.tipo_peca == request.tipo_peca and r.ativo),
            None
        )

        # Monta informações sobre as regras
        info_regras = {
            "regra_global": None,
            "regra_especifica": None,
            "variaveis_necessarias": []
        }

        if modulo.regra_deterministica:
            vars_global = list(_extrair_variaveis_regra(modulo.regra_deterministica))
            info_regras["regra_global"] = {
                "ast": modulo.regra_deterministica,
                "texto_original": modulo.regra_texto_original,
                "variaveis": vars_global
            }
            info_regras["variaveis_necessarias"].extend(vars_global)

        if regra_tipo_atual and regra_tipo_atual.regra_deterministica:
            vars_especifica = list(_extrair_variaveis_regra(regra_tipo_atual.regra_deterministica))
            info_regras["regra_especifica"] = {
                "tipo_peca": request.tipo_peca,
                "ast": regra_tipo_atual.regra_deterministica,
                "texto_original": regra_tipo_atual.regra_texto_original,
                "variaveis": vars_especifica
            }
            info_regras["variaveis_necessarias"].extend(vars_especifica)

        # Remove duplicatas
        info_regras["variaveis_necessarias"] = list(set(info_regras["variaveis_necessarias"]))

        # Busca grupo do módulo
        grupo = None
        if modulo.group_id:
            grupo_obj = db.query(PromptGroup).filter(PromptGroup.id == modulo.group_id).first()
            grupo = grupo_obj.name if grupo_obj else None

        # Monta prompt para o LLM
        prompt = f"""Você é um assistente especializado em análise de regras de ativação de módulos de prompts jurídicos.

Analise as informações abaixo e gere um relatório CLARO e DIDÁTICO explicando por que o módulo não foi ativado ou ficou indeterminado.

## INFORMAÇÕES DO MÓDULO

**Nome:** {modulo.nome}
**Título:** {modulo.titulo}
**Grupo:** {grupo or 'Sem grupo'}
**Modo de Ativação:** {modulo.modo_ativacao}
**Tipo de Peça Testado:** {request.tipo_peca}

## REGRAS DE ATIVAÇÃO

### Regra Global (aplicada quando não há regra específica para o tipo de peça):
{json.dumps(info_regras.get('regra_global'), indent=2, ensure_ascii=False) if info_regras.get('regra_global') else 'Nenhuma regra global configurada'}

### Regra Específica para "{request.tipo_peca}":
{json.dumps(info_regras.get('regra_especifica'), indent=2, ensure_ascii=False) if info_regras.get('regra_especifica') else f'Nenhuma regra específica para {request.tipo_peca}'}

### Variáveis Necessárias para Avaliação:
{json.dumps(info_regras['variaveis_necessarias'], indent=2, ensure_ascii=False)}

## VARIÁVEIS FORNECIDAS PELO USUÁRIO

{json.dumps(request.variaveis_fornecidas, indent=2, ensure_ascii=False) if request.variaveis_fornecidas else 'Nenhuma variável foi fornecida'}

## RESULTADO DA AVALIAÇÃO

{json.dumps(request.resultado_avaliacao, indent=2, ensure_ascii=False)}

## INSTRUÇÕES PARA O RELATÓRIO

Gere um relatório estruturado com as seguintes seções:

1. **RESUMO**: Uma frase explicando o status do módulo (não ativado/indeterminado)

2. **CONDIÇÕES DE ATIVAÇÃO**: Explique em linguagem simples o que a regra exige para o módulo ser ativado. Traduza o JSON da regra para português claro.
   - Se a regra usa operador "equals", diga "a variável X deve ser igual a Y"
   - Se usa "and", diga "TODAS as condições devem ser verdadeiras"
   - Se usa "or", diga "PELO MENOS UMA das condições deve ser verdadeira"
   - Se usa "not", diga "a condição deve ser FALSA"

3. **VARIÁVEIS FORNECIDAS vs NECESSÁRIAS**: Compare as variáveis fornecidas com as necessárias
   - Liste quais variáveis foram fornecidas e seus valores
   - Liste quais variáveis estão FALTANDO (necessárias mas não fornecidas)
   - Liste quais variáveis foram fornecidas mas NÃO são usadas pela regra

4. **DIAGNÓSTICO**: Explique EXATAMENTE por que o módulo não ativou:
   - Se variáveis estão faltando, diga quais
   - Se variáveis têm valores incorretos, diga quais e qual valor seria necessário
   - Se a regra foi avaliada como False, explique por quê

5. **COMO ATIVAR**: Dê instruções claras sobre o que o usuário precisa fazer para ativar este módulo:
   - Quais variáveis definir
   - Quais valores usar

Use formatação Markdown. Seja conciso mas completo. Evite jargão técnico desnecessário."""

        # Chama o Gemini
        response = await gemini_service.generate(
            prompt=prompt,
            model="gemini-3-flash-preview",
            temperature=0.3,
            max_tokens=2000,
            thinking_level="low"
        )

        if not response.success:
            return RelatorioAtivacaoResponse(
                relatorio="",
                sucesso=False,
                erro=f"Erro ao gerar relatório: {response.error}"
            )

        return RelatorioAtivacaoResponse(
            relatorio=response.content,
            sucesso=True
        )

    except Exception as e:
        logger.error(f"Erro ao gerar relatório de ativação: {e}")
        return RelatorioAtivacaoResponse(
            relatorio="",
            sucesso=False,
            erro=str(e)
        )
