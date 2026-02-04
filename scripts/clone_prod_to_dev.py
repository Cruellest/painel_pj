#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Clone banco de producao para desenvolvimento/homologacao"""

import psycopg2
from psycopg2 import sql
from io import StringIO

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

def get_tables(conn):
    """Lista tabelas do banco"""
    cur = conn.cursor()
    cur.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
    """)
    return [row[0] for row in cur.fetchall()]

def get_row_count(conn, table):
    """Conta registros na tabela"""
    cur = conn.cursor()
    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table)))
    return cur.fetchone()[0]

def copy_table(prod_conn, dev_conn, table):
    """Copia uma tabela usando COPY (mais rapido)"""
    # Exporta para CSV em memoria
    buffer = StringIO()
    prod_cur = prod_conn.cursor()
    prod_cur.copy_expert(
        sql.SQL("COPY {} TO STDOUT WITH CSV HEADER").format(sql.Identifier(table)),
        buffer
    )

    # Importa do CSV
    buffer.seek(0)
    dev_cur = dev_conn.cursor()

    # Limpa tabela destino
    dev_cur.execute(sql.SQL("TRUNCATE {} CASCADE").format(sql.Identifier(table)))

    # Importa dados
    buffer.seek(0)
    next(buffer)  # Pula header
    dev_cur.copy_expert(
        sql.SQL("COPY {} FROM STDIN WITH CSV").format(sql.Identifier(table)),
        buffer
    )

    return dev_cur.rowcount

def main():
    print("=" * 60)
    print("CLONE: Producao -> Homologacao")
    print("=" * 60)

    # Conecta
    print("\nConectando...")
    prod_conn = psycopg2.connect(**PROD)
    dev_conn = psycopg2.connect(**DEV)
    prod_conn.autocommit = False
    dev_conn.autocommit = False

    print("  Producao: OK")
    print("  Homologacao: OK")

    # Lista tabelas
    tables = get_tables(prod_conn)
    print(f"\nTabelas: {len(tables)}")

    # Desabilita FK no dev
    dev_cur = dev_conn.cursor()
    dev_cur.execute("SET session_replication_role = replica")

    # Copia cada tabela
    print("\nCopiando dados...\n")

    for i, table in enumerate(tables, 1):
        try:
            count = get_row_count(prod_conn, table)
            if count == 0:
                print(f"  [{i:2}/{len(tables)}] {table}: vazia")
                continue

            copied = copy_table(prod_conn, dev_conn, table)
            dev_conn.commit()
            print(f"  [{i:2}/{len(tables)}] {table}: {count} registros")

        except Exception as e:
            dev_conn.rollback()
            print(f"  [{i:2}/{len(tables)}] {table}: ERRO - {str(e)[:60]}")

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

    # Fecha conexoes
    prod_conn.close()
    dev_conn.close()

    print("\n" + "=" * 60)
    print("Clone concluido com sucesso!")
    print("=" * 60)

if __name__ == '__main__':
    main()
