#!/usr/bin/env python
"""
Script para sincronizar embeddings dos modulos de conteudo.

Uso:
    python scripts/sync_embeddings.py           # Sincroniza apenas novos/alterados
    python scripts/sync_embeddings.py --force   # Recria todos os embeddings
    python scripts/sync_embeddings.py --stats   # Mostra estatisticas
    python scripts/sync_embeddings.py --test    # Testa busca com query exemplo

Autor: LAB/PGE-MS
"""

import os
import sys
import asyncio
import argparse

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from database.connection import get_db_context

# Importa todos os modelos para resolver relacionamentos do SQLAlchemy
from admin.models_prompts import PromptModulo
from admin.models_prompt_groups import PromptGroup
from auth.models import User

from sistemas.gerador_pecas.models_embeddings import init_embeddings_table, PGVECTOR_AVAILABLE
from sistemas.gerador_pecas.services_embeddings import sync_all_embeddings, get_embedding_stats
from sistemas.gerador_pecas.services_busca_vetorial import buscar_argumentos_vetorial, buscar_argumentos_hibrido


def print_banner():
    print("""
============================================================
       SINCRONIZACAO DE EMBEDDINGS - PORTAL PGE-MS
============================================================
""")


async def main():
    parser = argparse.ArgumentParser(description='Sincroniza embeddings dos modulos de conteudo')
    parser.add_argument('--force', action='store_true', help='Recria todos os embeddings')
    parser.add_argument('--stats', action='store_true', help='Mostra apenas estatisticas')
    parser.add_argument('--test', type=str, help='Testa busca com query exemplo')
    parser.add_argument('--limit', type=int, help='Limita quantidade de modulos (para testes)')
    parser.add_argument('--hibrido', action='store_true', help='Usa busca hibrida no teste')

    args = parser.parse_args()

    print_banner()

    # Inicializa tabela de embeddings
    print("[*] Inicializando tabela de embeddings...")
    pgvector_ok = init_embeddings_table()
    print(f"    pgvector disponivel: {'[OK] SIM' if pgvector_ok else '[!] NAO (usando fallback numpy)'}")
    print()

    with get_db_context() as db:
        if args.stats:
            # Mostra estatisticas
            print("[STATS] ESTATISTICAS DE EMBEDDINGS:")
            print("-" * 40)
            stats = get_embedding_stats(db)
            print(f"    Modulos de conteudo: {stats['total_modulos']}")
            print(f"    Embeddings criados:  {stats['total_embeddings']}")
            print(f"    Cobertura:           {stats['cobertura']}%")
            print(f"    pgvector:            {'Sim' if stats['pgvector_disponivel'] else 'Nao'}")
            print(f"    Modelo:              {stats['modelo']}")
            print(f"    Dimensao:            {stats['dimensao']}")
            return

        if args.test:
            # Testa busca
            print(f"[SEARCH] TESTANDO BUSCA: '{args.test}'")
            print("-" * 40)

            if args.hibrido:
                print("    Metodo: Hibrido (vetorial + keyword)")
                resultados = await buscar_argumentos_hibrido(db, args.test, limit=5)
            else:
                print("    Metodo: Vetorial puro")
                resultados = await buscar_argumentos_vetorial(db, args.test, limit=5)

            print()
            if not resultados:
                print("    [!] Nenhum resultado encontrado")
                print("    Dica: Execute primeiro sem --test para criar os embeddings")
            else:
                print(f"    [OK] {len(resultados)} resultados encontrados:")
                print()
                for i, r in enumerate(resultados, 1):
                    print(f"    {i}. [{r.get('similaridade', 'N/A')}] {r['titulo']}")
                    print(f"       Categoria: {r.get('categoria', 'N/A')} > {r.get('subcategoria', 'N/A')}")
                    if r.get('condicao_ativacao'):
                        cond = r['condicao_ativacao'][:100]
                        print(f"       Condicao: {cond}...")
                    print()
            return

        # Sincroniza embeddings
        print("[SYNC] SINCRONIZANDO EMBEDDINGS...")
        print("-" * 40)

        if args.force:
            print("    [!] Modo FORCE: Recriando todos os embeddings")
        if args.limit:
            print(f"    [!] Limitado a {args.limit} modulos")

        print()

        stats = await sync_all_embeddings(
            db,
            force=args.force,
            limit=args.limit
        )

        print()
        print("[RESULT] RESULTADO:")
        print("-" * 40)
        print(f"    [+] Criados:     {stats['created']}")
        print(f"    [+] Atualizados: {stats['updated']}")
        print(f"    [-] Ignorados:   {stats['skipped']} (sem mudancas)")
        print(f"    [X] Falhas:      {stats['failed']}")
        print()

        # Mostra estatisticas finais
        final_stats = get_embedding_stats(db)
        print(f"    Cobertura final: {final_stats['cobertura']}% ({final_stats['total_embeddings']}/{final_stats['total_modulos']} modulos)")


if __name__ == "__main__":
    asyncio.run(main())
