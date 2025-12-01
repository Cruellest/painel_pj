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
    configs = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.chave == "modelo"
    ).all()
    
    resultado = {}
    for config in configs:
        resultado[config.sistema] = {
            "id": config.id,
            "modelo": config.valor,
            "descricao": config.descricao
        }
    
    # Adiciona valores padrão se não existirem
    if "assistencia_judiciaria" not in resultado:
        resultado["assistencia_judiciaria"] = {
            "id": None,
            "modelo": "google/gemini-2.5-flash",
            "descricao": "Modelo para análise de processos judiciais"
        }
    if "matriculas" not in resultado:
        resultado["matriculas"] = {
            "id": None,
            "modelo": "google/gemini-2.5-flash",
            "descricao": "Modelo para análise de matrículas imobiliárias"
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
    
    # Verifica ambiente
    env_key = os.getenv("OPENROUTER_API_KEY", "")
    if env_key:
        return {"configured": True, "source": "environment"}
    
    # Verifica banco
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "global",
        ConfiguracaoIA.chave == "openrouter_api_key"
    ).first()
    
    if config and config.valor:
        return {"configured": True, "source": "database"}
    
    return {"configured": False, "source": None}


@router.put("/api-key")
async def update_api_key(
    api_key: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Atualiza a API key global do OpenRouter (apenas admin)"""
    if not api_key or not api_key.strip():
        raise HTTPException(status_code=400, detail="API Key não pode estar vazia")
    
    config = db.query(ConfiguracaoIA).filter(
        ConfiguracaoIA.sistema == "global",
        ConfiguracaoIA.chave == "openrouter_api_key"
    ).first()
    
    if config:
        config.valor = api_key.strip()
    else:
        config = ConfiguracaoIA(
            sistema="global",
            chave="openrouter_api_key",
            valor=api_key.strip(),
            tipo_valor="string",
            descricao="API Key do OpenRouter (compartilhada por todos os sistemas)"
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
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retorna estatísticas do dashboard de feedbacks de ambos os sistemas.
    Exclui feedbacks de usuários admin e teste.
    Apenas para administradores.
    """
    try:
        # Usuarios a excluir (admin e teste)
        usuarios_excluir = db.query(User.id).filter(
            (User.role == 'admin') | (User.username.ilike('%teste%')) | (User.username.ilike('%test%'))
        ).all()
        ids_excluir = [u.id for u in usuarios_excluir]
        
        # === Sistema Assistência Judiciária ===
        total_consultas_aj = db.query(ConsultaProcesso).count()
        total_feedbacks_aj = db.query(FeedbackAnalise).filter(
            ~FeedbackAnalise.usuario_id.in_(ids_excluir) if ids_excluir else True
        ).count()
        
        feedbacks_por_avaliacao_aj = db.query(
            FeedbackAnalise.avaliacao,
            func.count(FeedbackAnalise.id).label('count')
        ).filter(
            ~FeedbackAnalise.usuario_id.in_(ids_excluir) if ids_excluir else True
        ).group_by(FeedbackAnalise.avaliacao).all()
        
        # === Sistema Matrículas ===
        total_analises_mat = db.query(Analise).count()
        total_feedbacks_mat = db.query(FeedbackMatricula).filter(
            ~FeedbackMatricula.usuario_id.in_(ids_excluir) if ids_excluir else True
        ).count()
        
        feedbacks_por_avaliacao_mat = db.query(
            FeedbackMatricula.avaliacao,
            func.count(FeedbackMatricula.id).label('count')
        ).filter(
            ~FeedbackMatricula.usuario_id.in_(ids_excluir) if ids_excluir else True
        ).group_by(FeedbackMatricula.avaliacao).all()
        
        # === Totais combinados ===
        total_consultas = total_consultas_aj + total_analises_mat
        total_feedbacks = total_feedbacks_aj + total_feedbacks_mat
        
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
        
        # Taxa de acerto (correto / total feedbacks)
        taxa_acerto = 0
        if total_feedbacks > 0:
            taxa_acerto = round((avaliacoes['correto'] / total_feedbacks) * 100, 1)
        
        # Feedbacks dos últimos 7 dias (combinados) - excluindo admin/teste
        data_limite = datetime.utcnow() - timedelta(days=7)
        feedbacks_recentes_aj = db.query(
            func.date(FeedbackAnalise.criado_em).label('data'),
            func.count(FeedbackAnalise.id).label('count')
        ).filter(
            FeedbackAnalise.criado_em >= data_limite,
            ~FeedbackAnalise.usuario_id.in_(ids_excluir) if ids_excluir else True
        ).group_by(
            func.date(FeedbackAnalise.criado_em)
        ).all()
        
        feedbacks_recentes_mat = db.query(
            func.date(FeedbackMatricula.criado_em).label('data'),
            func.count(FeedbackMatricula.id).label('count')
        ).filter(
            FeedbackMatricula.criado_em >= data_limite,
            ~FeedbackMatricula.usuario_id.in_(ids_excluir) if ids_excluir else True
        ).group_by(
            func.date(FeedbackMatricula.criado_em)
        ).all()
        
        # Combina feedbacks recentes por data
        feedbacks_por_data = {}
        for data, count in feedbacks_recentes_aj:
            feedbacks_por_data[str(data)] = feedbacks_por_data.get(str(data), 0) + count
        for data, count in feedbacks_recentes_mat:
            feedbacks_por_data[str(data)] = feedbacks_por_data.get(str(data), 0) + count
        
        feedbacks_recentes = [{"data": data, "count": count} for data, count in sorted(feedbacks_por_data.items())]
        
        # Feedbacks por usuário (top 10) - combinando ambos os sistemas, excluindo admin/teste
        feedbacks_por_usuario_aj = db.query(
            User.username,
            User.full_name,
            func.count(FeedbackAnalise.id).label('total'),
            func.sum(case((FeedbackAnalise.avaliacao == 'correto', 1), else_=0)).label('corretos')
        ).join(
            FeedbackAnalise, FeedbackAnalise.usuario_id == User.id
        ).filter(
            ~User.id.in_(ids_excluir) if ids_excluir else True
        ).group_by(
            User.id, User.username, User.full_name
        ).all()
        
        feedbacks_por_usuario_mat = db.query(
            User.username,
            User.full_name,
            func.count(FeedbackMatricula.id).label('total'),
            func.sum(case((FeedbackMatricula.avaliacao == 'correto', 1), else_=0)).label('corretos')
        ).join(
            FeedbackMatricula, FeedbackMatricula.usuario_id == User.id
        ).filter(
            ~User.id.in_(ids_excluir) if ids_excluir else True
        ).group_by(
            User.id, User.username, User.full_name
        ).all()
        
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
        
        feedbacks_por_usuario = sorted(
            [{"username": k, **v} for k, v in usuarios_stats.items()],
            key=lambda x: x["total"],
            reverse=True
        )[:10]
        
        # Usuários que geraram relatório mas não deram feedback
        # Assistência Judiciária
        consultas_sem_feedback_aj = db.query(
            ConsultaProcesso.id,
            ConsultaProcesso.cnj_formatado,
            ConsultaProcesso.cnj,
            ConsultaProcesso.criado_em,
            User.username,
            User.full_name
        ).outerjoin(
            FeedbackAnalise, FeedbackAnalise.consulta_id == ConsultaProcesso.id
        ).join(
            User, ConsultaProcesso.usuario_id == User.id
        ).filter(
            FeedbackAnalise.id == None,
            ConsultaProcesso.analise_ia.isnot(None),
            ~ConsultaProcesso.usuario_id.in_(ids_excluir) if ids_excluir else True
        ).order_by(
            ConsultaProcesso.criado_em.desc()
        ).limit(20).all()
        
        # Matrículas
        analises_sem_feedback_mat = db.query(
            Analise.id,
            Analise.file_name,
            Analise.matricula_principal,
            Analise.criado_em,
            User.username,
            User.full_name
        ).outerjoin(
            FeedbackMatricula, FeedbackMatricula.analise_id == Analise.id
        ).join(
            User, Analise.usuario_id == User.id
        ).filter(
            FeedbackMatricula.id == None,
            Analise.resultado_analise.isnot(None),
            ~Analise.usuario_id.in_(ids_excluir) if ids_excluir else True
        ).order_by(
            Analise.criado_em.desc()
        ).limit(20).all()
        
        # Combina e formata
        pendentes_feedback = []
        for id, cnj_fmt, cnj, criado_em, username, full_name in consultas_sem_feedback_aj:
            pendentes_feedback.append({
                "sistema": "assistencia_judiciaria",
                "identificador": cnj_fmt or cnj,
                "usuario": full_name or username,
                "data": criado_em.isoformat() if criado_em else None
            })
        for id, file_name, matricula, criado_em, username, full_name in analises_sem_feedback_mat:
            pendentes_feedback.append({
                "sistema": "matriculas",
                "identificador": matricula or file_name,
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
            "por_sistema": {
                "assistencia_judiciaria": {
                    "total": total_consultas_aj,
                    "feedbacks": total_feedbacks_aj
                },
                "matriculas": {
                    "total": total_analises_mat,
                    "feedbacks": total_feedbacks_mat
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
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Lista todos os feedbacks com paginação e filtros.
    Exclui feedbacks de usuários admin e teste.
    Apenas para administradores.
    """
    try:
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
            ).filter(
                ~FeedbackAnalise.usuario_id.in_(ids_excluir) if ids_excluir else True
            )
            
            if avaliacao:
                query_aj = query_aj.filter(FeedbackAnalise.avaliacao == avaliacao)
            if usuario_id:
                query_aj = query_aj.filter(FeedbackAnalise.usuario_id == usuario_id)
            
            for fb, cnj_fmt, cnj, modelo, username, full_name in query_aj.all():
                feedbacks_combinados.append({
                    "id": fb.id,
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
                User.username,
                User.full_name
            ).join(
                Analise, FeedbackMatricula.analise_id == Analise.id
            ).join(
                User, FeedbackMatricula.usuario_id == User.id
            ).filter(
                ~FeedbackMatricula.usuario_id.in_(ids_excluir) if ids_excluir else True
            )
            
            if avaliacao:
                query_mat = query_mat.filter(FeedbackMatricula.avaliacao == avaliacao)
            if usuario_id:
                query_mat = query_mat.filter(FeedbackMatricula.usuario_id == usuario_id)
            
            # Buscar modelo configurado para matrículas
            modelo_mat = db.query(ConfiguracaoIA).filter(
                ConfiguracaoIA.sistema == "matriculas",
                ConfiguracaoIA.chave == "modelo"
            ).first()
            modelo_matriculas = modelo_mat.valor if modelo_mat else "google/gemini-2.5-flash"
            
            for fb, file_name, matricula, username, full_name in query_mat.all():
                feedbacks_combinados.append({
                    "id": fb.id,
                    "sistema": "matriculas",
                    "identificador": matricula or file_name,
                    "cnj": None,
                    "modelo": modelo_matriculas,
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
        feedbacks = db.query(
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
        
        data = [
            {
                "id": fb.id,
                "cnj": cnj_fmt or cnj,
                "usuario": full_name or username,
                "avaliacao": fb.avaliacao,
                "comentario": fb.comentario,
                "campos_incorretos": fb.campos_incorretos,
                "criado_em": fb.criado_em.isoformat() if fb.criado_em else None
            }
            for fb, cnj_fmt, cnj, username, full_name in feedbacks
        ]
        
        return {"feedbacks": data, "total": len(data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
