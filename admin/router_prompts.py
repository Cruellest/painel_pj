# admin/router_prompts.py
"""
Router para gerenciamento de prompts modulares
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import difflib

from database.connection import get_db
from auth.models import User
from auth.dependencies import get_current_active_user, require_admin
from admin.models_prompts import PromptModulo, PromptModuloHistorico, ModuloTipoPeca

router = APIRouter(prefix="/prompts-modulos", tags=["Prompts Modulares"])


# ==========================================
# Schemas
# ==========================================

class PromptModuloBase(BaseModel):
    tipo: str  # 'base', 'peca', 'conteudo'
    categoria: Optional[str] = None
    subcategoria: Optional[str] = None
    nome: str
    titulo: str
    condicao_ativacao: Optional[str] = None  # Situação em que o prompt deve ser ativado (para Agente 2)
    conteudo: str  # Conteúdo do prompt (para Agente 3)
    palavras_chave: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    ativo: bool = True
    ordem: int = 0


class PromptModuloCreate(PromptModuloBase):
    pass


class PromptModuloUpdate(BaseModel):
    titulo: Optional[str] = None
    condicao_ativacao: Optional[str] = None  # Atualiza condição de ativação
    conteudo: Optional[str] = None
    palavras_chave: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    ativo: Optional[bool] = None
    ordem: Optional[int] = None
    motivo: str  # Obrigatório para rastrear alterações


class PromptModuloResponse(PromptModuloBase):
    id: int
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
    versao: int
    condicao_ativacao: Optional[str]
    conteudo: str
    palavras_chave: Optional[List[str]]
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
    busca: Optional[str] = None,
    apenas_ativos: bool = True,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todos os módulos de prompts com filtros"""
    query = db.query(PromptModulo)
    
    if apenas_ativos:
        query = query.filter(PromptModulo.ativo == True)
    
    if tipo:
        query = query.filter(PromptModulo.tipo == tipo)
    
    if categoria:
        query = query.filter(PromptModulo.categoria == categoria)
    
    if busca:
        busca_like = f"%{busca}%"
        query = query.filter(
            (PromptModulo.titulo.ilike(busca_like)) |
            (PromptModulo.nome.ilike(busca_like)) |
            (PromptModulo.conteudo.ilike(busca_like))
        )
    
    modulos = query.order_by(PromptModulo.tipo, PromptModulo.categoria, PromptModulo.ordem).all()
    return modulos


@router.get("/categorias")
async def listar_categorias(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Lista todas as categorias disponíveis"""
    categorias = db.query(PromptModulo.categoria).distinct().filter(
        PromptModulo.categoria.isnot(None)
    ).all()
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
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todos os tipos de peça disponíveis (módulos tipo='peca').
    """
    modulos_peca = db.query(PromptModulo).filter(
        PromptModulo.tipo == "peca",
        PromptModulo.ativo == True
    ).order_by(PromptModulo.ordem).all()
    
    return [
        {
            "categoria": m.categoria,
            "titulo": m.titulo,
            "nome": m.nome
        }
        for m in modulos_peca
    ]


@router.get("/resumo-configuracao-tipos-peca")
async def resumo_configuracao_tipos_peca(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Retorna um resumo da configuração de módulos por tipo de peça.
    Mostra quantos módulos estão ativos para cada tipo.
    """
    # Busca tipos de peça
    tipos_peca = db.query(PromptModulo).filter(
        PromptModulo.tipo == "peca",
        PromptModulo.ativo == True
    ).all()
    
    # Conta total de módulos de conteúdo
    total_modulos = db.query(PromptModulo).filter(
        PromptModulo.tipo == "conteudo",
        PromptModulo.ativo == True
    ).count()
    
    resultado = []
    for tipo in tipos_peca:
        # Conta associações ativas
        ativos = db.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.tipo_peca == tipo.categoria,
            ModuloTipoPeca.ativo == True
        ).count()
        
        # Conta associações inativas
        inativos = db.query(ModuloTipoPeca).filter(
            ModuloTipoPeca.tipo_peca == tipo.categoria,
            ModuloTipoPeca.ativo == False
        ).count()
        
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
    
    return modulo


@router.post("", response_model=PromptModuloResponse, status_code=status.HTTP_201_CREATED)
async def criar_modulo(
    modulo_data: PromptModuloCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Cria um novo módulo de prompt"""
    verificar_permissao_prompts(current_user, "criar")
    
    # Verifica se já existe com mesmo nome
    existente = db.query(PromptModulo).filter(
        PromptModulo.tipo == modulo_data.tipo,
        PromptModulo.categoria == modulo_data.categoria,
        PromptModulo.subcategoria == modulo_data.subcategoria,
        PromptModulo.nome == modulo_data.nome
    ).first()
    
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe um módulo com esta combinação tipo/categoria/subcategoria/nome"
        )
    
    # Para tipo "peca" e "base": se ativo, desativa outros da mesma categoria
    if modulo_data.ativo and modulo_data.tipo in ("peca", "base"):
        outros_ativos = db.query(PromptModulo).filter(
            PromptModulo.tipo == modulo_data.tipo,
            PromptModulo.categoria == modulo_data.categoria,
            PromptModulo.ativo == True
        ).all()
        
        for outro in outros_ativos:
            outro.ativo = False
            outro.atualizado_por = current_user.id
    
    modulo = PromptModulo(
        **modulo_data.model_dump(),
        versao=1,
        criado_por=current_user.id,
        atualizado_por=current_user.id
    )
    
    db.add(modulo)
    db.commit()
    db.refresh(modulo)
    
    return modulo


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
    
    # Para tipo "peca" e "base": se está ativando, desativa outros da mesma categoria
    if modulo_data.ativo == True and modulo.tipo in ("peca", "base"):
        outros_ativos = db.query(PromptModulo).filter(
            PromptModulo.tipo == modulo.tipo,
            PromptModulo.categoria == modulo.categoria,
            PromptModulo.ativo == True,
            PromptModulo.id != modulo_id
        ).all()
        
        for outro in outros_ativos:
            outro.ativo = False
            outro.atualizado_por = current_user.id
    
    # Salva versão atual no histórico
    diff_resumo = ""
    if modulo_data.conteudo and modulo_data.conteudo != modulo.conteudo:
        diff_resumo = gerar_diff_resumo(modulo.conteudo, modulo_data.conteudo)
    
    historico = PromptModuloHistorico(
        modulo_id=modulo.id,
        versao=modulo.versao,
        condicao_ativacao=modulo.condicao_ativacao,
        conteudo=modulo.conteudo,
        palavras_chave=modulo.palavras_chave,
        tags=modulo.tags,
        alterado_por=current_user.id,
        motivo=modulo_data.motivo,
        diff_resumo=diff_resumo
    )
    db.add(historico)
    
    # Atualiza módulo
    update_data = modulo_data.model_dump(exclude_unset=True, exclude={"motivo"})
    for field, value in update_data.items():
        setattr(modulo, field, value)
    
    modulo.versao += 1
    modulo.atualizado_por = current_user.id
    modulo.atualizado_em = datetime.utcnow()
    
    db.commit()
    db.refresh(modulo)
    
    return modulo


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
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Exporta todos os módulos em formato JSON"""
    modulos = db.query(PromptModulo).filter(PromptModulo.ativo == True).all()
    
    export_data = {
        "versao": "1.0",
        "exportado_em": datetime.utcnow().isoformat(),
        "exportado_por": current_user.username,
        "modulos": []
    }
    
    for modulo in modulos:
        export_data["modulos"].append({
            "tipo": modulo.tipo,
            "categoria": modulo.categoria,
            "subcategoria": modulo.subcategoria,
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
    erros: List[str]


@router.post("/importar", response_model=ImportarModulosResponse)
async def importar_modulos(
    dados: ImportarModulosRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Importa módulos de prompts a partir de arquivo JSON.
    
    Formato esperado do JSON:
    {
        "modulos": [
            {
                "tipo": "Conteúdo",  # ou "conteudo"
                "categoria": "Preliminar",
                "subcategoria": "Competência",
                "nome_unico": "prel_jef_estadual",  # ou "nome"
                "titulo": "Competência do Juizado...",
                "condicao_ativacao": "Quando o juízo for...",
                "conteudo_prompt": "## COMPETÊNCIA...",  # ou "conteudo"
                "palavras_chave": [],
                "tags": []
            }
        ]
    }
    """
    verificar_permissao_prompts(current_user, "criar")
    
    criados = 0
    atualizados = 0
    ignorados = 0
    erros = []
    
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
            
            # Verifica se já existe
            existente = db.query(PromptModulo).filter(
                PromptModulo.tipo == tipo,
                PromptModulo.categoria == categoria,
                PromptModulo.subcategoria == subcategoria,
                PromptModulo.nome == nome
            ).first()
            
            if existente:
                if dados.sobrescrever_existentes:
                    # Salva versão atual no histórico
                    diff_resumo = gerar_diff_resumo(existente.conteudo, conteudo)
                    historico = PromptModuloHistorico(
                        modulo_id=existente.id,
                        versao=existente.versao,
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
                    existente.versao += 1
                    existente.atualizado_por = current_user.id
                    existente.atualizado_em = datetime.utcnow()
                    existente.ativo = True
                    
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
                    ativo=True,
                    versao=1,
                    criado_por=current_user.id,
                    atualizado_por=current_user.id
                )
                db.add(novo_modulo)
                criados += 1
        
        except Exception as e:
            erros.append(f"Módulo {i+1}: {str(e)}")
    
    db.commit()
    
    return ImportarModulosResponse(
        total_recebidos=len(dados.modulos),
        criados=criados,
        atualizados=atualizados,
        ignorados=ignorados,
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
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Lista todos os módulos de conteúdo com status de ativação para um tipo de peça específico.
    """
    # Busca todos os módulos de conteúdo ativos
    modulos_conteudo = db.query(PromptModulo).filter(
        PromptModulo.tipo == "conteudo",
        PromptModulo.ativo == True
    ).order_by(PromptModulo.categoria, PromptModulo.ordem).all()
    
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

