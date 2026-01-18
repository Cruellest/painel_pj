#!/usr/bin/env python3
"""
Script para corrigir prefixos de variáveis no banco de dados.

Este script:
1. Diagnostica variáveis sem prefixo correto
2. Identifica variáveis órfãs (sem pergunta associada)
3. Aplica correções com confirmação

Uso:
    python scripts/corrigir_prefixos_variaveis.py --diagnostico
    python scripts/corrigir_prefixos_variaveis.py --corrigir
"""

import os
import sys
import re
import argparse
from typing import List, Dict, Any, Optional, Tuple

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# URL do banco PostgreSQL (Railway)
DATABASE_URL = "postgresql://postgres:dfDpTUMqyxdZAHAPMOEAhaRBkCVxuJws@yamanote.proxy.rlwy.net:48085/railway"


def normalizar_nome_para_namespace(nome: str) -> str:
    """Normaliza um nome de categoria para usar como namespace."""
    nome_normalizado = nome.lower()
    nome_normalizado = re.sub(r'[^a-z0-9]+', '_', nome_normalizado)
    return nome_normalizado.strip('_')


def obter_namespace_categoria(categoria: Dict[str, Any]) -> str:
    """Obtém o namespace efetivo de uma categoria."""
    if categoria.get('namespace_prefix'):
        return categoria['namespace_prefix']
    return normalizar_nome_para_namespace(categoria.get('nome', ''))


def diagnosticar_banco(session) -> Dict[str, Any]:
    """
    Executa diagnóstico completo do banco de dados.

    Retorna:
        Dict com resultados do diagnóstico
    """
    print("\n" + "="*70)
    print("DIAGNÓSTICO DO BANCO DE DADOS")
    print("="*70)

    resultados = {
        "categorias": [],
        "variaveis_sem_prefixo": [],
        "variaveis_orfas": [],
        "perguntas_sem_variavel": [],
        "duplicatas": []
    }

    # 1. Lista todas as categorias com seus namespaces
    print("\n1. CATEGORIAS E NAMESPACES")
    print("-" * 50)

    categorias = session.execute(text("""
        SELECT id, nome, namespace_prefix, ativo
        FROM categorias_resumo_json
        ORDER BY nome
    """)).fetchall()

    for cat in categorias:
        cat_dict = {
            "id": cat[0],
            "nome": cat[1],
            "namespace_prefix": cat[2],
            "ativo": cat[3]
        }
        namespace = obter_namespace_categoria(cat_dict)
        cat_dict["namespace_efetivo"] = namespace
        resultados["categorias"].append(cat_dict)

        status = "ATIVO" if cat[3] else "INATIVO"
        print(f"  ID={cat[0]:3d} | {status:8s} | namespace='{namespace}' | nome='{cat[1]}'")

    # 2. Variáveis sem prefixo correto
    print("\n2. VARIÁVEIS SEM PREFIXO CORRETO")
    print("-" * 50)

    variaveis = session.execute(text("""
        SELECT
            v.id,
            v.slug,
            v.categoria_id,
            v.source_question_id,
            c.nome as categoria_nome,
            c.namespace_prefix
        FROM extraction_variables v
        LEFT JOIN categorias_resumo_json c ON v.categoria_id = c.id
        WHERE v.ativo = true
        ORDER BY c.nome, v.slug
    """)).fetchall()

    for var in variaveis:
        var_id, slug, cat_id, source_q_id, cat_nome, ns_prefix = var

        if cat_id is None:
            print(f"  [ÓRFÃ] ID={var_id}: '{slug}' - SEM CATEGORIA!")
            resultados["variaveis_orfas"].append({
                "id": var_id,
                "slug": slug,
                "motivo": "Sem categoria associada"
            })
            continue

        # Calcula namespace esperado
        namespace = ns_prefix if ns_prefix else normalizar_nome_para_namespace(cat_nome or '')
        prefixo_esperado = f"{namespace}_"

        # Verifica se tem o prefixo correto
        if not slug.startswith(prefixo_esperado):
            print(f"  [SEM PREFIXO] ID={var_id}: '{slug}' deveria começar com '{prefixo_esperado}'")
            resultados["variaveis_sem_prefixo"].append({
                "id": var_id,
                "slug": slug,
                "categoria_id": cat_id,
                "categoria_nome": cat_nome,
                "namespace": namespace,
                "prefixo_esperado": prefixo_esperado,
                "slug_corrigido": f"{prefixo_esperado}{slug}" if not slug.startswith(prefixo_esperado) else slug
            })

    if not resultados["variaveis_sem_prefixo"]:
        print("  Todas as variáveis têm prefixo correto.")

    # 3. Variáveis órfãs (sem pergunta associada)
    print("\n3. VARIÁVEIS ÓRFÃS (SEM PERGUNTA ASSOCIADA)")
    print("-" * 50)

    orfas = session.execute(text("""
        SELECT
            v.id,
            v.slug,
            v.categoria_id,
            c.nome as categoria_nome
        FROM extraction_variables v
        LEFT JOIN categorias_resumo_json c ON v.categoria_id = c.id
        WHERE v.ativo = true
          AND v.source_question_id IS NULL
        ORDER BY c.nome, v.slug
    """)).fetchall()

    for orfa in orfas:
        var_id, slug, cat_id, cat_nome = orfa
        print(f"  [ÓRFÃ] ID={var_id}: '{slug}' (categoria: {cat_nome or 'NENHUMA'})")
        if var_id not in [v["id"] for v in resultados["variaveis_orfas"]]:
            resultados["variaveis_orfas"].append({
                "id": var_id,
                "slug": slug,
                "categoria_id": cat_id,
                "categoria_nome": cat_nome,
                "motivo": "Sem pergunta associada"
            })

    if not orfas:
        print("  Nenhuma variável órfã encontrada.")

    # 4. Perguntas ativas sem variável correspondente
    print("\n4. PERGUNTAS ATIVAS SEM VARIÁVEL CORRESPONDENTE")
    print("-" * 50)

    perguntas_sem_var = session.execute(text("""
        SELECT
            p.id,
            p.nome_variavel_sugerido,
            p.categoria_id,
            c.nome as categoria_nome,
            LEFT(p.pergunta, 80) as pergunta_resumo
        FROM extraction_questions p
        LEFT JOIN categorias_resumo_json c ON p.categoria_id = c.id
        WHERE p.ativo = true
          AND p.nome_variavel_sugerido IS NOT NULL
          AND p.nome_variavel_sugerido != ''
          AND NOT EXISTS (
              SELECT 1 FROM extraction_variables v
              WHERE v.source_question_id = p.id
          )
        ORDER BY c.nome, p.id
    """)).fetchall()

    for p in perguntas_sem_var:
        p_id, slug, cat_id, cat_nome, pergunta = p
        print(f"  [SEM VAR] ID={p_id}: slug='{slug}' | {pergunta}...")
        resultados["perguntas_sem_variavel"].append({
            "id": p_id,
            "slug": slug,
            "categoria_id": cat_id,
            "categoria_nome": cat_nome,
            "pergunta": pergunta
        })

    if not perguntas_sem_var:
        print("  Todas as perguntas têm variável correspondente.")

    # 5. Verificar duplicatas de slug
    print("\n5. DUPLICATAS DE SLUG")
    print("-" * 50)

    duplicatas = session.execute(text("""
        SELECT slug, COUNT(*) as total
        FROM extraction_variables
        WHERE ativo = true
        GROUP BY slug
        HAVING COUNT(*) > 1
        ORDER BY total DESC, slug
    """)).fetchall()

    for dup in duplicatas:
        slug, total = dup
        print(f"  [DUPLICATA] '{slug}' aparece {total} vezes")
        resultados["duplicatas"].append({
            "slug": slug,
            "total": total
        })

    if not duplicatas:
        print("  Nenhuma duplicata encontrada.")

    # Resumo
    print("\n" + "="*70)
    print("RESUMO DO DIAGNÓSTICO")
    print("="*70)
    print(f"  Categorias: {len(resultados['categorias'])}")
    print(f"  Variáveis sem prefixo correto: {len(resultados['variaveis_sem_prefixo'])}")
    print(f"  Variáveis órfãs: {len(resultados['variaveis_orfas'])}")
    print(f"  Perguntas sem variável: {len(resultados['perguntas_sem_variavel'])}")
    print(f"  Duplicatas de slug: {len(resultados['duplicatas'])}")
    print("="*70)

    return resultados


def corrigir_prefixos(session, dry_run: bool = True) -> int:
    """
    Corrige os prefixos das variáveis.

    Args:
        session: Sessão do SQLAlchemy
        dry_run: Se True, apenas mostra o que seria feito

    Returns:
        Número de correções realizadas
    """
    print("\n" + "="*70)
    print("CORREÇÃO DE PREFIXOS" + (" (DRY RUN)" if dry_run else ""))
    print("="*70)

    # Busca variáveis que precisam de correção
    variaveis = session.execute(text("""
        SELECT
            v.id,
            v.slug,
            v.categoria_id,
            c.nome as categoria_nome,
            c.namespace_prefix
        FROM extraction_variables v
        LEFT JOIN categorias_resumo_json c ON v.categoria_id = c.id
        WHERE v.ativo = true
          AND v.categoria_id IS NOT NULL
        ORDER BY c.nome, v.slug
    """)).fetchall()

    correcoes = []

    for var in variaveis:
        var_id, slug, cat_id, cat_nome, ns_prefix = var

        # Calcula namespace esperado
        namespace = ns_prefix if ns_prefix else normalizar_nome_para_namespace(cat_nome or '')
        prefixo_esperado = f"{namespace}_"

        # Verifica se precisa de correção
        if not slug.startswith(prefixo_esperado):
            # Remove prefixo incorreto se houver (evita duplicação)
            slug_base = slug
            # Se já tem algum prefixo que termina em _, remove
            if '_' in slug:
                partes = slug.split('_')
                # Tenta identificar se é um namespace incorreto
                # Verifica se a primeira parte é um namespace de outra categoria
                possivel_namespace = partes[0]
                if len(partes) > 1 and len(possivel_namespace) > 2:
                    # Provavelmente é um namespace - remove
                    slug_base = '_'.join(partes[1:])

            slug_corrigido = f"{prefixo_esperado}{slug_base}"

            # Verifica se o slug corrigido já existe
            existe = session.execute(text("""
                SELECT id FROM extraction_variables
                WHERE slug = :slug AND id != :id
            """), {"slug": slug_corrigido, "id": var_id}).fetchone()

            if existe:
                print(f"  [CONFLITO] ID={var_id}: '{slug}' -> '{slug_corrigido}' JÁ EXISTE!")
                continue

            correcoes.append({
                "id": var_id,
                "slug_antigo": slug,
                "slug_novo": slug_corrigido,
                "categoria": cat_nome
            })

            if dry_run:
                print(f"  [DRY RUN] ID={var_id}: '{slug}' -> '{slug_corrigido}'")
            else:
                # Atualiza a variável
                session.execute(text("""
                    UPDATE extraction_variables
                    SET slug = :novo_slug
                    WHERE id = :id
                """), {"novo_slug": slug_corrigido, "id": var_id})

                # Atualiza a pergunta correspondente se existir
                session.execute(text("""
                    UPDATE extraction_questions
                    SET nome_variavel_sugerido = :novo_slug
                    WHERE id = (
                        SELECT source_question_id
                        FROM extraction_variables
                        WHERE id = :var_id
                    )
                """), {"novo_slug": slug_corrigido, "var_id": var_id})

                print(f"  [OK] ID={var_id}: '{slug}' -> '{slug_corrigido}'")

    if not dry_run and correcoes:
        session.commit()
        print(f"\n{len(correcoes)} correções aplicadas com sucesso!")
    elif not correcoes:
        print("\nNenhuma correção necessária.")
    else:
        print(f"\n{len(correcoes)} correções seriam aplicadas. Use --corrigir para aplicar.")

    return len(correcoes)


def desativar_orfas(session, dry_run: bool = True) -> int:
    """
    Desativa variáveis órfãs (sem pergunta associada).

    Args:
        session: Sessão do SQLAlchemy
        dry_run: Se True, apenas mostra o que seria feito

    Returns:
        Número de variáveis desativadas
    """
    print("\n" + "="*70)
    print("DESATIVAÇÃO DE VARIÁVEIS ÓRFÃS" + (" (DRY RUN)" if dry_run else ""))
    print("="*70)

    orfas = session.execute(text("""
        SELECT
            v.id,
            v.slug,
            c.nome as categoria_nome
        FROM extraction_variables v
        LEFT JOIN categorias_resumo_json c ON v.categoria_id = c.id
        WHERE v.ativo = true
          AND v.source_question_id IS NULL
        ORDER BY c.nome, v.slug
    """)).fetchall()

    if not orfas:
        print("  Nenhuma variável órfã encontrada.")
        return 0

    for orfa in orfas:
        var_id, slug, cat_nome = orfa

        if dry_run:
            print(f"  [DRY RUN] Desativar ID={var_id}: '{slug}' (categoria: {cat_nome or 'NENHUMA'})")
        else:
            session.execute(text("""
                UPDATE extraction_variables
                SET ativo = false
                WHERE id = :id
            """), {"id": var_id})
            print(f"  [OK] Desativado ID={var_id}: '{slug}'")

    if not dry_run:
        session.commit()
        print(f"\n{len(orfas)} variáveis órfãs desativadas.")
    else:
        print(f"\n{len(orfas)} variáveis seriam desativadas. Use --corrigir para aplicar.")

    return len(orfas)


def main():
    parser = argparse.ArgumentParser(
        description="Corrige prefixos de variáveis no banco de dados"
    )
    parser.add_argument(
        "--diagnostico",
        action="store_true",
        help="Executa apenas diagnóstico (não faz alterações)"
    )
    parser.add_argument(
        "--corrigir",
        action="store_true",
        help="Aplica as correções (use com cuidado!)"
    )
    parser.add_argument(
        "--desativar-orfas",
        action="store_true",
        help="Desativa variáveis órfãs"
    )

    args = parser.parse_args()

    if not args.diagnostico and not args.corrigir and not args.desativar_orfas:
        parser.print_help()
        print("\nExemplos:")
        print("  python scripts/corrigir_prefixos_variaveis.py --diagnostico")
        print("  python scripts/corrigir_prefixos_variaveis.py --corrigir")
        print("  python scripts/corrigir_prefixos_variaveis.py --desativar-orfas")
        return

    # Conecta ao banco
    print(f"\nConectando ao PostgreSQL...")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        if args.diagnostico:
            diagnosticar_banco(session)

        if args.corrigir:
            if not args.diagnostico:
                diagnosticar_banco(session)

            print("\n" + "="*70)
            print("ATENÇÃO: Esta operação irá modificar o banco de dados!")
            print("="*70)
            resposta = input("Deseja continuar? (digite 'sim' para confirmar): ")

            if resposta.lower() == 'sim':
                corrigir_prefixos(session, dry_run=False)
            else:
                print("Operação cancelada.")

        if args.desativar_orfas:
            if not args.diagnostico and not args.corrigir:
                diagnosticar_banco(session)

            print("\n" + "="*70)
            print("ATENÇÃO: Esta operação irá desativar variáveis órfãs!")
            print("="*70)
            resposta = input("Deseja continuar? (digite 'sim' para confirmar): ")

            if resposta.lower() == 'sim':
                desativar_orfas(session, dry_run=False)
            else:
                print("Operação cancelada.")

    finally:
        session.close()


if __name__ == "__main__":
    main()
