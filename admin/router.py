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


@router.post("/prompts/reset-defaults")
async def reset_default_prompts(
    sistema: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Restaura os prompts padrão do sistema"""
    # Remove prompts existentes do sistema especificado ou todos
    query = db.query(PromptConfig)
    if sistema:
        query = query.filter(PromptConfig.sistema == sistema)
    
    count = query.delete()
    db.commit()
    
    # Recria prompts padrão
    seed_default_prompts(db, sistema)
    
    return {
        "success": True, 
        "message": f"{count} prompt(s) removido(s) e padrões restaurados"
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

        # === Totais combinados ===
        total_consultas = total_consultas_aj + total_analises_mat + total_geracoes_gp + total_geracoes_pc
        total_feedbacks = total_feedbacks_aj + total_feedbacks_mat + total_feedbacks_gp + total_feedbacks_pc
        
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
        
        feedbacks_recentes = [{"data": data, "count": count} for data, count in sorted(feedbacks_por_data.items())]
        
        # Feedbacks por usuário (top 10) - combinando sistemas selecionados
        feedbacks_por_usuario_aj = []
        feedbacks_por_usuario_mat = []
        feedbacks_por_usuario_gp = []
        feedbacks_por_usuario_pc = []
        
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

        # Combina e formata
        pendentes_feedback = []
        for id, cnj_fmt, cnj, consultado_em, username, full_name in consultas_sem_feedback_aj:
            pendentes_feedback.append({
                "id": id,
                "sistema": "assistencia_judiciaria",
                "identificador": cnj_fmt or cnj,
                "usuario": full_name or username,
                "data": consultado_em.isoformat() if consultado_em else None
            })
        for id, file_name, matricula, analisado_em, username, full_name in analises_sem_feedback_mat:
            pendentes_feedback.append({
                "id": id,
                "sistema": "matriculas",
                "identificador": matricula or file_name,
                "usuario": full_name or username,
                "data": analisado_em.isoformat() if analisado_em else None
            })
        for id, tipo_peca, numero_cnj, criado_em, username, full_name in geracoes_sem_feedback_gp:
            pendentes_feedback.append({
                "id": id,
                "sistema": "gerador_pecas",
                "identificador": numero_cnj or tipo_peca,
                "usuario": full_name or username,
                "data": criado_em.isoformat() if criado_em else None
            })
        for id, numero_cnj_fmt, numero_cnj, criado_em, username, full_name in geracoes_sem_feedback_pc:
            pendentes_feedback.append({
                "id": id,
                "sistema": "pedido_calculo",
                "identificador": numero_cnj_fmt or numero_cnj,
                "usuario": full_name or username,
                "data": criado_em.isoformat() if criado_em else None
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
                    "criado_em": fb.criado_em.isoformat() if fb.criado_em else None,
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
                    "criado_em": fb.criado_em.isoformat() if fb.criado_em else None,
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
                    "criado_em": fb.criado_em.isoformat() if fb.criado_em else None,
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
                    "criado_em": fb.criado_em.isoformat() if fb.criado_em else None,
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
                "consultado_em": c.consultado_em.isoformat() if c.consultado_em else None,
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": feedback.campos_incorretos if feedback else None,
                    "criado_em": feedback.criado_em.isoformat() if feedback and feedback.criado_em else None
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
                "analisado_em": a.analisado_em.isoformat() if a.analisado_em else None,
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": feedback.campos_incorretos if feedback else None,
                    "criado_em": feedback.criado_em.isoformat() if feedback and feedback.criado_em else None
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
                "analisado_em": g.criado_em.isoformat() if g.criado_em else None,
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": feedback.campos_incorretos if feedback else None,
                    "criado_em": feedback.criado_em.isoformat() if feedback and feedback.criado_em else None
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
                "analisado_em": p.criado_em.isoformat() if p.criado_em else None,
                "feedback": {
                    "avaliacao": feedback.avaliacao if feedback else None,
                    "comentario": feedback.comentario if feedback else None,
                    "campos_incorretos": feedback.campos_incorretos if feedback else None,
                    "criado_em": feedback.criado_em.isoformat() if feedback and feedback.criado_em else None
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
                "criado_em": fb.criado_em.isoformat() if fb.criado_em else None
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
                "criado_em": fb.criado_em.isoformat() if fb.criado_em else None
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
                "criado_em": fb.criado_em.isoformat() if fb.criado_em else None
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
                "criado_em": fb.criado_em.isoformat() if fb.criado_em else None
            })

        return {"feedbacks": data, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
