# sistemas/gerador_pecas/services_embeddings.py
"""
Serviço para geração e gerenciamento de embeddings vetoriais.

Usa a API do Google text-embedding-004 para gerar embeddings
dos módulos de conteúdo jurídico.
"""

import os
import hashlib
import logging
import asyncio
import httpx
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text

from dotenv import load_dotenv
load_dotenv()

from admin.models_prompts import PromptModulo
from sistemas.gerador_pecas.models_embeddings import (
    ModuloEmbedding,
    EMBEDDING_DIMENSION,
    PGVECTOR_AVAILABLE
)

logger = logging.getLogger(__name__)

# Configuração da API (aceita vários nomes de variável)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY")
EMBEDDING_MODEL = "text-embedding-004"
EMBEDDING_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent"

# Limites
MAX_TEXT_LENGTH = 2048  # Limite recomendado para embeddings
BATCH_SIZE = 100  # Processar em lotes para não sobrecarregar


async def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Gera embedding para um texto usando a API do Google.

    Args:
        text: Texto para gerar embedding (máx 2048 chars recomendado)

    Returns:
        Lista de floats representando o embedding (768 dimensões)
        None se houver erro
    """
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY não configurada")
        return None

    # Trunca texto se necessário
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]

    payload = {
        "model": f"models/{EMBEDDING_MODEL}",
        "content": {
            "parts": [{"text": text}]
        },
        "taskType": "RETRIEVAL_DOCUMENT"  # Otimizado para busca
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                EMBEDDING_API_URL,
                params={"key": GOOGLE_API_KEY},
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                logger.error(f"Erro API embedding: {response.status_code} - {response.text}")
                return None

            data = response.json()
            embedding = data.get("embedding", {}).get("values", [])

            if len(embedding) != EMBEDDING_DIMENSION:
                logger.warning(f"Dimensão inesperada: {len(embedding)} (esperado {EMBEDDING_DIMENSION})")

            return embedding

    except Exception as e:
        logger.error(f"Erro ao gerar embedding: {e}")
        return None


async def generate_embedding_for_query(query: str) -> Optional[List[float]]:
    """
    Gera embedding para uma query de busca.

    Usa taskType diferente para otimizar a busca.
    """
    if not GOOGLE_API_KEY:
        logger.error("GOOGLE_API_KEY não configurada")
        return None

    payload = {
        "model": f"models/{EMBEDDING_MODEL}",
        "content": {
            "parts": [{"text": query}]
        },
        "taskType": "RETRIEVAL_QUERY"  # Otimizado para queries
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                EMBEDDING_API_URL,
                params={"key": GOOGLE_API_KEY},
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code != 200:
                logger.error(f"Erro API embedding query: {response.status_code} - {response.text}")
                return None

            data = response.json()
            return data.get("embedding", {}).get("values", [])

    except Exception as e:
        logger.error(f"Erro ao gerar embedding query: {e}")
        return None


def build_embedding_text(modulo: PromptModulo) -> str:
    """
    Constrói o texto a ser usado para gerar o embedding do módulo.

    Formato otimizado para busca semântica:
    - Título (peso maior)
    - Categoria e subcategoria
    - Condição de ativação / regra determinística
    - Conteúdo (truncado)
    """
    parts = []

    # Título (importante para identificação)
    if modulo.titulo:
        parts.append(f"TÍTULO: {modulo.titulo}")

    # Categorização
    categoria = modulo.categoria or "Geral"
    subcategoria = modulo.subcategoria or "Geral"
    parts.append(f"CATEGORIA: {categoria} > {subcategoria}")

    # Condição de uso (crucial para entender QUANDO usar)
    condicao = modulo.regra_texto_original or modulo.condicao_ativacao
    if condicao:
        parts.append(f"QUANDO USAR: {condicao}")

    # Regra secundária (fallback)
    if modulo.regra_secundaria_texto_original:
        parts.append(f"ALTERNATIVAMENTE: {modulo.regra_secundaria_texto_original}")

    # Conteúdo (truncado para caber no limite)
    if modulo.conteudo:
        conteudo_limite = MAX_TEXT_LENGTH - len("\n".join(parts)) - 50
        if conteudo_limite > 200:
            conteudo = modulo.conteudo[:conteudo_limite]
            if len(modulo.conteudo) > conteudo_limite:
                conteudo += "..."
            parts.append(f"CONTEÚDO: {conteudo}")

    return "\n".join(parts)


def compute_text_hash(text: str) -> str:
    """Calcula hash SHA256 do texto para detectar mudanças."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


async def create_or_update_embedding(
    db: Session,
    modulo: PromptModulo,
    force: bool = False
) -> Optional[ModuloEmbedding]:
    """
    Cria ou atualiza o embedding de um módulo.

    Args:
        db: Sessão do banco
        modulo: Módulo de conteúdo
        force: Se True, recria mesmo sem mudanças

    Returns:
        ModuloEmbedding criado/atualizado ou None se erro
    """
    # Gera texto para embedding
    texto = build_embedding_text(modulo)
    texto_hash = compute_text_hash(texto)

    # Verifica se já existe
    existing = db.query(ModuloEmbedding).filter(
        ModuloEmbedding.modulo_id == modulo.id
    ).first()

    # Se existe e não mudou, pula
    if existing and not force:
        if existing.texto_hash == texto_hash:
            logger.debug(f"Embedding já atualizado para módulo {modulo.id}")
            return existing

    # Gera novo embedding
    logger.info(f"Gerando embedding para módulo {modulo.id}: {modulo.titulo[:50]}...")
    embedding = await generate_embedding(texto)

    if not embedding:
        logger.error(f"Falha ao gerar embedding para módulo {modulo.id}")
        return None

    if existing:
        # Atualiza existente
        existing.texto_embedding = texto
        existing.texto_hash = texto_hash
        existing.embedding_json = embedding
        existing.modelo_embedding = EMBEDDING_MODEL
        existing.dimensao = len(embedding)

        # Atualiza coluna vetorial se pgvector disponível
        if PGVECTOR_AVAILABLE:
            try:
                embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
                db.execute(text("""
                    UPDATE modulo_embeddings
                    SET embedding_vector = :vec::vector
                    WHERE id = :id
                """), {"vec": embedding_str, "id": existing.id})
            except Exception as e:
                logger.warning(f"Erro ao atualizar embedding_vector: {e}")

        db.commit()
        logger.info(f"✓ Embedding atualizado para módulo {modulo.id}")
        return existing
    else:
        # Cria novo
        new_embedding = ModuloEmbedding(
            modulo_id=modulo.id,
            texto_embedding=texto,
            texto_hash=texto_hash,
            embedding_json=embedding,
            modelo_embedding=EMBEDDING_MODEL,
            dimensao=len(embedding)
        )
        db.add(new_embedding)
        db.commit()
        db.refresh(new_embedding)

        # Adiciona coluna vetorial se pgvector disponível
        if PGVECTOR_AVAILABLE:
            try:
                embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
                db.execute(text("""
                    UPDATE modulo_embeddings
                    SET embedding_vector = :vec::vector
                    WHERE id = :id
                """), {"vec": embedding_str, "id": new_embedding.id})
                db.commit()
            except Exception as e:
                logger.warning(f"Erro ao adicionar embedding_vector: {e}")

        logger.info(f"✓ Embedding criado para módulo {modulo.id}")
        return new_embedding


async def sync_all_embeddings(
    db: Session,
    force: bool = False,
    limit: Optional[int] = None
) -> Dict[str, int]:
    """
    Sincroniza embeddings de todos os módulos de conteúdo.

    Args:
        db: Sessão do banco
        force: Se True, recria todos os embeddings
        limit: Limita quantidade (para testes)

    Returns:
        Estatísticas: {'created': N, 'updated': N, 'skipped': N, 'failed': N}
    """
    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0}

    # Busca todos os módulos de conteúdo ativos
    query = db.query(PromptModulo).filter(
        PromptModulo.tipo == 'conteudo',
        PromptModulo.ativo == True
    ).order_by(PromptModulo.ordem)

    if limit:
        query = query.limit(limit)

    modulos = query.all()
    logger.info(f"Sincronizando embeddings para {len(modulos)} módulos...")

    for i, modulo in enumerate(modulos):
        try:
            # Verifica se precisa atualizar
            texto = build_embedding_text(modulo)
            texto_hash = compute_text_hash(texto)

            existing = db.query(ModuloEmbedding).filter(
                ModuloEmbedding.modulo_id == modulo.id
            ).first()

            if existing and not force and existing.texto_hash == texto_hash:
                stats['skipped'] += 1
                continue

            # Cria/atualiza embedding
            result = await create_or_update_embedding(db, modulo, force)

            if result:
                if existing:
                    stats['updated'] += 1
                else:
                    stats['created'] += 1
            else:
                stats['failed'] += 1

            # Log de progresso a cada 10
            if (i + 1) % 10 == 0:
                logger.info(f"Progresso: {i + 1}/{len(modulos)}")

            # Pequena pausa para não sobrecarregar API
            await asyncio.sleep(0.1)

        except Exception as e:
            logger.error(f"Erro no módulo {modulo.id}: {e}")
            stats['failed'] += 1

    logger.info(f"Sincronização concluída: {stats}")
    return stats


def get_embedding_stats(db: Session) -> Dict[str, Any]:
    """Retorna estatísticas dos embeddings."""
    total_modulos = db.query(PromptModulo).filter(
        PromptModulo.tipo == 'conteudo',
        PromptModulo.ativo == True
    ).count()

    total_embeddings = db.query(ModuloEmbedding).filter(
        ModuloEmbedding.ativo == True
    ).count()

    # Verifica se há embeddings desatualizados
    # (isso requer comparar hashes, então simplificamos)

    return {
        'total_modulos': total_modulos,
        'total_embeddings': total_embeddings,
        'cobertura': round(total_embeddings / total_modulos * 100, 1) if total_modulos > 0 else 0,
        'pgvector_disponivel': PGVECTOR_AVAILABLE,
        'modelo': EMBEDDING_MODEL,
        'dimensao': EMBEDDING_DIMENSION
    }


def atualizar_embedding_modulo_sync(modulo_id: int) -> bool:
    """
    Atualiza o embedding de um módulo específico (versão síncrona).

    Chamado automaticamente quando um módulo de conteúdo é alterado.
    Usa uma nova sessão do banco para evitar conflitos.

    Args:
        modulo_id: ID do módulo a atualizar

    Returns:
        True se atualizado com sucesso, False caso contrário
    """
    from database.connection import SessionLocal

    try:
        db = SessionLocal()
        try:
            modulo = db.query(PromptModulo).filter(
                PromptModulo.id == modulo_id,
                PromptModulo.tipo == 'conteudo',
                PromptModulo.ativo == True
            ).first()

            if not modulo:
                logger.debug(f"Modulo {modulo_id} nao e de conteudo ou nao esta ativo")
                return False

            # Gera texto e verifica se mudou
            texto = build_embedding_text(modulo)
            texto_hash = compute_text_hash(texto)

            existing = db.query(ModuloEmbedding).filter(
                ModuloEmbedding.modulo_id == modulo_id
            ).first()

            if existing and existing.texto_hash == texto_hash:
                logger.debug(f"Embedding do modulo {modulo_id} ja esta atualizado")
                return True

            # Gera novo embedding de forma síncrona
            import asyncio

            # Cria event loop se não existir
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            embedding = loop.run_until_complete(generate_embedding(texto))

            if not embedding:
                logger.error(f"Falha ao gerar embedding para modulo {modulo_id}")
                return False

            if existing:
                existing.texto_embedding = texto
                existing.texto_hash = texto_hash
                existing.embedding_json = embedding
                existing.modelo_embedding = EMBEDDING_MODEL
                existing.dimensao = len(embedding)
                logger.info(f"[EMBEDDING] Atualizado embedding do modulo {modulo_id}")
            else:
                new_embedding = ModuloEmbedding(
                    modulo_id=modulo_id,
                    texto_embedding=texto,
                    texto_hash=texto_hash,
                    embedding_json=embedding,
                    modelo_embedding=EMBEDDING_MODEL,
                    dimensao=len(embedding)
                )
                db.add(new_embedding)
                logger.info(f"[EMBEDDING] Criado embedding do modulo {modulo_id}")

            db.commit()
            return True

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Erro ao atualizar embedding do modulo {modulo_id}: {e}")
        return False


def deletar_embedding_modulo(db: Session, modulo_id: int) -> bool:
    """
    Remove o embedding de um módulo (quando desativado ou excluído).

    Args:
        db: Sessão do banco
        modulo_id: ID do módulo

    Returns:
        True se removido, False se não existia
    """
    try:
        existing = db.query(ModuloEmbedding).filter(
            ModuloEmbedding.modulo_id == modulo_id
        ).first()

        if existing:
            db.delete(existing)
            db.commit()
            logger.info(f"[EMBEDDING] Removido embedding do modulo {modulo_id}")
            return True
        return False
    except Exception as e:
        logger.error(f"Erro ao remover embedding do modulo {modulo_id}: {e}")
        return False
