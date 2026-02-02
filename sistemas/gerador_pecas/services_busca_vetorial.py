# sistemas/gerador_pecas/services_busca_vetorial.py
"""
Serviço de busca semântica usando embeddings vetoriais.

Suporta:
- pgvector: Busca vetorial nativa do PostgreSQL (produção)
- Fallback numpy: Busca por similaridade de cosseno em Python (desenvolvimento)

A busca vetorial permite encontrar argumentos semanticamente similares
mesmo quando as palavras-chave não correspondem exatamente.
"""

import logging
import numpy as np
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from admin.models_prompts import PromptModulo
from sistemas.gerador_pecas.models_embeddings import (
    ModuloEmbedding,
    PGVECTOR_AVAILABLE,
    EMBEDDING_DIMENSION
)
from sistemas.gerador_pecas.services_embeddings import generate_embedding_for_query

logger = logging.getLogger(__name__)


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calcula similaridade de cosseno entre dois vetores.

    Retorna valor entre -1 e 1, onde 1 = idênticos.
    """
    a = np.array(vec1)
    b = np.array(vec2)

    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(dot_product / (norm_a * norm_b))


async def buscar_argumentos_vetorial(
    db: Session,
    query: str,
    tipo_peca: Optional[str] = None,
    limit: int = 5,
    threshold: float = 0.3
) -> List[Dict]:
    """
    Busca módulos de conteúdo usando similaridade vetorial.

    Args:
        db: Sessão do banco de dados
        query: Texto de busca do usuário
        tipo_peca: Tipo de peça atual (para contexto, não filtro)
        limit: Número máximo de resultados
        threshold: Similaridade mínima (0-1)

    Returns:
        Lista de módulos relevantes com score de similaridade
    """
    print(f"\n[BUSCA-VETORIAL] Query: '{query}'")
    print(f"[BUSCA-VETORIAL] Tipo de peca: {tipo_peca or 'nao especificado'}")
    print(f"[BUSCA-VETORIAL] pgvector disponivel: {PGVECTOR_AVAILABLE}")

    # Gera embedding da query
    print(f"[BUSCA-VETORIAL] Gerando embedding da query...")
    query_embedding = await generate_embedding_for_query(query)

    if not query_embedding:
        print(f"[BUSCA-VETORIAL] [ERRO] Falha ao gerar embedding da query")
        return []

    print(f"[BUSCA-VETORIAL] [OK] Embedding gerado ({len(query_embedding)} dimensoes)")

    # Busca usando pgvector ou fallback
    if PGVECTOR_AVAILABLE:
        resultados = _buscar_com_pgvector(db, query_embedding, limit, threshold)
    else:
        resultados = _buscar_com_numpy(db, query_embedding, limit, threshold)

    print(f"[BUSCA-VETORIAL] Resultados encontrados: {len(resultados)}")

    # Enriquece com dados do módulo
    resultados_enriquecidos = []
    for r in resultados:
        modulo = db.query(PromptModulo).filter(PromptModulo.id == r['modulo_id']).first()
        if modulo:
            resultado = {
                "id": modulo.id,
                "nome": modulo.nome,
                "titulo": modulo.titulo,
                "categoria": modulo.categoria,
                "subcategoria": modulo.subcategoria,
                "condicao_ativacao": modulo.condicao_ativacao,
                "regra_texto_original": modulo.regra_texto_original,
                "regra_secundaria": modulo.regra_secundaria_texto_original,
                "conteudo": modulo.conteudo,
                "score": r['score'],
                "similaridade": f"{r['score'] * 100:.1f}%",
                "metodo_busca": "vetorial_pgvector" if PGVECTOR_AVAILABLE else "vetorial_numpy"
            }
            resultados_enriquecidos.append(resultado)
            print(f"[BUSCA-VETORIAL]   [OK] [{r['score']:.3f}] {modulo.titulo[:50]}")

    return resultados_enriquecidos


def _buscar_com_pgvector(
    db: Session,
    query_embedding: List[float],
    limit: int,
    threshold: float
) -> List[Dict]:
    """Busca usando operador de distância do pgvector."""
    try:
        # Converte embedding para formato pgvector
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        # Busca usando operador de distância de cosseno (<=>)
        # Menor distância = maior similaridade
        # Similaridade = 1 - distância
        result = db.execute(text("""
            SELECT
                me.modulo_id,
                1 - (me.embedding_vector <=> :query_vec::vector) as similarity
            FROM modulo_embeddings me
            JOIN prompt_modulos pm ON pm.id = me.modulo_id
            WHERE me.ativo = true
              AND pm.ativo = true
              AND pm.tipo = 'conteudo'
              AND (1 - (me.embedding_vector <=> :query_vec::vector)) >= :threshold
            ORDER BY me.embedding_vector <=> :query_vec::vector
            LIMIT :limit
        """), {
            "query_vec": embedding_str,
            "threshold": threshold,
            "limit": limit
        })

        return [{"modulo_id": row[0], "score": float(row[1])} for row in result]

    except Exception as e:
        logger.error(f"Erro na busca pgvector: {e}")
        # Fallback para numpy se pgvector falhar
        return _buscar_com_numpy(db, query_embedding, limit, threshold)


def _buscar_com_numpy(
    db: Session,
    query_embedding: List[float],
    limit: int,
    threshold: float
) -> List[Dict]:
    """Busca usando numpy para calcular similaridade de cosseno."""
    print(f"[BUSCA-VETORIAL] Usando fallback numpy...")

    # Busca todos os embeddings ativos
    embeddings = db.query(ModuloEmbedding).join(
        PromptModulo, ModuloEmbedding.modulo_id == PromptModulo.id
    ).filter(
        ModuloEmbedding.ativo == True,
        PromptModulo.ativo == True,
        PromptModulo.tipo == 'conteudo'
    ).all()

    if not embeddings:
        logger.warning("Nenhum embedding encontrado no banco")
        return []

    print(f"[BUSCA-VETORIAL] Comparando com {len(embeddings)} embeddings...")

    # Calcula similaridade para cada embedding
    resultados = []
    for emb in embeddings:
        if not emb.embedding_json:
            continue

        similarity = cosine_similarity(query_embedding, emb.embedding_json)

        if similarity >= threshold:
            resultados.append({
                "modulo_id": emb.modulo_id,
                "score": similarity
            })

    # Ordena por similaridade decrescente
    resultados.sort(key=lambda x: x['score'], reverse=True)

    return resultados[:limit]


async def buscar_argumentos_hibrido(
    db: Session,
    query: str,
    tipo_peca: Optional[str] = None,
    limit: int = 5
) -> List[Dict]:
    """
    Busca híbrida combinando busca vetorial com busca por palavras-chave.

    Útil para capturar tanto correspondências semânticas quanto exatas.

    Args:
        db: Sessão do banco de dados
        query: Texto de busca do usuário
        tipo_peca: Tipo de peça atual
        limit: Número máximo de resultados

    Returns:
        Lista combinada e deduplicada de resultados
    """
    from sistemas.gerador_pecas.services_busca_argumentos import buscar_argumentos_relevantes

    print(f"\n[BUSCA-HIBRIDA] Query: '{query}'")

    # Executa ambas as buscas
    resultados_vetorial = await buscar_argumentos_vetorial(
        db, query, tipo_peca, limit=limit, threshold=0.35
    )

    resultados_keyword = buscar_argumentos_relevantes(
        db, query, tipo_peca, limit=limit
    )

    # Combina resultados, priorizando vetorial
    vistos = set()
    combinados = []

    # Primeiro, resultados vetoriais (maior peso semântico)
    for r in resultados_vetorial:
        if r['id'] not in vistos:
            r['fonte'] = 'vetorial'
            combinados.append(r)
            vistos.add(r['id'])

    # Depois, resultados por keyword (complementa)
    for r in resultados_keyword:
        if r['id'] not in vistos:
            r['fonte'] = 'keyword'
            r['similaridade'] = f"keyword match (score: {r.get('score', 0)})"
            combinados.append(r)
            vistos.add(r['id'])

    # Limita ao total desejado
    combinados = combinados[:limit]

    print(f"[BUSCA-HIBRIDA] Total combinado: {len(combinados)} (vetorial: {len(resultados_vetorial)}, keyword: {len(resultados_keyword)})")

    return combinados


def formatar_contexto_argumentos_vetorial(argumentos: List[Dict], max_chars: int = 8000) -> str:
    """
    Formata os argumentos encontrados como contexto para o prompt da IA.

    Versão otimizada para resultados de busca vetorial.
    """
    if not argumentos:
        return ""

    partes = [
        "### ARGUMENTOS ENCONTRADOS NA BASE DE CONHECIMENTO:",
        "",
        "Os seguintes argumentos jurídicos foram encontrados por **similaridade semântica** com seu pedido:",
        ""
    ]

    chars_usados = len("\n".join(partes))

    for i, arg in enumerate(argumentos, 1):
        similaridade = arg.get('similaridade', 'N/A')
        fonte = arg.get('fonte', arg.get('metodo_busca', 'vetorial'))

        bloco = f"""**{i}. {arg['titulo']}** ({similaridade})
- Categoria: {arg.get('categoria', 'N/A')} / {arg.get('subcategoria', 'N/A')}
- Condição de uso: {arg.get('condicao_ativacao') or arg.get('regra_texto_original') or 'Sem condição específica'}
- Fonte: {fonte}

Conteúdo:
{arg['conteudo'][:2000]}{'...' if len(arg['conteudo']) > 2000 else ''}

---
"""
        # Verifica se ainda cabe
        if chars_usados + len(bloco) > max_chars:
            partes.append(f"\n*({len(argumentos) - i + 1} argumentos adicionais omitidos por limite de contexto)*")
            break

        partes.append(bloco)
        chars_usados += len(bloco)

    partes.append("""
**INSTRUÇÕES PARA USO DOS ARGUMENTOS:**
1. Use o conteúdo acima como BASE, mas adapte ao caso concreto da minuta
2. Mantenha a estrutura e os fundamentos jurídicos apresentados
3. Se houver variáveis como {{ nome }} ou {{ valor }}, substitua pelos dados do caso
4. Integre o argumento de forma fluida na seção apropriada da minuta
5. Os argumentos com maior similaridade (%) são mais relevantes semanticamente
""")

    return "\n".join(partes)


def verificar_embeddings_disponiveis(db: Session) -> bool:
    """Verifica se há embeddings suficientes para busca vetorial."""
    try:
        count = db.query(ModuloEmbedding).filter(ModuloEmbedding.ativo == True).count()
        return count > 0
    except Exception:
        return False
