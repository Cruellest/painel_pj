# admin/router.py
"""
Router de administração - Gerenciamento de Prompts e Configurações de IA
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, Integer, case
from typing import List, Optional
from datetime import datetime, timedelta

from database.connection import get_db
from utils.timezone import to_iso_utc
from auth.dependencies import get_current_active_user, require_admin
from auth.models import User

from admin.models import PromptConfig, ConfiguracaoIA
from admin.schemas import (
    PromptCreate, PromptUpdate, PromptResponse, PromptListResponse,
    ConfiguracaoIACreate, ConfiguracaoIAUpdate, ConfiguracaoIAResponse
)
from admin.seed_prompts import seed_default_prompts

# Importa modelos de feedback
from sistemas.assistencia_judiciaria.models import ConsultaProcesso, FeedbackAnalise
from sistemas.matriculas_confrontantes.models import Analise, FeedbackMatricula
from sistemas.gerador_pecas.models import GeracaoPeca, FeedbackPeca
from sistemas.pedido_calculo.models import GeracaoPedidoCalculo, FeedbackPedidoCalculo
from sistemas.prestacao_contas.models import GeracaoAnalise, FeedbackPrestacao
from sistemas.relatorio_cumprimento.models import GeracaoRelatorioCumprimento, FeedbackRelatorioCumprimento


router = APIRouter(prefix="/admin", tags=["Administração"])


# ============================================
# CRUD de Prompts
# ============================================

@router.get("/prompts", response_model=PromptListResponse)
async def list_prompts(
    sistema: Optional[str] = None,
    tipo: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Lista todos os prompts configurados (apenas admin)"""
    query = db.query(PromptConfig)
    
    if sistema:
        query = query.filter(PromptConfig.sistema == sistema)
    if tipo:
        query = query.filter(PromptConfig.tipo == tipo)
    
    prompts = query.order_by(PromptConfig.sistema, PromptConfig.tipo).all()
    
    return PromptListResponse(prompts=prompts, total=len(prompts))


@router.get("/prompts/{prompt_id}", response_model=PromptResponse)
async def get_prompt(
    prompt_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Obtém um prompt específico"""
    prompt = db.query(PromptConfig).filter(PromptConfig.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")
    
    return prompt


@router.post("/prompts", response_model=PromptResponse, status_code=201)
async def create_prompt(
    prompt_data: PromptCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Cria um novo prompt"""
    # Verifica se já existe
    existing = db.query(PromptConfig).filter(
        PromptConfig.sistema == prompt_data.sistema,
        PromptConfig.tipo == prompt_data.tipo
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Já existe um prompt para sistema='{prompt_data.sistema}' e tipo='{prompt_data.tipo}'"
        )
    
    prompt = PromptConfig(
        sistema=prompt_data.sistema,
        tipo=prompt_data.tipo,
        nome=prompt_data.nome,
        descricao=prompt_data.descricao,
        conteudo=prompt_data.conteudo,
        updated_by=current_user.username
    )
    
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    
    return prompt


@router.put("/prompts/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: int,
    prompt_data: PromptUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Atualiza um prompt existente"""
    prompt = db.query(PromptConfig).filter(PromptConfig.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")
    
    # Atualiza campos fornecidos
    if prompt_data.nome is not None:
        prompt.nome = prompt_data.nome
    if prompt_data.descricao is not None:
        prompt.descricao = prompt_data.descricao
    if prompt_data.conteudo is not None:
        prompt.conteudo = prompt_data.conteudo
    if prompt_data.is_active is not None:
        prompt.is_active = prompt_data.is_active
    
    prompt.updated_by = current_user.username
    
    db.commit()
    db.refresh(prompt)
    
    return prompt


@router.delete("/prompts/{prompt_id}")
async def delete_prompt(
    prompt_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Exclui um prompt"""
    prompt = db.query(PromptConfig).filter(PromptConfig.id == prompt_id).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt não encontrado")
    
    db.delete(prompt)
    db.commit()
    
    return {"success": True, "message": "Prompt excluído com sucesso"}


@router.post("/prompts/criar-sistema/{sistema}")
async def criar_prompts_sistema(
    sistema: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Cria prompts e configurações para um sistema específico.
    Não deleta prompts existentes, apenas adiciona os que não existem.
    """
    sistemas_validos = ["pedido_calculo", "prestacao_contas", "matriculas", "assistencia_judiciaria", "gerador_pecas", "relatorio_cumprimento"]

    if sistema not in sistemas_validos:
        raise HTTPException(
            status_code=400,
            detail=f"Sistema inválido. Sistemas válidos: {', '.join(sistemas_validos)}"
        )

    prompts_criados = 0
    configs_criadas = 0

    # Cria prompts e configs com base no sistema
    if sistema == "pedido_calculo":
        from sistemas.pedido_calculo.seed_config import seed_prompts, seed_configuracoes
        # Conta antes
        prompts_antes = db.query(PromptConfig).filter(PromptConfig.sistema == sistema).count()
        configs_antes = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        # Executa seed
        seed_prompts(db)
        seed_configuracoes(db)
        # Conta depois
        prompts_depois = db.query(PromptConfig).filter(PromptConfig.sistema == sistema).count()
        configs_depois = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        prompts_criados = prompts_depois - prompts_antes
        configs_criadas = configs_depois - configs_antes

    elif sistema == "prestacao_contas":
        from sistemas.prestacao_contas.seed_config import seed_configuracoes as seed_prestacao
        # Conta antes
        prompts_antes = db.query(PromptConfig).filter(PromptConfig.sistema == sistema).count()
        configs_antes = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        # Executa seed (este seed inclui tanto prompts quanto configs)
        seed_prestacao(db)
        # Conta depois
        prompts_depois = db.query(PromptConfig).filter(PromptConfig.sistema == sistema).count()
        configs_depois = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        prompts_criados = prompts_depois - prompts_antes
        configs_criadas = configs_depois - configs_antes

    elif sistema in ["matriculas", "assistencia_judiciaria"]:
        from admin.seed_prompts import seed_default_prompts, seed_default_config_ia
        # Conta antes
        prompts_antes = db.query(PromptConfig).filter(PromptConfig.sistema == sistema).count()
        configs_antes = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        # Executa seed
        seed_default_prompts(db, sistema)
        seed_default_config_ia(db, sistema)
        # Conta depois
        prompts_depois = db.query(PromptConfig).filter(PromptConfig.sistema == sistema).count()
        configs_depois = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        prompts_criados = prompts_depois - prompts_antes
        configs_criadas = configs_depois - configs_antes

    elif sistema == "gerador_pecas":
        from admin.seed_prompts import seed_default_config_ia
        # Conta antes
        configs_antes = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        # Executa seed (gerador_pecas usa prompts modulares, só precisa das configs)
        seed_default_config_ia(db, sistema)
        # Conta depois
        configs_depois = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        configs_criadas = configs_depois - configs_antes

    elif sistema == "relatorio_cumprimento":
        from sistemas.relatorio_cumprimento.seed_config import seed_prompts, seed_configuracoes
        # Conta antes
        prompts_antes = db.query(PromptConfig).filter(PromptConfig.sistema == sistema).count()
        configs_antes = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        # Executa seed
        seed_prompts(db)
        seed_configuracoes(db)
        # Conta depois
        prompts_depois = db.query(PromptConfig).filter(PromptConfig.sistema == sistema).count()
        configs_depois = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.sistema == sistema).count()
        prompts_criados = prompts_depois - prompts_antes
        configs_criadas = configs_depois - configs_antes

    if prompts_criados == 0 and configs_criadas == 0:
        return {
            "success": True,
            "message": f"Prompts e configurações do sistema '{sistema}' já existem."
        }

    return {
        "success": True,
        "message": f"Criados {prompts_criados} prompt(s) e {configs_criadas} configuração(ões) para '{sistema}'."
    }


# ============================================
# CRUD de Configurações de IA
# ============================================

@router.get("/config-ia", response_model=List[ConfiguracaoIAResponse])
async def list_config_ia(
    sistema: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Lista configurações de IA"""
    query = db.query(ConfiguracaoIA)
    
    if sistema:
        query = query.filter(ConfiguracaoIA.sistema == sistema)
    
    return query.order_by(ConfiguracaoIA.sistema, ConfiguracaoIA.chave).all()


@router.put("/config-ia/{config_id}", response_model=ConfiguracaoIAResponse)
async def update_config_ia(
    config_id: int,
    config_data: ConfiguracaoIAUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Atualiza uma configuração de IA"""
    config = db.query(ConfiguracaoIA).filter(ConfiguracaoIA.id == config_id).first()
    
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    
    if config_data.valor is not None:
        config.valor = config_data.valor
    if config_data.descricao is not None:
        config.descricao = config_data.descricao
    
    db.commit()
    db.refresh(config)
    
    return config


class ConfigUpsertRequest(BaseModel):
    sistema: str
    chave: str
    valor: str


@router.post("/config-ia/upsert")
async def upsert_config_ia(
    data: ConfigUpsertRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Cria ou atualiza uma configuração de IA"""
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == data.sistema,
        ConfiguracaoIA.chave == data.chave
    ).first()
    
    if config:
        config.valor = data.valor
    else:
        config = ConfiguracaoIA(
            sistema=data.sistema,
            chave=data.chave,
            valor=data.valor,
            tipo_valor="string"
        )
        db.add(config)
    
    db.commit()

    return {"success": True, "sistema": data.sistema, "chave": data.chave}


# ============================================
# Configuração de IA por Agente
# ============================================

@router.get("/config-ia/per-agent/{sistema}")
async def get_config_ia_per_agent(
    sistema: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retorna configurações de IA por agente para um sistema.

    Mostra a hierarquia de resolução de parâmetros com indicação de herança:
    - fonte: "agent" = configurado especificamente para o agente
    - fonte: "system" = herdado do sistema
    - fonte: "global" = herdado da configuração global
    - fonte: "default" = usando valor padrão
    """
    from services.ia_params_resolver import (
        get_config_per_agent as resolver_get_config_per_agent,
        listar_agentes,
        AGENTES_POR_SISTEMA
    )

    if sistema not in AGENTES_POR_SISTEMA:
        raise HTTPException(
            status_code=404,
            detail=f"Sistema '{sistema}' não encontrado. Sistemas disponíveis: {list(AGENTES_POR_SISTEMA.keys())}"
        )

    # Obtém configurações de todos os agentes do sistema
    configs = resolver_get_config_per_agent(db, sistema)
    agentes_info = listar_agentes(sistema)

    # Formata resposta
    resultado = {
        "sistema": sistema,
        "agentes": {}
    }

    for agente_slug, params in configs.items():
        resultado["agentes"][agente_slug] = {
            "descricao": agentes_info.get(agente_slug, ""),
            "modelo": params.modelo,
            "modelo_fonte": params.modelo_source,
            "temperatura": params.temperatura,
            "temperatura_fonte": params.temperatura_source,
            "max_tokens": params.max_tokens,
            "max_tokens_fonte": params.max_tokens_source,
            "thinking_level": params.thinking_level,
            "thinking_level_fonte": params.thinking_level_source,
        }

    return resultado


@router.get("/config-ia/sistemas")
async def listar_sistemas_ia(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Lista todos os sistemas disponíveis e seus agentes."""
    from services.ia_params_resolver import AGENTES_POR_SISTEMA

    resultado = {}
    for sistema, agentes in AGENTES_POR_SISTEMA.items():
        resultado[sistema] = {
            "agentes": [
                {"slug": slug, "descricao": desc}
                for slug, desc in agentes.items()
            ]
        }

    return resultado


# ============================================
# Gerenciamento de Modelos de IA por Sistema
# ============================================

@router.get("/modelos-ia")
async def listar_modelos_ia(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Lista os modelos de IA configurados por sistema"""
    # Busca modelos configurados para cada sistema (chave modelo_relatorio ou modelo_analise)
    configs_aj = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "assistencia_judiciaria",
        ConfiguracaoIA.chave == "modelo_relatorio"
    ).first()

    configs_mat_analise = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "matriculas",
        ConfiguracaoIA.chave == "modelo_analise"
    ).first()

    configs_mat_relatorio = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "matriculas",
        ConfiguracaoIA.chave == "modelo_relatorio"
    ).first()

    configs_gp = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "gerador_pecas",
        ConfiguracaoIA.chave == "modelo_agente_final"
    ).first()

    configs_pc = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "pedido_calculo",
        ConfiguracaoIA.chave == "modelo_agente_final"
    ).first()

    resultado = {
        "assistencia_judiciaria": {
            "id": configs_aj.id if configs_aj else None,
            "modelo": configs_aj.valor if configs_aj else "google/gemini-3-flash-preview",
            "descricao": "Modelo para análise de processos judiciais"
        },
        "matriculas": {
            "id": configs_mat_analise.id if configs_mat_analise else None,
            "modelo": configs_mat_analise.valor if configs_mat_analise else "google/gemini-3-flash-preview",
            "modelo_analise": configs_mat_analise.valor if configs_mat_analise else "google/gemini-3-flash-preview",
            "modelo_relatorio": configs_mat_relatorio.valor if configs_mat_relatorio else "google/gemini-3-flash-preview",
            "descricao": "Modelo para análise de matrículas imobiliárias"
        },
        "gerador_pecas": {
            "id": configs_gp.id if configs_gp else None,
            "modelo": configs_gp.valor if configs_gp else "google/gemini-3-flash-preview",
            "descricao": "Modelo para geração de peças jurídicas"
        },
        "pedido_calculo": {
            "id": configs_pc.id if configs_pc else None,
            "modelo": configs_pc.valor if configs_pc else "google/gemini-3-flash-preview",
            "descricao": "Modelo para geração de pedidos de cálculo"
        }
    }

    return resultado


@router.put("/modelos-ia/{sistema}")
async def atualizar_modelo_ia(
    sistema: str,
    modelo: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Atualiza o modelo de IA de um sistema específico"""
    if sistema not in ["assistencia_judiciaria", "matriculas"]:
        raise HTTPException(status_code=400, detail="Sistema inválido")
    
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == sistema,
        ConfiguracaoIA.chave == "modelo"
    ).first()
    
    if config:
        config.valor = modelo
    else:
        config = ConfiguracaoIA(
            sistema=sistema,
            chave="modelo",
            valor=modelo,
            tipo_valor="string",
            descricao=f"Modelo de IA para o sistema {sistema}"
        )
        db.add(config)
    
    db.commit()
    
    return {"success": True, "sistema": sistema, "modelo": modelo}


# ============================================
# Configuração de API Key Global
# ============================================

@router.get("/api-key-status")
async def get_api_key_status(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Verifica se a API key está configurada (apenas admin)"""
    import os
    
    # Verifica GEMINI_KEY primeiro (nova API direta)
    gemini_key = os.getenv("GEMINI_KEY", "")
    if gemini_key:
        return {"configured": True, "source": "environment (GEMINI_KEY)"}
    
    # Verifica ambiente OpenRouter (legado)
    env_key = os.getenv("OPENROUTER_API_KEY", "")
    if env_key:
        return {"configured": True, "source": "environment (OpenRouter)"}
    
    # Verifica banco
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "global",
        ConfiguracaoIA.chave == "gemini_api_key"
    ).first()
    
    if config and config.valor:
        return {"configured": True, "source": "database (Gemini)"}
    
    # Verifica banco OpenRouter (legado)
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "global",
        ConfiguracaoIA.chave == "openrouter_api_key"
    ).first()
    
    if config and config.valor:
        return {"configured": True, "source": "database (OpenRouter)"}
    
    return {"configured": False, "source": None}


@router.put("/api-key")
async def update_api_key(
    api_key: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Atualiza a API key global do Gemini (apenas admin)"""
    if not api_key or not api_key.strip():
        raise HTTPException(status_code=400, detail="API Key não pode estar vazia")
    
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "global",
        ConfiguracaoIA.chave == "gemini_api_key"
    ).first()
    
    if config:
        config.valor = api_key.strip()
    else:
        config = ConfiguracaoIA(
            sistema="global",
            chave="gemini_api_key",
            valor=api_key.strip(),
            tipo_valor="string",
            descricao="API Key do Google Gemini (compartilhada por todos os sistemas)"
        )
        db.add(config)
    
    db.commit()
    
    return {"success": True, "message": "API Key atualizada com sucesso"}


# ============================================
# API pública para obter prompts (usada pelos sistemas)
# ============================================

@router.get("/prompts/get/{sistema}/{tipo}")
async def get_prompt_by_tipo(
    sistema: str,
    tipo: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém o conteúdo de um prompt específico (para uso interno dos sistemas)"""
    prompt = db.query(PromptConfig).filter(
        PromptConfig.sistema == sistema,
        PromptConfig.tipo == tipo,
        PromptConfig.is_active == True
    ).first()
    
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt não encontrado ou inativo")
    
    return {"conteudo": prompt.conteudo}


# ============================================
# Dashboard de Feedback (Admin)
# ============================================

@router.get("/feedbacks/dashboard")
async def dashboard_feedbacks(
    mes: Optional[int] = None,
    ano: Optional[int] = None,
    sistema: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retorna estatísticas do dashboard de feedbacks.
    
    Parâmetros:
        - mes: Mês para filtrar (1-12)
        - ano: Ano para filtrar (ex: 2026)
        - sistema: Sistema específico ('assistencia_judiciaria' ou 'matriculas')
    
    Exclui feedbacks de usuários admin e teste.
    Apenas para administradores.
    """
    try:
        # Calcula período de filtro
        data_inicio = None
        data_fim = None
        if ano:
            if mes:
                # Mês específico
                data_inicio = datetime(ano, mes, 1)
                if mes == 12:
                    data_fim = datetime(ano + 1, 1, 1)
                else:
                    data_fim = datetime(ano, mes + 1, 1)
            else:
                # Ano inteiro
                data_inicio = datetime(ano, 1, 1)
                data_fim = datetime(ano + 1, 1, 1)
        
        # Usuarios a excluir (admin e teste)
        usuarios_excluir = db.query(User.id).filter(
            (User.role == 'admin') | (User.username.ilike('%teste%')) | (User.username.ilike('%test%'))
        ).all()
        ids_excluir = [u.id for u in usuarios_excluir]
        
        # Flags para incluir cada sistema
        incluir_aj = sistema is None or sistema == 'assistencia_judiciaria'
        incluir_mat = sistema is None or sistema == 'matriculas'
        incluir_gp = sistema is None or sistema == 'gerador_pecas'
        incluir_pc = sistema is None or sistema == 'pedido_calculo'
        incluir_prest = sistema is None or sistema == 'prestacao_contas'
        incluir_rc = sistema is None or sistema == 'relatorio_cumprimento'

        total_consultas_aj = 0
        total_feedbacks_aj = 0
        feedbacks_por_avaliacao_aj = []

        total_analises_mat = 0
        total_feedbacks_mat = 0
        feedbacks_por_avaliacao_mat = []

        total_geracoes_gp = 0
        total_feedbacks_gp = 0
        feedbacks_por_avaliacao_gp = []

        total_geracoes_pc = 0
        total_feedbacks_pc = 0
        feedbacks_por_avaliacao_pc = []

        total_geracoes_prest = 0
        total_feedbacks_prest = 0
        feedbacks_por_avaliacao_prest = []

        total_geracoes_rc = 0
        total_feedbacks_rc = 0
        feedbacks_por_avaliacao_rc = []
        
        # === Sistema Assistência Judiciária ===
        if incluir_aj:
            query_total_aj = db.query(ConsultaProcesso)
            if ids_excluir:
                query_total_aj = query_total_aj.filter(~ConsultaProcesso.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_total_aj = query_total_aj.filter(
                    ConsultaProcesso.consultado_em >= data_inicio,
                    ConsultaProcesso.consultado_em < data_fim
                )
            total_consultas_aj = query_total_aj.count()
            
            query_feedbacks_aj = db.query(FeedbackAnalise)
            if ids_excluir:
                query_feedbacks_aj = query_feedbacks_aj.filter(~FeedbackAnalise.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_feedbacks_aj = query_feedbacks_aj.filter(
                    FeedbackAnalise.criado_em >= data_inicio,
                    FeedbackAnalise.criado_em < data_fim
                )
            total_feedbacks_aj = query_feedbacks_aj.count()
            
            query_avaliacoes_aj = db.query(
                FeedbackAnalise.avaliacao,
                func.count(FeedbackAnalise.id).label('count')
            )
            if ids_excluir:
                query_avaliacoes_aj = query_avaliacoes_aj.filter(~FeedbackAnalise.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_avaliacoes_aj = query_avaliacoes_aj.filter(
                    FeedbackAnalise.criado_em >= data_inicio,
                    FeedbackAnalise.criado_em < data_fim
                )
            feedbacks_por_avaliacao_aj = query_avaliacoes_aj.group_by(FeedbackAnalise.avaliacao).all()
        
        # === Sistema Matrículas ===
        if incluir_mat:
            query_total_mat = db.query(Analise)
            if ids_excluir:
                query_total_mat = query_total_mat.filter(~Analise.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_total_mat = query_total_mat.filter(
                    Analise.analisado_em >= data_inicio,
                    Analise.analisado_em < data_fim
                )
            total_analises_mat = query_total_mat.count()
            
            query_feedbacks_mat = db.query(FeedbackMatricula)
            if ids_excluir:
                query_feedbacks_mat = query_feedbacks_mat.filter(~FeedbackMatricula.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_feedbacks_mat = query_feedbacks_mat.filter(
                    FeedbackMatricula.criado_em >= data_inicio,
                    FeedbackMatricula.criado_em < data_fim
                )
            total_feedbacks_mat = query_feedbacks_mat.count()
            
            query_avaliacoes_mat = db.query(
                FeedbackMatricula.avaliacao,
                func.count(FeedbackMatricula.id).label('count')
            )
            if ids_excluir:
                query_avaliacoes_mat = query_avaliacoes_mat.filter(~FeedbackMatricula.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_avaliacoes_mat = query_avaliacoes_mat.filter(
                    FeedbackMatricula.criado_em >= data_inicio,
                    FeedbackMatricula.criado_em < data_fim
                )
            feedbacks_por_avaliacao_mat = query_avaliacoes_mat.group_by(FeedbackMatricula.avaliacao).all()

        # === Sistema Gerador de Peças ===
        if incluir_gp:
            query_total_gp = db.query(GeracaoPeca)
            if ids_excluir:
                query_total_gp = query_total_gp.filter(~GeracaoPeca.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_total_gp = query_total_gp.filter(
                    GeracaoPeca.criado_em >= data_inicio,
                    GeracaoPeca.criado_em < data_fim
                )
            total_geracoes_gp = query_total_gp.count()

            query_feedbacks_gp = db.query(FeedbackPeca)
            if ids_excluir:
                query_feedbacks_gp = query_feedbacks_gp.filter(~FeedbackPeca.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_feedbacks_gp = query_feedbacks_gp.filter(
                    FeedbackPeca.criado_em >= data_inicio,
                    FeedbackPeca.criado_em < data_fim
                )
            total_feedbacks_gp = query_feedbacks_gp.count()

            query_avaliacoes_gp = db.query(
                FeedbackPeca.avaliacao,
                func.count(FeedbackPeca.id).label('count')
            )
            if ids_excluir:
                query_avaliacoes_gp = query_avaliacoes_gp.filter(~FeedbackPeca.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_avaliacoes_gp = query_avaliacoes_gp.filter(
                    FeedbackPeca.criado_em >= data_inicio,
                    FeedbackPeca.criado_em < data_fim
                )
            feedbacks_por_avaliacao_gp = query_avaliacoes_gp.group_by(FeedbackPeca.avaliacao).all()

        # === Sistema Pedido de Cálculo ===
        if incluir_pc:
            query_total_pc = db.query(GeracaoPedidoCalculo)
            if ids_excluir:
                query_total_pc = query_total_pc.filter(~GeracaoPedidoCalculo.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_total_pc = query_total_pc.filter(
                    GeracaoPedidoCalculo.criado_em >= data_inicio,
                    GeracaoPedidoCalculo.criado_em < data_fim
                )
            total_geracoes_pc = query_total_pc.count()

            query_feedbacks_pc = db.query(FeedbackPedidoCalculo)
            if ids_excluir:
                query_feedbacks_pc = query_feedbacks_pc.filter(~FeedbackPedidoCalculo.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_feedbacks_pc = query_feedbacks_pc.filter(
                    FeedbackPedidoCalculo.criado_em >= data_inicio,
                    FeedbackPedidoCalculo.criado_em < data_fim
                )
            total_feedbacks_pc = query_feedbacks_pc.count()

            query_avaliacoes_pc = db.query(
                FeedbackPedidoCalculo.avaliacao,
                func.count(FeedbackPedidoCalculo.id).label('count')
            )
            if ids_excluir:
                query_avaliacoes_pc = query_avaliacoes_pc.filter(~FeedbackPedidoCalculo.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_avaliacoes_pc = query_avaliacoes_pc.filter(
                    FeedbackPedidoCalculo.criado_em >= data_inicio,
                    FeedbackPedidoCalculo.criado_em < data_fim
                )
            feedbacks_por_avaliacao_pc = query_avaliacoes_pc.group_by(FeedbackPedidoCalculo.avaliacao).all()

        # === Sistema Prestação de Contas ===
        if incluir_prest:
            query_total_prest = db.query(GeracaoAnalise)
            if ids_excluir:
                query_total_prest = query_total_prest.filter(~GeracaoAnalise.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_total_prest = query_total_prest.filter(
                    GeracaoAnalise.criado_em >= data_inicio,
                    GeracaoAnalise.criado_em < data_fim
                )
            total_geracoes_prest = query_total_prest.count()

            query_feedbacks_prest = db.query(FeedbackPrestacao)
            if ids_excluir:
                query_feedbacks_prest = query_feedbacks_prest.filter(~FeedbackPrestacao.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_feedbacks_prest = query_feedbacks_prest.filter(
                    FeedbackPrestacao.criado_em >= data_inicio,
                    FeedbackPrestacao.criado_em < data_fim
                )
            total_feedbacks_prest = query_feedbacks_prest.count()

            query_avaliacoes_prest = db.query(
                FeedbackPrestacao.avaliacao,
                func.count(FeedbackPrestacao.id).label('count')
            )
            if ids_excluir:
                query_avaliacoes_prest = query_avaliacoes_prest.filter(~FeedbackPrestacao.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_avaliacoes_prest = query_avaliacoes_prest.filter(
                    FeedbackPrestacao.criado_em >= data_inicio,
                    FeedbackPrestacao.criado_em < data_fim
                )
            feedbacks_por_avaliacao_prest = query_avaliacoes_prest.group_by(FeedbackPrestacao.avaliacao).all()

        # === Sistema Relatório de Cumprimento ===
        if incluir_rc:
            query_total_rc = db.query(GeracaoRelatorioCumprimento).filter(
                GeracaoRelatorioCumprimento.status == 'concluido'
            )
            if ids_excluir:
                query_total_rc = query_total_rc.filter(~GeracaoRelatorioCumprimento.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_total_rc = query_total_rc.filter(
                    GeracaoRelatorioCumprimento.criado_em >= data_inicio,
                    GeracaoRelatorioCumprimento.criado_em < data_fim
                )
            total_geracoes_rc = query_total_rc.count()

            query_feedbacks_rc = db.query(FeedbackRelatorioCumprimento)
            if ids_excluir:
                query_feedbacks_rc = query_feedbacks_rc.filter(~FeedbackRelatorioCumprimento.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_feedbacks_rc = query_feedbacks_rc.filter(
                    FeedbackRelatorioCumprimento.criado_em >= data_inicio,
                    FeedbackRelatorioCumprimento.criado_em < data_fim
                )
            total_feedbacks_rc = query_feedbacks_rc.count()

            query_avaliacoes_rc = db.query(
                FeedbackRelatorioCumprimento.avaliacao,
                func.count(FeedbackRelatorioCumprimento.id).label('count')
            )
            if ids_excluir:
                query_avaliacoes_rc = query_avaliacoes_rc.filter(~FeedbackRelatorioCumprimento.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_avaliacoes_rc = query_avaliacoes_rc.filter(
                    FeedbackRelatorioCumprimento.criado_em >= data_inicio,
                    FeedbackRelatorioCumprimento.criado_em < data_fim
                )
            feedbacks_por_avaliacao_rc = query_avaliacoes_rc.group_by(FeedbackRelatorioCumprimento.avaliacao).all()

        # === Totais combinados ===
        total_consultas = total_consultas_aj + total_analises_mat + total_geracoes_gp + total_geracoes_pc + total_geracoes_prest + total_geracoes_rc
        total_feedbacks = total_feedbacks_aj + total_feedbacks_mat + total_feedbacks_gp + total_feedbacks_pc + total_feedbacks_prest + total_feedbacks_rc

        # Combinar avaliações
        avaliacoes = {
            'correto': 0,
            'parcial': 0,
            'incorreto': 0,
            'erro_ia': 0
        }
        for avaliacao, count in feedbacks_por_avaliacao_aj:
            if avaliacao in avaliacoes:
                avaliacoes[avaliacao] += count
        for avaliacao, count in feedbacks_por_avaliacao_mat:
            if avaliacao in avaliacoes:
                avaliacoes[avaliacao] += count
        for avaliacao, count in feedbacks_por_avaliacao_gp:
            if avaliacao in avaliacoes:
                avaliacoes[avaliacao] += count
        for avaliacao, count in feedbacks_por_avaliacao_pc:
            if avaliacao in avaliacoes:
                avaliacoes[avaliacao] += count
        for avaliacao, count in feedbacks_por_avaliacao_prest:
            if avaliacao in avaliacoes:
                avaliacoes[avaliacao] += count
        for avaliacao, count in feedbacks_por_avaliacao_rc:
            if avaliacao in avaliacoes:
                avaliacoes[avaliacao] += count

        # Taxa de acerto (correto / total feedbacks)
        taxa_acerto = 0
        if total_feedbacks > 0:
            taxa_acerto = round((avaliacoes['correto'] / total_feedbacks) * 100, 1)
        
        # Feedbacks por dia (no período selecionado ou últimos 30 dias)
        if data_inicio and data_fim:
            data_limite_recentes = data_inicio
            data_fim_recentes = data_fim
        else:
            data_limite_recentes = datetime.utcnow() - timedelta(days=30)
            data_fim_recentes = datetime.utcnow()
        
        feedbacks_recentes_aj = []
        feedbacks_recentes_mat = []
        feedbacks_recentes_gp = []
        feedbacks_recentes_pc = []
        feedbacks_recentes_prest = []
        feedbacks_recentes_rc = []

        if incluir_aj:
            query_recentes_aj = db.query(
                func.date(FeedbackAnalise.criado_em).label('data'),
                func.count(FeedbackAnalise.id).label('count')
            ).filter(
                FeedbackAnalise.criado_em >= data_limite_recentes,
                FeedbackAnalise.criado_em < data_fim_recentes
            )
            if ids_excluir:
                query_recentes_aj = query_recentes_aj.filter(~FeedbackAnalise.usuario_id.in_(ids_excluir))
            feedbacks_recentes_aj = query_recentes_aj.group_by(func.date(FeedbackAnalise.criado_em)).all()
        
        if incluir_mat:
            query_recentes_mat = db.query(
                func.date(FeedbackMatricula.criado_em).label('data'),
                func.count(FeedbackMatricula.id).label('count')
            ).filter(
                FeedbackMatricula.criado_em >= data_limite_recentes,
                FeedbackMatricula.criado_em < data_fim_recentes
            )
            if ids_excluir:
                query_recentes_mat = query_recentes_mat.filter(~FeedbackMatricula.usuario_id.in_(ids_excluir))
            feedbacks_recentes_mat = query_recentes_mat.group_by(func.date(FeedbackMatricula.criado_em)).all()

        if incluir_gp:
            query_recentes_gp = db.query(
                func.date(FeedbackPeca.criado_em).label('data'),
                func.count(FeedbackPeca.id).label('count')
            ).filter(
                FeedbackPeca.criado_em >= data_limite_recentes,
                FeedbackPeca.criado_em < data_fim_recentes
            )
            if ids_excluir:
                query_recentes_gp = query_recentes_gp.filter(~FeedbackPeca.usuario_id.in_(ids_excluir))
            feedbacks_recentes_gp = query_recentes_gp.group_by(func.date(FeedbackPeca.criado_em)).all()

        if incluir_pc:
            query_recentes_pc = db.query(
                func.date(FeedbackPedidoCalculo.criado_em).label('data'),
                func.count(FeedbackPedidoCalculo.id).label('count')
            ).filter(
                FeedbackPedidoCalculo.criado_em >= data_limite_recentes,
                FeedbackPedidoCalculo.criado_em < data_fim_recentes
            )
            if ids_excluir:
                query_recentes_pc = query_recentes_pc.filter(~FeedbackPedidoCalculo.usuario_id.in_(ids_excluir))
            feedbacks_recentes_pc = query_recentes_pc.group_by(func.date(FeedbackPedidoCalculo.criado_em)).all()

        if incluir_prest:
            query_recentes_prest = db.query(
                func.date(FeedbackPrestacao.criado_em).label('data'),
                func.count(FeedbackPrestacao.id).label('count')
            ).filter(
                FeedbackPrestacao.criado_em >= data_limite_recentes,
                FeedbackPrestacao.criado_em < data_fim_recentes
            )
            if ids_excluir:
                query_recentes_prest = query_recentes_prest.filter(~FeedbackPrestacao.usuario_id.in_(ids_excluir))
            feedbacks_recentes_prest = query_recentes_prest.group_by(func.date(FeedbackPrestacao.criado_em)).all()

        if incluir_rc:
            query_recentes_rc = db.query(
                func.date(FeedbackRelatorioCumprimento.criado_em).label('data'),
                func.count(FeedbackRelatorioCumprimento.id).label('count')
            ).filter(
                FeedbackRelatorioCumprimento.criado_em >= data_limite_recentes,
                FeedbackRelatorioCumprimento.criado_em < data_fim_recentes
            )
            if ids_excluir:
                query_recentes_rc = query_recentes_rc.filter(~FeedbackRelatorioCumprimento.usuario_id.in_(ids_excluir))
            feedbacks_recentes_rc = query_recentes_rc.group_by(func.date(FeedbackRelatorioCumprimento.criado_em)).all()

        # Combina feedbacks recentes por data
        feedbacks_por_data = {}
        for data, count in feedbacks_recentes_aj:
            feedbacks_por_data[str(data)] = feedbacks_por_data.get(str(data), 0) + count
        for data, count in feedbacks_recentes_mat:
            feedbacks_por_data[str(data)] = feedbacks_por_data.get(str(data), 0) + count
        for data, count in feedbacks_recentes_gp:
            feedbacks_por_data[str(data)] = feedbacks_por_data.get(str(data), 0) + count
        for data, count in feedbacks_recentes_pc:
            feedbacks_por_data[str(data)] = feedbacks_por_data.get(str(data), 0) + count
        for data, count in feedbacks_recentes_prest:
            feedbacks_por_data[str(data)] = feedbacks_por_data.get(str(data), 0) + count
        for data, count in feedbacks_recentes_rc:
            feedbacks_por_data[str(data)] = feedbacks_por_data.get(str(data), 0) + count

        feedbacks_recentes = [{"data": data, "count": count} for data, count in sorted(feedbacks_por_data.items())]
        
        # Feedbacks por usuário (top 10) - combinando sistemas selecionados
        feedbacks_por_usuario_aj = []
        feedbacks_por_usuario_mat = []
        feedbacks_por_usuario_gp = []
        feedbacks_por_usuario_pc = []
        feedbacks_por_usuario_prest = []
        feedbacks_por_usuario_rc = []
        
        if incluir_aj:
            query_usuarios_aj = db.query(
                User.username,
                User.full_name,
                func.count(FeedbackAnalise.id).label('total'),
                func.sum(case((FeedbackAnalise.avaliacao == 'correto', 1), else_=0)).label('corretos')
            ).join(FeedbackAnalise, FeedbackAnalise.usuario_id == User.id)
            if ids_excluir:
                query_usuarios_aj = query_usuarios_aj.filter(~User.id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_usuarios_aj = query_usuarios_aj.filter(
                    FeedbackAnalise.criado_em >= data_inicio,
                    FeedbackAnalise.criado_em < data_fim
                )
            feedbacks_por_usuario_aj = query_usuarios_aj.group_by(User.id, User.username, User.full_name).all()
        
        if incluir_mat:
            query_usuarios_mat = db.query(
                User.username,
                User.full_name,
                func.count(FeedbackMatricula.id).label('total'),
                func.sum(case((FeedbackMatricula.avaliacao == 'correto', 1), else_=0)).label('corretos')
            ).join(FeedbackMatricula, FeedbackMatricula.usuario_id == User.id)
            if ids_excluir:
                query_usuarios_mat = query_usuarios_mat.filter(~User.id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_usuarios_mat = query_usuarios_mat.filter(
                    FeedbackMatricula.criado_em >= data_inicio,
                    FeedbackMatricula.criado_em < data_fim
                )
            feedbacks_por_usuario_mat = query_usuarios_mat.group_by(User.id, User.username, User.full_name).all()

        if incluir_gp:
            query_usuarios_gp = db.query(
                User.username,
                User.full_name,
                func.count(FeedbackPeca.id).label('total'),
                func.sum(case((FeedbackPeca.avaliacao == 'correto', 1), else_=0)).label('corretos')
            ).join(FeedbackPeca, FeedbackPeca.usuario_id == User.id)
            if ids_excluir:
                query_usuarios_gp = query_usuarios_gp.filter(~User.id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_usuarios_gp = query_usuarios_gp.filter(
                    FeedbackPeca.criado_em >= data_inicio,
                    FeedbackPeca.criado_em < data_fim
                )
            feedbacks_por_usuario_gp = query_usuarios_gp.group_by(User.id, User.username, User.full_name).all()

        if incluir_pc:
            query_usuarios_pc = db.query(
                User.username,
                User.full_name,
                func.count(FeedbackPedidoCalculo.id).label('total'),
                func.sum(case((FeedbackPedidoCalculo.avaliacao == 'correto', 1), else_=0)).label('corretos')
            ).join(FeedbackPedidoCalculo, FeedbackPedidoCalculo.usuario_id == User.id)
            if ids_excluir:
                query_usuarios_pc = query_usuarios_pc.filter(~User.id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_usuarios_pc = query_usuarios_pc.filter(
                    FeedbackPedidoCalculo.criado_em >= data_inicio,
                    FeedbackPedidoCalculo.criado_em < data_fim
                )
            feedbacks_por_usuario_pc = query_usuarios_pc.group_by(User.id, User.username, User.full_name).all()

        if incluir_prest:
            query_usuarios_prest = db.query(
                User.username,
                User.full_name,
                func.count(FeedbackPrestacao.id).label('total'),
                func.sum(case((FeedbackPrestacao.avaliacao == 'correto', 1), else_=0)).label('corretos')
            ).join(FeedbackPrestacao, FeedbackPrestacao.usuario_id == User.id)
            if ids_excluir:
                query_usuarios_prest = query_usuarios_prest.filter(~User.id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_usuarios_prest = query_usuarios_prest.filter(
                    FeedbackPrestacao.criado_em >= data_inicio,
                    FeedbackPrestacao.criado_em < data_fim
                )
            feedbacks_por_usuario_prest = query_usuarios_prest.group_by(User.id, User.username, User.full_name).all()

        if incluir_rc:
            query_usuarios_rc = db.query(
                User.username,
                User.full_name,
                func.count(FeedbackRelatorioCumprimento.id).label('total'),
                func.sum(case((FeedbackRelatorioCumprimento.avaliacao == 'correto', 1), else_=0)).label('corretos')
            ).join(FeedbackRelatorioCumprimento, FeedbackRelatorioCumprimento.usuario_id == User.id)
            if ids_excluir:
                query_usuarios_rc = query_usuarios_rc.filter(~User.id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_usuarios_rc = query_usuarios_rc.filter(
                    FeedbackRelatorioCumprimento.criado_em >= data_inicio,
                    FeedbackRelatorioCumprimento.criado_em < data_fim
                )
            feedbacks_por_usuario_rc = query_usuarios_rc.group_by(User.id, User.username, User.full_name).all()

        # Combina por usuário
        usuarios_stats = {}
        for username, full_name, total, corretos in feedbacks_por_usuario_aj:
            if username not in usuarios_stats:
                usuarios_stats[username] = {"nome": full_name or username, "total": 0, "corretos": 0}
            usuarios_stats[username]["total"] += total
            usuarios_stats[username]["corretos"] += corretos or 0
        for username, full_name, total, corretos in feedbacks_por_usuario_mat:
            if username not in usuarios_stats:
                usuarios_stats[username] = {"nome": full_name or username, "total": 0, "corretos": 0}
            usuarios_stats[username]["total"] += total
            usuarios_stats[username]["corretos"] += corretos or 0
        for username, full_name, total, corretos in feedbacks_por_usuario_gp:
            if username not in usuarios_stats:
                usuarios_stats[username] = {"nome": full_name or username, "total": 0, "corretos": 0}
            usuarios_stats[username]["total"] += total
            usuarios_stats[username]["corretos"] += corretos or 0
        for username, full_name, total, corretos in feedbacks_por_usuario_pc:
            if username not in usuarios_stats:
                usuarios_stats[username] = {"nome": full_name or username, "total": 0, "corretos": 0}
            usuarios_stats[username]["total"] += total
            usuarios_stats[username]["corretos"] += corretos or 0
        for username, full_name, total, corretos in feedbacks_por_usuario_prest:
            if username not in usuarios_stats:
                usuarios_stats[username] = {"nome": full_name or username, "total": 0, "corretos": 0}
            usuarios_stats[username]["total"] += total
            usuarios_stats[username]["corretos"] += corretos or 0
        for username, full_name, total, corretos in feedbacks_por_usuario_rc:
            if username not in usuarios_stats:
                usuarios_stats[username] = {"nome": full_name or username, "total": 0, "corretos": 0}
            usuarios_stats[username]["total"] += total
            usuarios_stats[username]["corretos"] += corretos or 0

        feedbacks_por_usuario = sorted(
            [{"username": k, **v} for k, v in usuarios_stats.items()],
            key=lambda x: x["total"],
            reverse=True
        )[:10]
        
        # Usuários que geraram relatório mas não deram feedback
        consultas_sem_feedback_aj = []
        analises_sem_feedback_mat = []
        geracoes_sem_feedback_gp = []
        geracoes_sem_feedback_pc = []
        geracoes_sem_feedback_prest = []
        geracoes_sem_feedback_rc = []
        
        # Assistência Judiciária
        if incluir_aj:
            query_pendentes_aj = db.query(
                ConsultaProcesso.id,
                ConsultaProcesso.cnj_formatado,
                ConsultaProcesso.cnj,
                ConsultaProcesso.consultado_em,
                User.username,
                User.full_name
            ).outerjoin(
                FeedbackAnalise, FeedbackAnalise.consulta_id == ConsultaProcesso.id
            ).join(
                User, ConsultaProcesso.usuario_id == User.id
            ).filter(
                FeedbackAnalise.id == None,
                ConsultaProcesso.relatorio.isnot(None)
            )
            if ids_excluir:
                query_pendentes_aj = query_pendentes_aj.filter(~ConsultaProcesso.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_pendentes_aj = query_pendentes_aj.filter(
                    ConsultaProcesso.consultado_em >= data_inicio,
                    ConsultaProcesso.consultado_em < data_fim
                )
            consultas_sem_feedback_aj = query_pendentes_aj.order_by(ConsultaProcesso.consultado_em.desc()).limit(20).all()
        
        # Matrículas
        if incluir_mat:
            query_pendentes_mat = db.query(
                Analise.id,
                Analise.file_name,
                Analise.matricula_principal,
                Analise.analisado_em,
                User.username,
                User.full_name
            ).outerjoin(
                FeedbackMatricula, FeedbackMatricula.analise_id == Analise.id
            ).join(
                User, Analise.usuario_id == User.id
            ).filter(
                FeedbackMatricula.id == None,
                Analise.resultado_json.isnot(None)
            )
            if ids_excluir:
                query_pendentes_mat = query_pendentes_mat.filter(~Analise.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_pendentes_mat = query_pendentes_mat.filter(
                    Analise.analisado_em >= data_inicio,
                    Analise.analisado_em < data_fim
                )
            analises_sem_feedback_mat = query_pendentes_mat.order_by(Analise.analisado_em.desc()).limit(20).all()

        # Gerador de Peças
        if incluir_gp:
            query_pendentes_gp = db.query(
                GeracaoPeca.id,
                GeracaoPeca.tipo_peca,
                GeracaoPeca.numero_cnj,
                GeracaoPeca.criado_em,
                User.username,
                User.full_name
            ).outerjoin(
                FeedbackPeca, FeedbackPeca.geracao_id == GeracaoPeca.id
            ).join(
                User, GeracaoPeca.usuario_id == User.id
            ).filter(
                FeedbackPeca.id == None,
                GeracaoPeca.conteudo_gerado.isnot(None)
            )
            if ids_excluir:
                query_pendentes_gp = query_pendentes_gp.filter(~GeracaoPeca.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_pendentes_gp = query_pendentes_gp.filter(
                    GeracaoPeca.criado_em >= data_inicio,
                    GeracaoPeca.criado_em < data_fim
                )
            geracoes_sem_feedback_gp = query_pendentes_gp.order_by(GeracaoPeca.criado_em.desc()).limit(20).all()

        # Pedido de Cálculo
        if incluir_pc:
            query_pendentes_pc = db.query(
                GeracaoPedidoCalculo.id,
                GeracaoPedidoCalculo.numero_cnj_formatado,
                GeracaoPedidoCalculo.numero_cnj,
                GeracaoPedidoCalculo.criado_em,
                User.username,
                User.full_name
            ).outerjoin(
                FeedbackPedidoCalculo, FeedbackPedidoCalculo.geracao_id == GeracaoPedidoCalculo.id
            ).join(
                User, GeracaoPedidoCalculo.usuario_id == User.id
            ).filter(
                FeedbackPedidoCalculo.id == None,
                GeracaoPedidoCalculo.conteudo_gerado.isnot(None)
            )
            if ids_excluir:
                query_pendentes_pc = query_pendentes_pc.filter(~GeracaoPedidoCalculo.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_pendentes_pc = query_pendentes_pc.filter(
                    GeracaoPedidoCalculo.criado_em >= data_inicio,
                    GeracaoPedidoCalculo.criado_em < data_fim
                )
            geracoes_sem_feedback_pc = query_pendentes_pc.order_by(GeracaoPedidoCalculo.criado_em.desc()).limit(20).all()

        # Prestação de Contas
        if incluir_prest:
            query_pendentes_prest = db.query(
                GeracaoAnalise.id,
                GeracaoAnalise.numero_cnj_formatado,
                GeracaoAnalise.numero_cnj,
                GeracaoAnalise.criado_em,
                User.username,
                User.full_name
            ).outerjoin(
                FeedbackPrestacao, FeedbackPrestacao.geracao_id == GeracaoAnalise.id
            ).join(
                User, GeracaoAnalise.usuario_id == User.id
            ).filter(
                FeedbackPrestacao.id == None,
                GeracaoAnalise.fundamentacao.isnot(None)
            )
            if ids_excluir:
                query_pendentes_prest = query_pendentes_prest.filter(~GeracaoAnalise.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_pendentes_prest = query_pendentes_prest.filter(
                    GeracaoAnalise.criado_em >= data_inicio,
                    GeracaoAnalise.criado_em < data_fim
                )
            geracoes_sem_feedback_prest = query_pendentes_prest.order_by(GeracaoAnalise.criado_em.desc()).limit(20).all()

        # Relatório de Cumprimento
        if incluir_rc:
            query_pendentes_rc = db.query(
                GeracaoRelatorioCumprimento.id,
                GeracaoRelatorioCumprimento.numero_cumprimento_formatado,
                GeracaoRelatorioCumprimento.numero_cumprimento,
                GeracaoRelatorioCumprimento.criado_em,
                User.username,
                User.full_name
            ).outerjoin(
                FeedbackRelatorioCumprimento, FeedbackRelatorioCumprimento.geracao_id == GeracaoRelatorioCumprimento.id
            ).join(
                User, GeracaoRelatorioCumprimento.usuario_id == User.id
            ).filter(
                FeedbackRelatorioCumprimento.id == None,
                GeracaoRelatorioCumprimento.conteudo_gerado.isnot(None),
                GeracaoRelatorioCumprimento.status == 'concluido'
            )
            if ids_excluir:
                query_pendentes_rc = query_pendentes_rc.filter(~GeracaoRelatorioCumprimento.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_pendentes_rc = query_pendentes_rc.filter(
                    GeracaoRelatorioCumprimento.criado_em >= data_inicio,
                    GeracaoRelatorioCumprimento.criado_em < data_fim
                )
            geracoes_sem_feedback_rc = query_pendentes_rc.order_by(GeracaoRelatorioCumprimento.criado_em.desc()).limit(20).all()

        # Combina e formata
        pendentes_feedback = []
        for id, cnj_fmt, cnj, consultado_em, username, full_name in consultas_sem_feedback_aj:
            pendentes_feedback.append({
                "id": id,
                "sistema": "assistencia_judiciaria",
                "identificador": cnj_fmt or cnj,
                "usuario": full_name or username,
                "data": to_iso_utc(consultado_em)
            })
        for id, file_name, matricula, analisado_em, username, full_name in analises_sem_feedback_mat:
            pendentes_feedback.append({
                "id": id,
                "sistema": "matriculas",
                "identificador": matricula or file_name,
                "usuario": full_name or username,
                "data": to_iso_utc(analisado_em)
            })
        for id, tipo_peca, numero_cnj, criado_em, username, full_name in geracoes_sem_feedback_gp:
            pendentes_feedback.append({
                "id": id,
                "sistema": "gerador_pecas",
                "identificador": numero_cnj or tipo_peca,
                "usuario": full_name or username,
                "data": to_iso_utc(criado_em)
            })
        for id, numero_cnj_fmt, numero_cnj, criado_em, username, full_name in geracoes_sem_feedback_pc:
            pendentes_feedback.append({
                "id": id,
                "sistema": "pedido_calculo",
                "identificador": numero_cnj_fmt or numero_cnj,
                "usuario": full_name or username,
                "data": to_iso_utc(criado_em)
            })
        for id, numero_cnj_fmt, numero_cnj, criado_em, username, full_name in geracoes_sem_feedback_prest:
            pendentes_feedback.append({
                "id": id,
                "sistema": "prestacao_contas",
                "identificador": numero_cnj_fmt or numero_cnj,
                "usuario": full_name or username,
                "data": to_iso_utc(criado_em)
            })
        for id, numero_cnj_fmt, numero_cnj, criado_em, username, full_name in geracoes_sem_feedback_rc:
            pendentes_feedback.append({
                "id": id,
                "sistema": "relatorio_cumprimento",
                "identificador": numero_cnj_fmt or numero_cnj,
                "usuario": full_name or username,
                "data": to_iso_utc(criado_em)
            })

        # Ordena por data (mais recentes primeiro)
        pendentes_feedback.sort(key=lambda x: x.get('data') or '', reverse=True)
        pendentes_feedback = pendentes_feedback[:20]
        
        return {
            "total_consultas": total_consultas,
            "total_feedbacks": total_feedbacks,
            "consultas_sem_feedback": total_consultas - total_feedbacks,
            "taxa_acerto": taxa_acerto,
            "avaliacoes": avaliacoes,
            "feedbacks_recentes": feedbacks_recentes,
            "feedbacks_por_usuario": feedbacks_por_usuario,
            "pendentes_feedback": pendentes_feedback,
            "filtro_aplicado": {
                "mes": mes,
                "ano": ano,
                "sistema": sistema
            },
            "por_sistema": {
                "assistencia_judiciaria": {
                    "total": total_consultas_aj,
                    "feedbacks": total_feedbacks_aj
                },
                "matriculas": {
                    "total": total_analises_mat,
                    "feedbacks": total_feedbacks_mat
                },
                "gerador_pecas": {
                    "total": total_geracoes_gp,
                    "feedbacks": total_feedbacks_gp
                },
                "pedido_calculo": {
                    "total": total_geracoes_pc,
                    "feedbacks": total_feedbacks_pc
                },
                "prestacao_contas": {
                    "total": total_geracoes_prest,
                    "feedbacks": total_feedbacks_prest
                },
                "relatorio_cumprimento": {
                    "total": total_geracoes_rc,
                    "feedbacks": total_feedbacks_rc
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedbacks/lista")
async def listar_feedbacks(
    page: int = 1,
    per_page: int = 20,
    avaliacao: Optional[str] = None,
    usuario_id: Optional[int] = None,
    sistema: Optional[str] = None,
    mes: Optional[int] = None,
    ano: Optional[int] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista todos os feedbacks com paginação e filtros.
    Exclui feedbacks de usuários admin e teste.
    Apenas para administradores.
    """
    try:
        # Calcula período de filtro
        data_inicio = None
        data_fim = None
        if ano:
            if mes:
                data_inicio = datetime(ano, mes, 1)
                if mes == 12:
                    data_fim = datetime(ano + 1, 1, 1)
                else:
                    data_fim = datetime(ano, mes + 1, 1)
            else:
                data_inicio = datetime(ano, 1, 1)
                data_fim = datetime(ano + 1, 1, 1)
        
        # Usuarios a excluir (admin e teste)
        usuarios_excluir = db.query(User.id).filter(
            (User.role == 'admin') | (User.username.ilike('%teste%')) | (User.username.ilike('%test%'))
        ).all()
        ids_excluir = [u.id for u in usuarios_excluir]
        
        feedbacks_combinados = []
        
        # Feedbacks de Assistência Judiciária
        if sistema is None or sistema == 'assistencia_judiciaria':
            query_aj = db.query(
                FeedbackAnalise,
                ConsultaProcesso.cnj_formatado,
                ConsultaProcesso.cnj,
                ConsultaProcesso.modelo_usado,
                User.username,
                User.full_name
            ).join(
                ConsultaProcesso, FeedbackAnalise.consulta_id == ConsultaProcesso.id
            ).join(
                User, FeedbackAnalise.usuario_id == User.id
            )
            
            if ids_excluir:
                query_aj = query_aj.filter(~FeedbackAnalise.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_aj = query_aj.filter(
                    FeedbackAnalise.criado_em >= data_inicio,
                    FeedbackAnalise.criado_em < data_fim
                )
            if avaliacao:
                query_aj = query_aj.filter(FeedbackAnalise.avaliacao == avaliacao)
            if usuario_id:
                query_aj = query_aj.filter(FeedbackAnalise.usuario_id == usuario_id)
            
            for fb, cnj_fmt, cnj, modelo, username, full_name in query_aj.all():
                feedbacks_combinados.append({
                    "id": fb.id,
                    "consulta_id": fb.consulta_id,
                    "sistema": "assistencia_judiciaria",
                    "identificador": cnj_fmt or cnj,
                    "cnj": cnj_fmt or cnj,
                    "modelo": modelo,
                    "usuario": full_name or username,
                    "username": username,
                    "avaliacao": fb.avaliacao,
                    "comentario": fb.comentario,
                    "campos_incorretos": fb.campos_incorretos,
                    "criado_em": to_iso_utc(fb.criado_em),
                    "criado_em_dt": fb.criado_em
                })
        
        # Feedbacks de Matrículas
        if sistema is None or sistema == 'matriculas':
            query_mat = db.query(
                FeedbackMatricula,
                Analise.file_name,
                Analise.matricula_principal,
                Analise.modelo_usado,
                User.username,
                User.full_name
            ).join(
                Analise, FeedbackMatricula.analise_id == Analise.id
            ).join(
                User, FeedbackMatricula.usuario_id == User.id
            )
            
            if ids_excluir:
                query_mat = query_mat.filter(~FeedbackMatricula.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_mat = query_mat.filter(
                    FeedbackMatricula.criado_em >= data_inicio,
                    FeedbackMatricula.criado_em < data_fim
                )
            if avaliacao:
                query_mat = query_mat.filter(FeedbackMatricula.avaliacao == avaliacao)
            if usuario_id:
                query_mat = query_mat.filter(FeedbackMatricula.usuario_id == usuario_id)
            
            # Modelo padrão caso não esteja salvo na análise
            modelo_mat_config = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "matriculas",
                ConfiguracaoIA.chave == "modelo_relatorio"
            ).first()
            modelo_matriculas_default = modelo_mat_config.valor if modelo_mat_config else "gemini-3-flash-preview"
            
            for fb, file_name, matricula, modelo_usado, username, full_name in query_mat.all():
                feedbacks_combinados.append({
                    "id": fb.id,
                    "consulta_id": fb.analise_id,
                    "sistema": "matriculas",
                    "identificador": matricula or file_name,
                    "cnj": None,
                    "modelo": modelo_usado or modelo_matriculas_default,
                    "usuario": full_name or username,
                    "username": username,
                    "avaliacao": fb.avaliacao,
                    "comentario": fb.comentario,
                    "campos_incorretos": fb.campos_incorretos,
                    "criado_em": to_iso_utc(fb.criado_em),
                    "criado_em_dt": fb.criado_em
                })

        # Feedbacks de Gerador de Peças
        if sistema is None or sistema == 'gerador_pecas':
            query_gp = db.query(
                FeedbackPeca,
                GeracaoPeca.tipo_peca,
                GeracaoPeca.numero_cnj,
                GeracaoPeca.modelo_usado,
                User.username,
                User.full_name
            ).join(
                GeracaoPeca, FeedbackPeca.geracao_id == GeracaoPeca.id
            ).join(
                User, FeedbackPeca.usuario_id == User.id
            )

            if ids_excluir:
                query_gp = query_gp.filter(~FeedbackPeca.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_gp = query_gp.filter(
                    FeedbackPeca.criado_em >= data_inicio,
                    FeedbackPeca.criado_em < data_fim
                )
            if avaliacao:
                query_gp = query_gp.filter(FeedbackPeca.avaliacao == avaliacao)
            if usuario_id:
                query_gp = query_gp.filter(FeedbackPeca.usuario_id == usuario_id)

            for fb, tipo_peca, numero_cnj, modelo_usado, username, full_name in query_gp.all():
                feedbacks_combinados.append({
                    "id": fb.id,
                    "consulta_id": fb.geracao_id,
                    "sistema": "gerador_pecas",
                    "identificador": numero_cnj or tipo_peca,
                    "cnj": numero_cnj,
                    "modelo": modelo_usado or "gemini-3-flash-preview",
                    "usuario": full_name or username,
                    "username": username,
                    "avaliacao": fb.avaliacao,
                    "comentario": fb.comentario,
                    "campos_incorretos": fb.campos_incorretos,
                    "criado_em": to_iso_utc(fb.criado_em),
                    "criado_em_dt": fb.criado_em
                })

        # Feedbacks de Pedido de Cálculo
        if sistema is None or sistema == 'pedido_calculo':
            query_pc = db.query(
                FeedbackPedidoCalculo,
                GeracaoPedidoCalculo.numero_cnj_formatado,
                GeracaoPedidoCalculo.numero_cnj,
                GeracaoPedidoCalculo.modelo_usado,
                User.username,
                User.full_name
            ).join(
                GeracaoPedidoCalculo, FeedbackPedidoCalculo.geracao_id == GeracaoPedidoCalculo.id
            ).join(
                User, FeedbackPedidoCalculo.usuario_id == User.id
            )

            if ids_excluir:
                query_pc = query_pc.filter(~FeedbackPedidoCalculo.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_pc = query_pc.filter(
                    FeedbackPedidoCalculo.criado_em >= data_inicio,
                    FeedbackPedidoCalculo.criado_em < data_fim
                )
            if avaliacao:
                query_pc = query_pc.filter(FeedbackPedidoCalculo.avaliacao == avaliacao)
            if usuario_id:
                query_pc = query_pc.filter(FeedbackPedidoCalculo.usuario_id == usuario_id)

            for fb, numero_cnj_fmt, numero_cnj, modelo_usado, username, full_name in query_pc.all():
                feedbacks_combinados.append({
                    "id": fb.id,
                    "consulta_id": fb.geracao_id,
                    "sistema": "pedido_calculo",
                    "identificador": numero_cnj_fmt or numero_cnj,
                    "cnj": numero_cnj,
                    "modelo": modelo_usado or "gemini-3-flash-preview",
                    "usuario": full_name or username,
                    "username": username,
                    "avaliacao": fb.avaliacao,
                    "comentario": fb.comentario,
                    "campos_incorretos": fb.campos_incorretos,
                    "criado_em": to_iso_utc(fb.criado_em),
                    "criado_em_dt": fb.criado_em
                })

        # Feedbacks de Prestação de Contas
        if sistema is None or sistema == 'prestacao_contas':
            query_prest = db.query(
                FeedbackPrestacao,
                GeracaoAnalise.numero_cnj_formatado,
                GeracaoAnalise.numero_cnj,
                GeracaoAnalise.modelo_usado,
                User.username,
                User.full_name
            ).join(
                GeracaoAnalise, FeedbackPrestacao.geracao_id == GeracaoAnalise.id
            ).join(
                User, FeedbackPrestacao.usuario_id == User.id
            )

            if ids_excluir:
                query_prest = query_prest.filter(~FeedbackPrestacao.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_prest = query_prest.filter(
                    FeedbackPrestacao.criado_em >= data_inicio,
                    FeedbackPrestacao.criado_em < data_fim
                )
            if avaliacao:
                query_prest = query_prest.filter(FeedbackPrestacao.avaliacao == avaliacao)
            if usuario_id:
                query_prest = query_prest.filter(FeedbackPrestacao.usuario_id == usuario_id)

            for fb, numero_cnj_fmt, numero_cnj, modelo_usado, username, full_name in query_prest.all():
                # Constrói campos_incorretos a partir dos booleanos específicos
                campos_incorretos = []
                if fb.parecer_correto is False:
                    campos_incorretos.append("parecer")
                if fb.valores_corretos is False:
                    campos_incorretos.append("valores")
                if fb.medicamento_correto is False:
                    campos_incorretos.append("medicamento")

                feedbacks_combinados.append({
                    "id": fb.id,
                    "consulta_id": fb.geracao_id,
                    "sistema": "prestacao_contas",
                    "identificador": numero_cnj_fmt or numero_cnj,
                    "cnj": numero_cnj,
                    "modelo": modelo_usado or "gemini-2.0-flash",
                    "usuario": full_name or username,
                    "username": username,
                    "avaliacao": fb.avaliacao,
                    "comentario": fb.comentario,
                    "campos_incorretos": campos_incorretos if campos_incorretos else None,
                    "criado_em": to_iso_utc(fb.criado_em),
                    "criado_em_dt": fb.criado_em
                })

        # Feedbacks de Relatório de Cumprimento
        if sistema is None or sistema == 'relatorio_cumprimento':
            query_rc = db.query(
                FeedbackRelatorioCumprimento,
                GeracaoRelatorioCumprimento.numero_cumprimento_formatado,
                GeracaoRelatorioCumprimento.numero_cumprimento,
                GeracaoRelatorioCumprimento.modelo_usado,
                User.username,
                User.full_name
            ).join(
                GeracaoRelatorioCumprimento, FeedbackRelatorioCumprimento.geracao_id == GeracaoRelatorioCumprimento.id
            ).join(
                User, FeedbackRelatorioCumprimento.usuario_id == User.id
            )

            if ids_excluir:
                query_rc = query_rc.filter(~FeedbackRelatorioCumprimento.usuario_id.in_(ids_excluir))
            if data_inicio and data_fim:
                query_rc = query_rc.filter(
                    FeedbackRelatorioCumprimento.criado_em >= data_inicio,
                    FeedbackRelatorioCumprimento.criado_em < data_fim
                )
            if avaliacao:
                query_rc = query_rc.filter(FeedbackRelatorioCumprimento.avaliacao == avaliacao)
            if usuario_id:
                query_rc = query_rc.filter(FeedbackRelatorioCumprimento.usuario_id == usuario_id)

            for fb, numero_cnj_fmt, numero_cnj, modelo_usado, username, full_name in query_rc.all():
                feedbacks_combinados.append({
                    "id": fb.id,
                    "consulta_id": fb.geracao_id,
                    "sistema": "relatorio_cumprimento",
                    "identificador": numero_cnj_fmt or numero_cnj,
                    "cnj": numero_cnj,
                    "modelo": modelo_usado or "gemini-2.0-flash",
                    "usuario": full_name or username,
                    "username": username,
                    "avaliacao": fb.avaliacao,
                    "comentario": fb.comentario,
                    "campos_incorretos": fb.campos_incorretos,
                    "criado_em": to_iso_utc(fb.criado_em),
                    "criado_em_dt": fb.criado_em
                })

        # Ordena por data (mais recentes primeiro)
        feedbacks_combinados.sort(key=lambda x: x.get('criado_em_dt') or datetime.min, reverse=True)
        
        # Remove campo auxiliar
        for fb in feedbacks_combinados:
            del fb['criado_em_dt']
        
        # Total e paginação
        total = len(feedbacks_combinados)
        total_pages = (total + per_page - 1) // per_page
        offset = (page - 1) * per_page
        feedbacks_paginados = feedbacks_combinados[offset:offset + per_page]
        
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "feedbacks": feedbacks_paginados
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedbacks/consulta/{consulta_id}")
async def obter_consulta_detalhes(
    consulta_id: int,
    sistema: str = "assistencia_judiciaria",
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Obtém detalhes de uma consulta/análise incluindo o relatório gerado.
    Apenas para administradores.
    """
    try:
        if sistema == "assistencia_judiciaria":
            consulta = db.query(
                ConsultaProcesso,
                User.username,
                User.full_name
            ).join(
                User, ConsultaProcesso.usuario_id == User.id
            ).filter(
                ConsultaProcesso.id == consulta_id
            ).first()
            
            if not consulta:
                raise HTTPException(status_code=404, detail="Consulta não encontrada")
            
            c, username, full_name = consulta
            
            # Busca feedback se existir
            feedback = db.query(FeedbackAnalise).filter(
                FeedbackAnalise.consulta_id == consulta_id
            ).first()
            
            return {
                "id": c.id,
                "sistema": "assistencia_judiciaria",
                "identificador": c.cnj_formatado or c.cnj,
                "cnj": c.cnj_formatado or c.cnj,
                "dados": c.dados_json,
                "relatorio": c.relatorio,
                "modelo": c.modelo_usado,
                "usuario": full_name or username,
                "consultado_em": to_iso_utc(c.consultado_em),
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": feedback.campos_incorretos if feedback else None,
                    "criado_em": to_iso_utc(feedback.criado_em) if feedback else None
                } if feedback else None
            }
        
        elif sistema == "matriculas":
            analise = db.query(
                Analise,
                User.username,
                User.full_name
            ).join(
                User, Analise.usuario_id == User.id
            ).filter(
                Analise.id == consulta_id
            ).first()
            
            if not analise:
                raise HTTPException(status_code=404, detail="Análise não encontrada")
            
            a, username, full_name = analise
            
            # Busca feedback se existir
            feedback = db.query(FeedbackMatricula).filter(
                FeedbackMatricula.analise_id == consulta_id
            ).first()
            
            return {
                "id": a.id,
                "sistema": "matriculas",
                "identificador": a.matricula_principal or a.file_name,
                "arquivo": a.file_name,
                "matricula_principal": a.matricula_principal,
                "dados": a.resultado_json,
                "relatorio": a.relatorio_texto,
                "modelo": a.modelo_usado,
                "usuario": full_name or username,
                "analisado_em": to_iso_utc(a.analisado_em),
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": feedback.campos_incorretos if feedback else None,
                    "criado_em": to_iso_utc(feedback.criado_em) if feedback else None
                } if feedback else None
            }

        elif sistema == "gerador_pecas":
            geracao = db.query(
                GeracaoPeca,
                User.username,
                User.full_name
            ).join(
                User, GeracaoPeca.usuario_id == User.id
            ).filter(
                GeracaoPeca.id == consulta_id
            ).first()

            if not geracao:
                raise HTTPException(status_code=404, detail="Geração não encontrada")

            g, username, full_name = geracao

            # Busca feedback se existir
            feedback = db.query(FeedbackPeca).filter(
                FeedbackPeca.geracao_id == consulta_id
            ).first()

            return {
                "id": g.id,
                "sistema": "gerador_pecas",
                "identificador": g.numero_cnj_formatado or g.numero_cnj or g.tipo_peca,
                "cnj": g.numero_cnj,
                "tipo_peca": g.tipo_peca,
                "dados": g.dados_processo,
                "relatorio": g.conteudo_gerado,
                "modelo": g.modelo_usado,
                "usuario": full_name or username,
                "criado_em": to_iso_utc(g.criado_em),
                "historico_chat": g.historico_chat,  # Histórico de edições via chat
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": feedback.campos_incorretos if feedback else None,
                    "criado_em": to_iso_utc(feedback.criado_em) if feedback else None
                } if feedback else None
            }

        elif sistema == "pedido_calculo":
            geracao = db.query(
                GeracaoPedidoCalculo,
                User.username,
                User.full_name
            ).join(
                User, GeracaoPedidoCalculo.usuario_id == User.id
            ).filter(
                GeracaoPedidoCalculo.id == consulta_id
            ).first()

            if not geracao:
                raise HTTPException(status_code=404, detail="Geração não encontrada")

            p, username, full_name = geracao

            # Busca feedback se existir
            feedback = db.query(FeedbackPedidoCalculo).filter(
                FeedbackPedidoCalculo.geracao_id == consulta_id
            ).first()

            return {
                "id": p.id,
                "sistema": "pedido_calculo",
                "identificador": p.numero_cnj_formatado or p.numero_cnj,
                "numero_processo": p.numero_cnj,
                "titulo": p.numero_cnj_formatado,
                "dados": p.dados_agente1,
                "relatorio": p.conteudo_gerado,
                "modelo": p.modelo_usado,
                "usuario": full_name or username,
                "analisado_em": to_iso_utc(p.criado_em),
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": feedback.campos_incorretos if feedback else None,
                    "criado_em": to_iso_utc(feedback.criado_em) if feedback else None
                } if feedback else None
            }

        elif sistema == "prestacao_contas":
            geracao = db.query(
                GeracaoAnalise,
                User.username,
                User.full_name
            ).join(
                User, GeracaoAnalise.usuario_id == User.id
            ).filter(
                GeracaoAnalise.id == consulta_id
            ).first()

            if not geracao:
                raise HTTPException(status_code=404, detail="Análise não encontrada")

            g, username, full_name = geracao

            # Busca feedback se existir
            feedback = db.query(FeedbackPrestacao).filter(
                FeedbackPrestacao.geracao_id == consulta_id
            ).first()

            return {
                "id": g.id,
                "sistema": "prestacao_contas",
                "identificador": g.numero_cnj_formatado or g.numero_cnj,
                "numero_processo": g.numero_cnj,
                "parecer": g.parecer,
                "dados": g.dados_processo_xml,
                "relatorio": g.fundamentacao,
                "modelo": g.modelo_usado,
                "usuario": full_name or username,
                "criado_em": to_iso_utc(g.criado_em),
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": None,
                    "criado_em": to_iso_utc(feedback.criado_em) if feedback else None
                } if feedback else None
            }

        elif sistema == "relatorio_cumprimento":
            geracao = db.query(
                GeracaoRelatorioCumprimento,
                User.username,
                User.full_name
            ).join(
                User, GeracaoRelatorioCumprimento.usuario_id == User.id
            ).filter(
                GeracaoRelatorioCumprimento.id == consulta_id
            ).first()

            if not geracao:
                raise HTTPException(status_code=404, detail="Relatório não encontrado")

            g, username, full_name = geracao

            # Busca feedback se existir
            feedback = db.query(FeedbackRelatorioCumprimento).filter(
                FeedbackRelatorioCumprimento.geracao_id == consulta_id
            ).first()

            return {
                "id": g.id,
                "sistema": "relatorio_cumprimento",
                "identificador": g.numero_cumprimento_formatado or g.numero_cumprimento,
                "numero_processo": g.numero_cumprimento,
                "numero_principal": g.numero_principal_formatado or g.numero_principal,
                "dados": g.dados_basicos,
                "relatorio": g.conteudo_gerado,
                "modelo": g.modelo_usado,
                "usuario": full_name or username,
                "criado_em": to_iso_utc(g.criado_em),
                "documentos_baixados": g.documentos_baixados,
                "transito_julgado_localizado": g.transito_julgado_localizado,
                "data_transito_julgado": g.data_transito_julgado,
                "historico_chat": g.historico_chat,
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": feedback.campos_incorretos if feedback else None,
                    "criado_em": to_iso_utc(feedback.criado_em) if feedback else None
                } if feedback else None
            }

        else:
            raise HTTPException(status_code=400, detail="Sistema inválido")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/feedbacks/exportar")
async def exportar_feedbacks(
    formato: str = "json",
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Exporta todos os feedbacks.
    Apenas para administradores.
    """
    try:
        data = []

        # Feedbacks de Assistência Judiciária
        feedbacks_aj = db.query(
            FeedbackAnalise,
            ConsultaProcesso.cnj_formatado,
            ConsultaProcesso.cnj,
            User.username,
            User.full_name
        ).join(
            ConsultaProcesso, FeedbackAnalise.consulta_id == ConsultaProcesso.id
        ).join(
            User, FeedbackAnalise.usuario_id == User.id
        ).order_by(
            FeedbackAnalise.criado_em.desc()
        ).all()

        for fb, cnj_fmt, cnj, username, full_name in feedbacks_aj:
            data.append({
                "id": fb.id,
                "sistema": "assistencia_judiciaria",
                "identificador": cnj_fmt or cnj,
                "usuario": full_name or username,
                "avaliacao": fb.avaliacao,
                "comentario": fb.comentario,
                "campos_incorretos": fb.campos_incorretos,
                "criado_em": to_iso_utc(fb.criado_em)
            })

        # Feedbacks de Matrículas
        feedbacks_mat = db.query(
            FeedbackMatricula,
            Analise.file_name,
            Analise.matricula_principal,
            User.username,
            User.full_name
        ).join(
            Analise, FeedbackMatricula.analise_id == Analise.id
        ).join(
            User, FeedbackMatricula.usuario_id == User.id
        ).order_by(
            FeedbackMatricula.criado_em.desc()
        ).all()

        for fb, file_name, matricula, username, full_name in feedbacks_mat:
            data.append({
                "id": fb.id,
                "sistema": "matriculas",
                "identificador": matricula or file_name,
                "usuario": full_name or username,
                "avaliacao": fb.avaliacao,
                "comentario": fb.comentario,
                "campos_incorretos": fb.campos_incorretos,
                "criado_em": to_iso_utc(fb.criado_em)
            })

        # Feedbacks de Gerador de Peças
        feedbacks_gp = db.query(
            FeedbackPeca,
            GeracaoPeca.numero_cnj,
            GeracaoPeca.tipo_peca,
            User.username,
            User.full_name
        ).join(
            GeracaoPeca, FeedbackPeca.geracao_id == GeracaoPeca.id
        ).join(
            User, FeedbackPeca.usuario_id == User.id
        ).order_by(
            FeedbackPeca.criado_em.desc()
        ).all()

        for fb, numero_cnj, tipo_peca, username, full_name in feedbacks_gp:
            data.append({
                "id": fb.id,
                "sistema": "gerador_pecas",
                "identificador": numero_cnj or tipo_peca,
                "usuario": full_name or username,
                "avaliacao": fb.avaliacao,
                "comentario": fb.comentario,
                "campos_incorretos": fb.campos_incorretos,
                "criado_em": to_iso_utc(fb.criado_em)
            })

        # Feedbacks de Pedido de Cálculo
        feedbacks_pc = db.query(
            FeedbackPedidoCalculo,
            GeracaoPedidoCalculo.numero_cnj_formatado,
            GeracaoPedidoCalculo.numero_cnj,
            User.username,
            User.full_name
        ).join(
            GeracaoPedidoCalculo, FeedbackPedidoCalculo.geracao_id == GeracaoPedidoCalculo.id
        ).join(
            User, FeedbackPedidoCalculo.usuario_id == User.id
        ).order_by(
            FeedbackPedidoCalculo.criado_em.desc()
        ).all()

        for fb, numero_cnj_fmt, numero_cnj, username, full_name in feedbacks_pc:
            data.append({
                "id": fb.id,
                "sistema": "pedido_calculo",
                "identificador": numero_cnj_fmt or numero_cnj,
                "usuario": full_name or username,
                "avaliacao": fb.avaliacao,
                "comentario": fb.comentario,
                "campos_incorretos": fb.campos_incorretos,
                "criado_em": to_iso_utc(fb.criado_em)
            })

        return {"feedbacks": data, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# Importar Prompts de Produção (TEMPORÁRIO)
# ============================================

from fastapi.responses import HTMLResponse

@router.get("/importar-prompts-producao", response_class=HTMLResponse)
async def pagina_importar_prompts(
    current_user: User = Depends(require_admin)
):
    """
    Página HTML para importar prompts - TEMPORÁRIO.
    Acesse no navegador e clique no botão.
    """
    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Importar Prompts - Admin</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="min-h-screen bg-gray-100 flex items-center justify-center p-4">
        <div class="bg-white rounded-2xl shadow-xl p-8 max-w-md w-full">
            <div class="text-center mb-6">
                <div class="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <svg class="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
                    </svg>
                </div>
                <h1 class="text-2xl font-bold text-gray-800">Importar Prompts</h1>
                <p class="text-gray-500 mt-2">Pedido de Cálculo e Prestação de Contas</p>
            </div>

            <div id="info" class="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
                <p class="text-sm text-blue-800">
                    <strong>O que será importado:</strong><br>
                    • 6 prompts (3 pedido_calculo + 3 prestacao_contas)<br>
                    • 9 configurações de IA (modelos e temperaturas)<br>
                    • O arquivo SQL será deletado após a importação
                </p>
            </div>

            <div id="resultado" class="hidden mb-6"></div>

            <button id="btnImportar" onclick="importarPrompts()"
                class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-xl transition-colors flex items-center justify-center gap-2">
                <span id="btnTexto">Importar Prompts</span>
                <svg id="btnSpinner" class="hidden animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
            </button>

            <p class="text-xs text-gray-400 text-center mt-4">
                Endpoint temporário - será removido após uso
            </p>
        </div>

        <script>
            async function importarPrompts() {
                const btn = document.getElementById('btnImportar');
                const btnTexto = document.getElementById('btnTexto');
                const btnSpinner = document.getElementById('btnSpinner');
                const resultado = document.getElementById('resultado');
                const info = document.getElementById('info');

                btn.disabled = true;
                btnTexto.textContent = 'Importando...';
                btnSpinner.classList.remove('hidden');

                try {
                    const token = localStorage.getItem('access_token');
                    const response = await fetch('/admin/importar-prompts-producao', {
                        method: 'POST',
                        headers: {
                            'Authorization': 'Bearer ' + token,
                            'Content-Type': 'application/json'
                        }
                    });

                    const data = await response.json();

                    info.classList.add('hidden');
                    resultado.classList.remove('hidden');

                    if (response.ok) {
                        resultado.className = 'bg-green-50 border border-green-200 rounded-xl p-4 mb-6';
                        resultado.innerHTML = `
                            <div class="flex items-center gap-2 text-green-800">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                                </svg>
                                <strong>Sucesso!</strong>
                            </div>
                            <p class="text-sm text-green-700 mt-2">${data.message}</p>
                        `;
                        btn.classList.add('hidden');
                    } else {
                        resultado.className = 'bg-red-50 border border-red-200 rounded-xl p-4 mb-6';
                        resultado.innerHTML = `
                            <div class="flex items-center gap-2 text-red-800">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                </svg>
                                <strong>Erro</strong>
                            </div>
                            <p class="text-sm text-red-700 mt-2">${data.detail || 'Erro desconhecido'}</p>
                        `;
                        btn.disabled = false;
                        btnTexto.textContent = 'Tentar Novamente';
                        btnSpinner.classList.add('hidden');
                    }
                } catch (error) {
                    resultado.classList.remove('hidden');
                    resultado.className = 'bg-red-50 border border-red-200 rounded-xl p-4 mb-6';
                    resultado.innerHTML = `
                        <div class="flex items-center gap-2 text-red-800">
                            <strong>Erro de conexão</strong>
                        </div>
                        <p class="text-sm text-red-700 mt-2">${error.message}</p>
                    `;
                    btn.disabled = false;
                    btnTexto.textContent = 'Tentar Novamente';
                    btnSpinner.classList.add('hidden');
                }
            }
        </script>
    </body>
    </html>
    """


@router.post("/importar-prompts-producao")
async def importar_prompts_producao(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Importa os prompts de pedido_calculo e prestacao_contas do arquivo SQL.

    ENDPOINT TEMPORÁRIO - Deve ser removido após uso.
    Apenas para administradores.
    """
    import os
    import sqlite3

    script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'scripts', 'prompts_producao.sql')

    if not os.path.exists(script_path):
        raise HTTPException(
            status_code=404,
            detail=f"Arquivo de prompts não encontrado. Já foi importado anteriormente?"
        )

    try:
        # Lê o conteúdo do script SQL
        with open(script_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # Obtém o caminho do banco de dados da conexão atual
        db_path = db.bind.url.database

        # Executa o script SQL diretamente
        conn = sqlite3.connect(db_path)
        conn.executescript(sql_content)
        conn.commit()
        conn.close()

        # Remove o arquivo SQL após execução bem-sucedida
        os.remove(script_path)

        return {
            "success": True,
            "message": "Prompts importados com sucesso! Arquivo SQL removido.",
            "arquivo_removido": script_path
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao importar prompts: {str(e)}"
        )


# ============================================
# Glossário de Conceitos (Ajuda)
# ============================================

@router.get("/help/glossary")
async def obter_glossario(
    current_user: User = Depends(get_current_active_user)
):
    """
    Retorna o conteúdo do glossário de conceitos do sistema.
    O glossário está em formato Markdown.
    """
    import os

    # Caminho do arquivo do glossário
    glossary_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'docs',
        'GLOSSARIO_CONCEITOS.md'
    )

    if not os.path.exists(glossary_path):
        raise HTTPException(
            status_code=404,
            detail="Arquivo de glossário não encontrado"
        )

    try:
        with open(glossary_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            "success": True,
            "content": content,
            "format": "markdown"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao ler glossário: {str(e)}"
        )
