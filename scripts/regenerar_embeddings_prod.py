# scripts/regenerar_embeddings_prod.py
"""
Script para regenerar todos os embeddings em produção usando gemini-embedding-001.
"""
import asyncio
import os
import sys
import hashlib
import httpx

# Configura URL de produção
PROD_DATABASE_URL = 'postgresql://postgres:dfDpTUMqyxdZAHAPMOEAhaRBkCVxuJws@yamanote.proxy.rlwy.net:48085/railway'

# API Key do Gemini
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY")
EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent"
EMBEDDING_DIMENSION = 768
MAX_TEXT_LENGTH = 2048


async def generate_embedding(text: str) -> list:
    """Gera embedding usando gemini-embedding-001."""
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]

    payload = {
        "model": f"models/{EMBEDDING_MODEL}",
        "content": {"parts": [{"text": text}]},
        "taskType": "RETRIEVAL_DOCUMENT",
        "outputDimensionality": EMBEDDING_DIMENSION
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            EMBEDDING_API_URL,
            params={"key": GOOGLE_API_KEY},
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code != 200:
            print(f"  ERRO API: {response.status_code} - {response.text[:200]}")
            return None

        data = response.json()
        return data.get("embedding", {}).get("values", [])


def build_embedding_text(row) -> str:
    """Constrói texto para embedding a partir de uma row do banco."""
    parts = []

    if row['titulo']:
        parts.append(f"TÍTULO: {row['titulo']}")

    categoria = row['categoria'] or "Geral"
    subcategoria = row['subcategoria'] or "Geral"
    parts.append(f"CATEGORIA: {categoria} > {subcategoria}")

    condicao = row['regra_texto_original'] or row['condicao_ativacao']
    if condicao:
        parts.append(f"QUANDO USAR: {condicao}")

    if row['regra_secundaria_texto_original']:
        parts.append(f"ALTERNATIVAMENTE: {row['regra_secundaria_texto_original']}")

    if row['conteudo']:
        conteudo_limite = MAX_TEXT_LENGTH - len("\n".join(parts)) - 50
        if conteudo_limite > 200:
            conteudo = row['conteudo'][:conteudo_limite]
            if len(row['conteudo']) > conteudo_limite:
                conteudo += "..."
            parts.append(f"CONTEÚDO: {conteudo}")

    return "\n".join(parts)


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


async def main():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    import json

    print(f"Modelo: {EMBEDDING_MODEL}")
    print(f"Dimensão: {EMBEDDING_DIMENSION}")
    print(f"API Key: {'OK' if GOOGLE_API_KEY else 'FALTANDO!'}")

    if not GOOGLE_API_KEY:
        print("ERRO: GOOGLE_API_KEY não configurada")
        return

    print(f"\nConectando ao banco de produção...")
    conn = psycopg2.connect(PROD_DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Busca módulos de conteúdo ativos
    cur.execute("""
        SELECT id, nome, titulo, categoria, subcategoria,
               condicao_ativacao, regra_texto_original,
               regra_secundaria_texto_original, conteudo
        FROM prompt_modulos
        WHERE tipo = 'conteudo' AND ativo = true
        ORDER BY ordem
    """)
    modulos = cur.fetchall()
    print(f"Total de módulos de conteúdo: {len(modulos)}")

    stats = {'updated': 0, 'created': 0, 'failed': 0}

    for i, modulo in enumerate(modulos):
        try:
            # Gera texto e hash
            texto = build_embedding_text(modulo)
            texto_hash = compute_hash(texto)

            # Gera embedding
            print(f"[{i+1}/{len(modulos)}] {modulo['titulo'][:50]}...", end=" ")
            embedding = await generate_embedding(texto)

            if not embedding:
                print("FALHOU")
                stats['failed'] += 1
                continue

            embedding_json = json.dumps(embedding)

            # Verifica se já existe
            cur.execute(
                "SELECT id FROM modulo_embeddings WHERE modulo_id = %s",
                (modulo['id'],)
            )
            existing = cur.fetchone()

            if existing:
                # Atualiza
                cur.execute("""
                    UPDATE modulo_embeddings
                    SET texto_embedding = %s,
                        texto_hash = %s,
                        embedding_json = %s,
                        modelo_embedding = %s,
                        dimensao = %s,
                        atualizado_em = NOW()
                    WHERE modulo_id = %s
                """, (texto, texto_hash, embedding_json, EMBEDDING_MODEL,
                      len(embedding), modulo['id']))
                stats['updated'] += 1
                print("ATUALIZADO")
            else:
                # Cria
                cur.execute("""
                    INSERT INTO modulo_embeddings
                    (modulo_id, texto_embedding, texto_hash, embedding_json,
                     modelo_embedding, dimensao, ativo, criado_em, atualizado_em)
                    VALUES (%s, %s, %s, %s, %s, %s, true, NOW(), NOW())
                """, (modulo['id'], texto, texto_hash, embedding_json,
                      EMBEDDING_MODEL, len(embedding)))
                stats['created'] += 1
                print("CRIADO")

            conn.commit()

            # Pequena pausa para não sobrecarregar API
            await asyncio.sleep(0.1)

        except Exception as e:
            print(f"ERRO: {e}")
            stats['failed'] += 1
            conn.rollback()

    cur.close()
    conn.close()

    print(f"\n{'='*50}")
    print(f"CONCLUÍDO!")
    print(f"  Atualizados: {stats['updated']}")
    print(f"  Criados: {stats['created']}")
    print(f"  Falhas: {stats['failed']}")


if __name__ == "__main__":
    # Carrega .env
    from dotenv import load_dotenv
    load_dotenv()

    asyncio.run(main())
