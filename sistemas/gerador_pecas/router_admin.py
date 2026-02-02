# sistemas/gerador_pecas/router_admin.py
"""
Router de administração do Gerador de Peças
- Visualização de prompts enviados
- Histórico detalhado de gerações
"""

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime

from auth.dependencies import get_current_active_user
from auth.models import User
from database.connection import get_db
from utils.timezone import to_iso_utc
from sistemas.gerador_pecas.models import GeracaoPeca, VersaoPeca

router = APIRouter(prefix="/gerador-pecas-admin", tags=["Gerador de Peças - Admin"])


# ==========================================
# Schemas
# ==========================================

class GeracaoDetalhadaResponse(BaseModel):
    id: int
    numero_cnj: str
    numero_cnj_formatado: Optional[str]
    tipo_peca: Optional[str]
    modelo_usado: Optional[str]
    tempo_processamento: Optional[int]
    prompt_enviado: Optional[str]
    resumo_consolidado: Optional[str]
    conteudo_gerado: Optional[str] = None  # Markdown string
    historico_chat: Optional[List[Any]] = None  # Histórico de edições via chat
    modo_ativacao_agente2: Optional[str] = None  # 'fast_path', 'misto', 'llm', 'semi_automatico'
    modulos_ativados_det: Optional[int] = None  # Ativados por regra determinística (ou total-manuais no semi_automatico)
    modulos_ativados_llm: Optional[int] = None  # Ativados por LLM (ou manuais no semi_automatico)
    criado_em: datetime

    class Config:
        from_attributes = True


# ==========================================
# Endpoints de Histórico de Gerações
# ==========================================

def _safe_get_attr(obj, attr, default=None):
    """Obtém atributo de forma segura, retornando default se coluna não existe no banco"""
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _geracao_to_dict(geracao: GeracaoPeca) -> dict:
    """Converte GeracaoPeca para dict, tratando colunas que podem não existir"""
    return {
        "id": geracao.id,
        "numero_cnj": geracao.numero_cnj,
        "numero_cnj_formatado": geracao.numero_cnj_formatado,
        "tipo_peca": geracao.tipo_peca,
        "modelo_usado": geracao.modelo_usado,
        "tempo_processamento": geracao.tempo_processamento,
        "prompt_enviado": geracao.prompt_enviado,
        "resumo_consolidado": geracao.resumo_consolidado,
        "conteudo_gerado": geracao.conteudo_gerado,
        "historico_chat": geracao.historico_chat,
        # Colunas que podem não existir em produção (migration pendente)
        "modo_ativacao_agente2": _safe_get_attr(geracao, 'modo_ativacao_agente2'),
        "modulos_ativados_det": _safe_get_attr(geracao, 'modulos_ativados_det'),
        "modulos_ativados_llm": _safe_get_attr(geracao, 'modulos_ativados_llm'),
        "criado_em": geracao.criado_em,
    }


@router.get("/geracoes", response_model=List[GeracaoDetalhadaResponse])
async def listar_geracoes(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista histórico de gerações com detalhes"""
    geracoes = db.query(GeracaoPeca).order_by(
        GeracaoPeca.criado_em.desc()
    ).offset(offset).limit(limit).all()

    return [_geracao_to_dict(g) for g in geracoes]


@router.get("/geracoes/{geracao_id}", response_model=GeracaoDetalhadaResponse)
async def obter_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de uma geração específica"""
    geracao = db.query(GeracaoPeca).filter(GeracaoPeca.id == geracao_id).first()
    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")
    return _geracao_to_dict(geracao)


@router.get("/geracoes/{geracao_id}/prompt")
async def obter_prompt_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém apenas o prompt enviado de uma geração"""
    geracao = db.query(GeracaoPeca).filter(GeracaoPeca.id == geracao_id).first()
    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")
    
    return {
        "id": geracao.id,
        "numero_cnj": geracao.numero_cnj_formatado or geracao.numero_cnj,
        "tipo_peca": geracao.tipo_peca,
        "prompt_enviado": geracao.prompt_enviado,
        "resumo_consolidado": geracao.resumo_consolidado,
        "criado_em": to_iso_utc(geracao.criado_em)
    }


@router.get("/geracoes/{geracao_id}/versoes")
async def listar_versoes_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todas as versões de uma geração"""
    geracao = db.query(GeracaoPeca).filter(GeracaoPeca.id == geracao_id).first()
    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")

    versoes = db.query(VersaoPeca).filter(
        VersaoPeca.geracao_id == geracao_id
    ).order_by(VersaoPeca.numero_versao.desc()).all()

    return {
        "geracao_id": geracao_id,
        "total_versoes": len(versoes),
        "versoes": [
            {
                "id": v.id,
                "numero_versao": v.numero_versao,
                "tipo_alteracao": v.origem,  # Campo correto do modelo
                "descricao": v.descricao_alteracao,  # Campo correto do modelo
                "conteudo_markdown": v.conteudo,  # Campo correto do modelo
                "criado_em": to_iso_utc(v.criado_em)
            }
            for v in versoes
        ]
    }


@router.get("/geracoes/{geracao_id}/versoes/{versao_id}")
async def obter_versao_geracao(
    geracao_id: int,
    versao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Obtém detalhes de uma versão específica"""
    versao = db.query(VersaoPeca).filter(
        VersaoPeca.id == versao_id,
        VersaoPeca.geracao_id == geracao_id
    ).first()

    if not versao:
        raise HTTPException(status_code=404, detail="Versão não encontrada")

    return {
        "id": versao.id,
        "geracao_id": versao.geracao_id,
        "numero_versao": versao.numero_versao,
        "tipo_alteracao": versao.origem,  # Campo correto do modelo
        "descricao": versao.descricao_alteracao,  # Campo correto do modelo
        "conteudo_markdown": versao.conteudo,  # Campo correto do modelo
        "criado_em": to_iso_utc(versao.criado_em)
    }


@router.get("/geracoes/{geracao_id}/curadoria")
async def obter_curadoria_geracao(
    geracao_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Obtém detalhes completos de curadoria de uma geração no modo semi-automático.

    Retorna informações detalhadas para auditoria e transparência:
    - Metadados de curadoria (IDs, contagens, timestamp)
    - Lista completa de módulos incluídos com: título, categoria, conteúdo, origem, decisão
    - Lista de módulos excluídos com: título, categoria, conteúdo, motivo
    - Ordem das categorias definida pelo usuário
    - Explicações semânticas de cada status/decisão
    """
    from admin.models_prompts import PromptModulo

    geracao = db.query(GeracaoPeca).filter(GeracaoPeca.id == geracao_id).first()
    if not geracao:
        raise HTTPException(status_code=404, detail="Geração não encontrada")

    # Verifica se é modo semi-automático
    modo = _safe_get_attr(geracao, 'modo_ativacao_agente2')
    if modo != 'semi_automatico':
        raise HTTPException(
            status_code=404,
            detail="Esta geração não foi feita no modo semi-automático"
        )

    # Obtém metadados de curadoria
    metadata = _safe_get_attr(geracao, 'curadoria_metadata') or {}

    # IDs dos módulos
    modulos_curados_ids = metadata.get('modulos_curados_ids', [])
    modulos_manuais_ids = metadata.get('modulos_manuais_ids', [])
    modulos_excluidos_ids = metadata.get('modulos_excluidos_ids', [])
    modulos_preview_ids = metadata.get('modulos_preview_ids', [])

    # Busca dados completos dos módulos no banco (incluindo conteúdo)
    todos_ids = set(modulos_curados_ids + modulos_manuais_ids + modulos_excluidos_ids + modulos_preview_ids)
    modulos_db = {}
    if todos_ids:
        modulos = db.query(PromptModulo).filter(PromptModulo.id.in_(todos_ids)).all()
        modulos_db = {
            m.id: {
                "id": m.id,
                "titulo": m.titulo,
                "categoria": m.categoria or "Outros",
                "subcategoria": m.subcategoria,
                "conteudo": m.conteudo,  # Conteúdo completo para transparência
                "modo_ativacao_modulo": m.modo_ativacao or "llm"  # Como o módulo é normalmente ativado
            }
            for m in modulos
        }

    # Usa modulos_detalhados se disponível (nova estrutura), senão reconstrói
    modulos_detalhados = metadata.get('modulos_detalhados', [])
    manuais_set = set(modulos_manuais_ids)
    preview_set = set(modulos_preview_ids)

    # Monta listas com informações completas de auditoria
    modulos_incluidos = []
    for i, mid in enumerate(modulos_curados_ids):
        base_info = modulos_db.get(mid, {
            "id": mid,
            "titulo": f"Módulo {mid}",
            "categoria": "Desconhecido",
            "subcategoria": None,
            "conteudo": "(Conteúdo não disponível)",
            "modo_ativacao_modulo": "desconhecido"
        })
        info = base_info.copy()

        # Determina origem e tipo de decisão
        if modulos_detalhados and i < len(modulos_detalhados):
            detalhe = modulos_detalhados[i]
            info["origem"] = detalhe.get("origem", "desconhecido")
        else:
            info["origem"] = "manual" if mid in manuais_set else ("preview" if mid in preview_set else "automatico")

        # Define status com tag HUMAN_VALIDATED e explicação semântica
        if info["origem"] == "manual":
            info["tag"] = "[HUMAN_VALIDATED:MANUAL]"
            info["tipo_decisao"] = "manual"
            info["decisao_explicacao"] = "Adicionado manualmente pelo usuário durante a curadoria"
            info["motivo_inclusao"] = "O usuário escolheu incluir este argumento que não estava na sugestão automática"
        else:
            info["tag"] = "[HUMAN_VALIDATED]"
            info["tipo_decisao"] = "confirmado"
            info["decisao_explicacao"] = "Sugerido automaticamente e confirmado pelo usuário"
            info["motivo_inclusao"] = "O sistema sugeriu este argumento e o usuário confirmou sua inclusão"

        info["ordem"] = i + 1  # Posição na ordem final
        info["status_final"] = "incluido"
        modulos_incluidos.append(info)

    # Módulos excluídos com explicação
    modulos_excluidos = []
    for mid in modulos_excluidos_ids:
        base_info = modulos_db.get(mid, {
            "id": mid,
            "titulo": f"Módulo {mid}",
            "categoria": "Desconhecido",
            "subcategoria": None,
            "conteudo": "(Conteúdo não disponível)",
            "modo_ativacao_modulo": "desconhecido"
        })
        info = base_info.copy()
        info["origem"] = "preview"  # Excluídos sempre vêm do preview
        info["tag"] = "[EXCLUÍDO]"
        info["tipo_decisao"] = "removido"
        info["decisao_explicacao"] = "Sugerido automaticamente mas removido pelo usuário"
        info["motivo_exclusao"] = "O sistema sugeriu este argumento, mas o usuário decidiu não incluí-lo na peça final"
        info["status_final"] = "excluido"
        modulos_excluidos.append(info)

    # Calcula estatísticas detalhadas
    total_preview = metadata.get('total_preview', len(modulos_preview_ids))
    total_confirmados = len([m for m in modulos_incluidos if m["tipo_decisao"] == "confirmado"])
    total_manuais = len([m for m in modulos_incluidos if m["tipo_decisao"] == "manual"])
    total_excluidos = len(modulos_excluidos)

    return {
        "geracao_id": geracao_id,
        "modo": "semi_automatico",
        "metadata": {
            "total_preview": total_preview,
            "total_incluidos": len(modulos_incluidos),
            "total_confirmados": total_confirmados,
            "total_manuais": total_manuais,
            "total_excluidos": total_excluidos,
            "preview_timestamp": metadata.get('preview_timestamp'),
            "categorias_ordem": metadata.get('categorias_ordem', [])
        },
        # Glossário de termos para a UI exibir
        "glossario": {
            "HUMAN_VALIDATED": "Argumento validado pelo usuário - será incluído integralmente na peça final sem modificação pela IA",
            "HUMAN_VALIDATED:MANUAL": "Argumento adicionado manualmente pelo usuário - não estava na sugestão automática",
            "confirmado": "Argumento sugerido pelo sistema e confirmado pelo usuário",
            "manual": "Argumento adicionado pelo usuário durante a revisão",
            "removido": "Argumento sugerido pelo sistema mas removido pelo usuário",
            "preview": "Sugestão automática do sistema (Agente 2) antes da revisão humana",
            "incluido": "Este argumento FAZ PARTE da peça final gerada",
            "excluido": "Este argumento NÃO FAZ PARTE da peça final gerada"
        },
        # Explicação do processo para transparência
        "explicacao_processo": {
            "titulo": "Como funciona o Modo Semi-Automático",
            "etapas": [
                "1. O sistema analisa o processo e sugere argumentos relevantes (Preview)",
                "2. O usuário revisa a sugestão, podendo confirmar, remover ou adicionar argumentos",
                "3. Argumentos confirmados recebem a tag [HUMAN_VALIDATED]",
                "4. Argumentos adicionados manualmente recebem [HUMAN_VALIDATED:MANUAL]",
                "5. A IA recebe instrução de usar estes argumentos integralmente, sem modificação"
            ],
            "garantia": "Todos os argumentos marcados como HUMAN_VALIDATED são incluídos na peça final exatamente como validados pelo usuário."
        },
        "modulos_incluidos": modulos_incluidos,
        "modulos_excluidos": modulos_excluidos
    }
