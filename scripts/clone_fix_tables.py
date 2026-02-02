#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Corrige tabelas que falharam no clone via COPY"""

import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

# URLs
PROD = {
    'host': 'yamanote.proxy.rlwy.net',
    'port': 48085,
    'dbname': 'railway',
    'user': 'postgres',
    'password': 'dfDpTUMqyxdZAHAPMOEAhaRBkCVxuJws'
}

DEV = {
    'host': 'centerbeam.proxy.rlwy.net',
    'port': 50662,
    'dbname': 'railway',
    'user': 'postgres',
    'password': 'pGJBjuovHGUSyZHYsvHmJtNGAsezCOCg'
}

# Tabelas que falharam
FAILED_TABLES = [
    'analises',
    'categorias_documento',
    'categorias_resumo_json',
    'extraction_questions',
    'gemini_api_logs',
    'geracoes_pecas',
    'geracoes_prestacao_contas',
    'performance_logs',
    'prompt_activation_logs',
    'prompt_modulos',
    'prompt_modulos_historico',
    'users',
    'regra_deterministica_tipo_peca',  # Pode nao existir em prod
]

def get_columns(conn, table):
    """Obtem colunas da tabela"""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s AND table_schema = 'public'
        ORDER BY ordinal_position
    """, (table,))
    return [row[0] for row in cur.fetchall()]

def copy_table_insert(prod_conn, dev_conn, table):
    """Copia tabela usando INSERT"""
    prod_cur = prod_conn.cursor()
    dev_cur = dev_conn.cursor()

    # Obtem colunas
    columns = get_columns(prod_conn, table)
    if not columns:
        return 0, "tabela nao existe"

    # Limpa destino
    try:
        dev_cur.execute(sql.SQL("TRUNCATE {} CASCADE").format(sql.Identifier(table)))
        dev_conn.commit()
    except Exception as e:
        dev_conn.rollback()
        return 0, f"erro truncate: {e}"

    # Seleciona dados
    cols_sql = sql.SQL(', ').join([sql.Identifier(c) for c in columns])
    prod_cur.execute(sql.SQL("SELECT {} FROM {}").format(cols_sql, sql.Identifier(table)))

    rows = prod_cur.fetchall()
    if not rows:
        return 0, "vazia"

    # Insere em batches
    batch_size = 100
    total = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]

        # Monta INSERT
        placeholders = sql.SQL(', ').join([sql.Placeholder()] * len(columns))
        insert_sql = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(table),
            cols_sql,
            placeholders
        )

        for row in batch:
            try:
                dev_cur.execute(insert_sql, row)
                total += 1
            except Exception as e:
                dev_conn.rollback()
                # Tenta continuar com proximas linhas
                continue

        dev_conn.commit()

    return total, None

def main():
    print("=" * 60)
    print("CORRIGINDO TABELAS COM ERRO")
    print("=" * 60)

    prod_conn = psycopg2.connect(**PROD)
    dev_conn = psycopg2.connect(**DEV)

    # Desabilita FK
    dev_cur = dev_conn.cursor()
    dev_cur.execute("SET session_replication_role = replica")
    dev_conn.commit()

    print()
    for i, table in enumerate(FAILED_TABLES, 1):
        count, error = copy_table_insert(prod_conn, dev_conn, table)
        if error:
            print(f"  [{i:2}/{len(FAILED_TABLES)}] {table}: {error}")
        else:
            print(f"  [{i:2}/{len(FAILED_TABLES)}] {table}: {count} registros")

    # Reabilita FK
    dev_cur.execute("SET session_replication_role = DEFAULT")
    dev_conn.commit()

    # Reseta sequences
    print("\nResetando sequences...")
    dev_cur.execute("""
        SELECT 'SELECT setval(' || quote_literal(S.relname) || ', COALESCE(MAX(' || quote_ident(C.attname) || '), 1)) FROM ' || quote_ident(T.relname) || ';'
        FROM pg_class AS S
        JOIN pg_depend AS D ON S.oid = D.objid
        JOIN pg_class AS T ON D.refobjid = T.oid
        JOIN pg_attribute AS C ON D.refobjid = C.attrelid AND D.refobjsubid = C.attnum
        WHERE S.relkind = 'S' AND D.deptype = 'a'
    """)

    for row in dev_cur.fetchall():
        try:
            dev_cur.execute(row[0])
        except:
            pass
    dev_conn.commit()

    prod_conn.close()
    dev_conn.close()

    print("\n" + "=" * 60)
    print("Correcao concluida!")
    print("=" * 60)

if __name__ == '__main__':
    main()
