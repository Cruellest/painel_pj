# Script para verificar tipos de peça cadastrados
# Execute com: railway run python scripts/diagnostico/check_tipos_peca.py

import sys
sys.path.insert(0, '.')

from sqlalchemy import text
from database.connection import engine

print("=" * 70)
print("TIPOS DE PECA CADASTRADOS (prompt_modulos onde tipo='peca')")
print("=" * 70)

with engine.connect() as conn:
    # Busca módulos de peça
    result = conn.execute(text("""
        SELECT id, nome, titulo, categoria, ativo
        FROM prompt_modulos
        WHERE tipo = 'peca' AND ativo = true
        ORDER BY ordem
    """))
    modulos = result.fetchall()

    print(f"\nTotal de tipos de peca ativos: {len(modulos)}\n")

    nomes_prompt = set()
    for m in modulos:
        print(f"ID: {m.id}")
        print(f"  nome:      '{m.nome}'")
        print(f"  titulo:    '{m.titulo}'")
        print(f"  categoria: '{m.categoria}'")
        print()
        nomes_prompt.add(m.nome)

    # Verifica se tem tipos_peca (para filtro de categorias)
    print("=" * 70)
    print("TIPOS DE PECA PARA FILTRO DE DOCUMENTOS (tipos_peca)")
    print("=" * 70)

    try:
        result = conn.execute(text("""
            SELECT id, nome, titulo
            FROM tipos_peca
            WHERE ativo = true
            ORDER BY ordem
        """))
        tipos = result.fetchall()

        print(f"\nTotal de tipos no filtro: {len(tipos)}\n")

        nomes_filtro = set()
        for t in tipos:
            print(f"ID: {t.id}")
            print(f"  nome:   '{t.nome}'")
            print(f"  titulo: '{t.titulo}'")
            print()
            nomes_filtro.add(t.nome)

        # Compara nomes
        print("=" * 70)
        print("COMPARACAO DE NOMES")
        print("=" * 70)
        print(f"\nNomes em prompt_modulos: {sorted(nomes_prompt)}")
        print(f"Nomes em tipos_peca:     {sorted(nomes_filtro)}")

        so_prompt = nomes_prompt - nomes_filtro
        so_filtro = nomes_filtro - nomes_prompt

        if so_prompt:
            print(f"\n[!] Tipos so em prompt_modulos (sem filtro de docs): {so_prompt}")
        if so_filtro:
            print(f"\n[!] Tipos so em tipos_peca (sem prompt): {so_filtro}")
        if not so_prompt and not so_filtro:
            print(f"\n[OK] Todos os tipos estao sincronizados!")

    except Exception as e:
        print(f"\n[!] Tabela tipos_peca nao existe ou erro: {e}")
