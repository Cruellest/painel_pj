# sistemas/gerador_pecas/versoes.py
"""
Utilitários para gerenciamento de versões de peças jurídicas.
Inclui cálculo de diff e criação de versões.
"""

import difflib
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from sistemas.gerador_pecas.models import GeracaoPeca, VersaoPeca
from utils.timezone import to_iso_utc


def calcular_diff(texto_antigo: str, texto_novo: str) -> Dict:
    """
    Calcula as diferenças entre duas versões de texto.

    Retorna um dicionário com:
    - linhas_adicionadas: lista de linhas adicionadas
    - linhas_removidas: lista de linhas removidas
    - total_alteracoes: número total de alterações
    - diff_unificado: diff em formato unificado (para visualização)
    - resumo: resumo textual das alterações
    """
    if not texto_antigo:
        texto_antigo = ""
    if not texto_novo:
        texto_novo = ""

    linhas_antigas = texto_antigo.splitlines(keepends=True)
    linhas_novas = texto_novo.splitlines(keepends=True)

    # Gera diff unificado
    diff_unificado = list(difflib.unified_diff(
        linhas_antigas,
        linhas_novas,
        fromfile='versao_anterior',
        tofile='versao_atual',
        lineterm=''
    ))

    # Conta alterações
    linhas_adicionadas = []
    linhas_removidas = []

    for linha in diff_unificado:
        if linha.startswith('+') and not linha.startswith('+++'):
            linhas_adicionadas.append(linha[1:].strip())
        elif linha.startswith('-') and not linha.startswith('---'):
            linhas_removidas.append(linha[1:].strip())

    # Calcula estatísticas
    total_adicionadas = len(linhas_adicionadas)
    total_removidas = len(linhas_removidas)
    total_alteracoes = total_adicionadas + total_removidas

    # Gera resumo
    partes_resumo = []
    if total_adicionadas > 0:
        partes_resumo.append(f"+{total_adicionadas} linha(s)")
    if total_removidas > 0:
        partes_resumo.append(f"-{total_removidas} linha(s)")

    resumo = ", ".join(partes_resumo) if partes_resumo else "Sem alterações"

    return {
        "linhas_adicionadas": linhas_adicionadas[:50],  # Limita para não sobrecarregar
        "linhas_removidas": linhas_removidas[:50],
        "total_adicionadas": total_adicionadas,
        "total_removidas": total_removidas,
        "total_alteracoes": total_alteracoes,
        "diff_unificado": "\n".join(diff_unificado[:200]),  # Limita tamanho
        "resumo": resumo
    }


def criar_versao_inicial(
    db: Session,
    geracao_id: int,
    conteudo: str
) -> VersaoPeca:
    """
    Cria a versão inicial (v1) de uma peça.
    Chamado após a geração inicial da peça.
    """
    versao = VersaoPeca(
        geracao_id=geracao_id,
        numero_versao=1,
        conteudo=conteudo,
        origem='geracao_inicial',
        descricao_alteracao='Versão inicial gerada pela IA',
        diff_anterior=None  # Primeira versão não tem diff
    )
    db.add(versao)
    db.commit()
    db.refresh(versao)
    return versao


def criar_nova_versao(
    db: Session,
    geracao_id: int,
    conteudo_novo: str,
    descricao: str = None,
    origem: str = 'edicao_chat'
) -> Tuple[VersaoPeca, Dict]:
    """
    Cria uma nova versão da peça, calculando o diff em relação à anterior.

    Args:
        db: Sessão do banco de dados
        geracao_id: ID da geração
        conteudo_novo: Novo conteúdo do texto
        descricao: Descrição da alteração (mensagem do usuário no chat)
        origem: 'edicao_chat' ou 'edicao_manual'

    Returns:
        Tupla com (nova_versao, diff_calculado)
    """
    # Busca a última versão existente
    ultima_versao = db.query(VersaoPeca).filter(
        VersaoPeca.geracao_id == geracao_id
    ).order_by(VersaoPeca.numero_versao.desc()).first()

    if ultima_versao:
        numero_nova = ultima_versao.numero_versao + 1
        conteudo_anterior = ultima_versao.conteudo
    else:
        # Se não existe versão, criar como v1
        numero_nova = 1
        conteudo_anterior = ""

    # Calcula diff
    diff = calcular_diff(conteudo_anterior, conteudo_novo)

    # Só cria nova versão se houve alterações reais
    if diff["total_alteracoes"] == 0:
        return None, diff

    # Cria a nova versão
    nova_versao = VersaoPeca(
        geracao_id=geracao_id,
        numero_versao=numero_nova,
        conteudo=conteudo_novo,
        origem=origem,
        descricao_alteracao=descricao,
        diff_anterior=diff
    )
    db.add(nova_versao)
    db.commit()
    db.refresh(nova_versao)

    return nova_versao, diff


def obter_versoes(db: Session, geracao_id: int) -> List[Dict]:
    """
    Obtém lista de todas as versões de uma peça.
    Retorna lista ordenada da mais recente para a mais antiga.
    """
    versoes = db.query(VersaoPeca).filter(
        VersaoPeca.geracao_id == geracao_id
    ).order_by(VersaoPeca.numero_versao.desc()).all()

    return [
        {
            "id": v.id,
            "numero_versao": v.numero_versao,
            "origem": v.origem,
            "descricao_alteracao": v.descricao_alteracao,
            "criado_em": to_iso_utc(v.criado_em),
            "resumo_diff": v.diff_anterior.get("resumo") if v.diff_anterior else "Versão inicial"
        }
        for v in versoes
    ]


def obter_versao_detalhada(db: Session, versao_id: int) -> Optional[Dict]:
    """
    Obtém detalhes completos de uma versão específica, incluindo diff.
    """
    versao = db.query(VersaoPeca).filter(VersaoPeca.id == versao_id).first()

    if not versao:
        return None

    return {
        "id": versao.id,
        "geracao_id": versao.geracao_id,
        "numero_versao": versao.numero_versao,
        "conteudo": versao.conteudo,
        "origem": versao.origem,
        "descricao_alteracao": versao.descricao_alteracao,
        "diff_anterior": versao.diff_anterior,
        "criado_em": to_iso_utc(versao.criado_em)
    }


def comparar_versoes(db: Session, versao_id_1: int, versao_id_2: int) -> Optional[Dict]:
    """
    Compara duas versões específicas e retorna o diff entre elas.
    """
    versao1 = db.query(VersaoPeca).filter(VersaoPeca.id == versao_id_1).first()
    versao2 = db.query(VersaoPeca).filter(VersaoPeca.id == versao_id_2).first()

    if not versao1 or not versao2:
        return None

    # Garante que v1 é a mais antiga
    if versao1.numero_versao > versao2.numero_versao:
        versao1, versao2 = versao2, versao1

    diff = calcular_diff(versao1.conteudo, versao2.conteudo)

    return {
        "versao_antiga": {
            "id": versao1.id,
            "numero_versao": versao1.numero_versao,
            "criado_em": to_iso_utc(versao1.criado_em)
        },
        "versao_nova": {
            "id": versao2.id,
            "numero_versao": versao2.numero_versao,
            "criado_em": to_iso_utc(versao2.criado_em)
        },
        "diff": diff
    }


def restaurar_versao(db: Session, geracao_id: int, versao_id: int) -> Optional[VersaoPeca]:
    """
    Restaura uma versão anterior, criando uma nova versão com o conteúdo antigo.
    """
    versao_antiga = db.query(VersaoPeca).filter(
        VersaoPeca.id == versao_id,
        VersaoPeca.geracao_id == geracao_id
    ).first()

    if not versao_antiga:
        return None

    # Cria nova versão com o conteúdo restaurado
    nova_versao, _ = criar_nova_versao(
        db=db,
        geracao_id=geracao_id,
        conteudo_novo=versao_antiga.conteudo,
        descricao=f"Restaurado da versão {versao_antiga.numero_versao}",
        origem='edicao_manual'
    )

    # Atualiza o conteúdo na geração principal
    if nova_versao:
        geracao = db.query(GeracaoPeca).filter(GeracaoPeca.id == geracao_id).first()
        if geracao:
            geracao.conteudo_gerado = versao_antiga.conteudo
            db.commit()

    return nova_versao
