#!/usr/bin/env python3
"""Diagnóstico completo do banco de dados para variáveis."""
import psycopg2
import json

DATABASE_URL = "postgresql://postgres:dfDpTUMqyxdZAHAPMOEAhaRBkCVxuJws@yamanote.proxy.rlwy.net:48085/railway"

def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print('=== DIAGNÓSTICO DO BANCO DE DADOS ===')
    print()

    # 1. Total de variáveis por categoria
    print('1. VARIÁVEIS POR CATEGORIA:')
    cur.execute('''
        SELECT v.categoria_id, c.nome, COUNT(*) as total
        FROM extraction_variables v
        LEFT JOIN categorias_resumo_json c ON c.id = v.categoria_id
        GROUP BY v.categoria_id, c.nome
        ORDER BY v.categoria_id
    ''')
    for row in cur.fetchall():
        print(f'   Categoria {row[0]} ({row[1]}): {row[2]} variáveis')

    print()

    # 2. Verificar variáveis com campos NULL obrigatórios
    print('2. VARIÁVEIS COM CAMPOS POTENCIALMENTE INVÁLIDOS:')
    cur.execute("""
        SELECT id, slug, categoria_id, tipo, label
        FROM extraction_variables
        WHERE slug IS NULL OR slug = ''
           OR categoria_id IS NULL
           OR tipo IS NULL OR tipo = ''
    """)
    invalidas = cur.fetchall()
    print(f'   Variáveis com campos obrigatórios NULL/vazios: {len(invalidas)}')
    for row in invalidas[:10]:
        print(f'     ID={row[0]}: slug="{row[1]}", cat={row[2]}, tipo="{row[3]}"')

    print()

    # 3. Verificar variáveis com categoria_id inexistente
    print('3. VARIÁVEIS COM CATEGORIA INEXISTENTE:')
    cur.execute('''
        SELECT v.id, v.slug, v.categoria_id
        FROM extraction_variables v
        LEFT JOIN categorias_resumo_json c ON c.id = v.categoria_id
        WHERE c.id IS NULL
    ''')
    orfas = cur.fetchall()
    print(f'   Variáveis órfãs (categoria não existe): {len(orfas)}')
    for row in orfas[:10]:
        print(f'     ID={row[0]}: slug="{row[1]}", categoria_id={row[2]}')

    print()

    # 4. Verificar slugs duplicados
    print('4. SLUGS DUPLICADOS:')
    cur.execute('''
        SELECT slug, COUNT(*) as cnt
        FROM extraction_variables
        GROUP BY slug
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        LIMIT 10
    ''')
    duplicados = cur.fetchall()
    print(f'   Slugs duplicados: {len(duplicados)}')
    for row in duplicados:
        print(f'     "{row[0][:50]}": {row[1]} ocorrências')

    print()

    # 5. Verificar campo opcoes com valores inválidos
    print('5. VARIÁVEIS COM OPCOES:')
    cur.execute('''
        SELECT COUNT(*) FROM extraction_variables WHERE opcoes IS NOT NULL
    ''')
    print(f'   Total com opcoes: {cur.fetchone()[0]}')

    # Verificar se opcoes é array válido
    cur.execute('''
        SELECT id, slug, opcoes
        FROM extraction_variables
        WHERE opcoes IS NOT NULL
        LIMIT 3
    ''')
    for row in cur.fetchall():
        opcoes = row[2]
        tipo = type(opcoes).__name__
        print(f'   ID={row[0]}: tipo_python={tipo}, valor={str(opcoes)[:50]}')

    print()

    # 6. Verificar dependency_config
    print('6. VARIÁVEIS COM DEPENDENCY_CONFIG:')
    cur.execute('''
        SELECT COUNT(*) FROM extraction_variables WHERE dependency_config IS NOT NULL
    ''')
    print(f'   Total com dependency_config: {cur.fetchone()[0]}')

    print()

    # 7. Verificar estrutura da tabela
    print('7. ESTRUTURA DA TABELA extraction_variables:')
    cur.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'extraction_variables'
        ORDER BY ordinal_position
    """)
    for row in cur.fetchall():
        print(f'   {row[0]}: {row[1]} (nullable={row[2]})')

    print()

    # 8. Verificar últimas variáveis criadas (podem ser as problemáticas)
    print('8. ÚLTIMAS 10 VARIÁVEIS CRIADAS:')
    cur.execute('''
        SELECT id, slug, categoria_id, tipo, criado_em
        FROM extraction_variables
        ORDER BY id DESC
        LIMIT 10
    ''')
    for row in cur.fetchall():
        print(f'   ID={row[0]}: {row[1][:40]} (cat={row[2]}, tipo={row[3]})')

    conn.close()

if __name__ == '__main__':
    main()
