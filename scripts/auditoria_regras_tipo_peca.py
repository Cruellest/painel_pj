#!/usr/bin/env python
"""
Script de auditoria para verificar regras por tipo de peça (via SQL direto).
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def auditar():
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        print("=" * 80)
        print("AUDITORIA DE REGRAS POR TIPO DE PEÇA")
        print("=" * 80)

        # 1. Buscar módulo orçamento_pacote
        print("\n[1] BUSCANDO MÓDULO 'orçamento_pacote' ou similar...")
        result = conn.execute(text("""
            SELECT id, nome, titulo, modo_ativacao, ativo, regra_deterministica
            FROM prompt_modulos
            WHERE nome ILIKE '%orcamento%' OR nome ILIKE '%orçamento%'
               OR titulo ILIKE '%orçamento%' OR titulo ILIKE '%pacote%'
            LIMIT 10
        """))
        modulos = result.fetchall()

        if not modulos:
            print("  [ERRO] Nenhum módulo encontrado com 'orcamento' ou 'pacote'!")
            return

        for m in modulos:
            print(f"\n  ID: {m[0]}")
            print(f"  Nome: {m[1]}")
            print(f"  Título: {m[2]}")
            print(f"  Modo ativação: {m[3]}")
            print(f"  Ativo: {m[4]}")
            print(f"  Regra global: {m[5]}")

        # Pegar o primeiro módulo encontrado
        modulo_id = modulos[0][0]
        modulo_nome = modulos[0][1]

        # 2. Buscar regras específicas deste módulo
        print(f"\n[2] REGRAS ESPECÍFICAS DO MÓDULO '{modulo_nome}' (ID={modulo_id})...")
        result = conn.execute(text("""
            SELECT id, tipo_peca, regra_deterministica, regra_texto_original, ativo
            FROM regra_deterministica_tipo_peca
            WHERE modulo_id = :modulo_id
        """), {"modulo_id": modulo_id})
        regras = result.fetchall()

        if not regras:
            print("  >>> NENHUMA REGRA ESPECÍFICA ENCONTRADA PARA ESTE MÓDULO!")
        else:
            for r in regras:
                print(f"\n  ID: {r[0]}")
                print(f"  Tipo peça: {r[1]}")
                print(f"  Regra: {r[2]}")
                print(f"  Texto original: {r[3]}")
                print(f"  Ativo: {r[4]}")

        # 3. Listar TODAS as regras específicas no sistema
        print("\n" + "=" * 80)
        print("[3] TODAS AS REGRAS ESPECÍFICAS NO SISTEMA")
        print("=" * 80)

        result = conn.execute(text("""
            SELECT r.id, r.modulo_id, m.nome as modulo_nome, r.tipo_peca,
                   r.regra_deterministica, r.ativo
            FROM regra_deterministica_tipo_peca r
            JOIN prompt_modulos m ON m.id = r.modulo_id
            ORDER BY r.modulo_id, r.tipo_peca
        """))
        todas_regras = result.fetchall()

        print(f"\nTotal de regras específicas: {len(todas_regras)}")

        for r in todas_regras:
            print(f"\n  Módulo: {r[2]} (ID={r[1]})")
            print(f"    Tipo peça: {r[3]}")
            print(f"    Ativo: {r[5]}")
            print(f"    Regra: {r[4]}")

        # 4. Verificar variáveis disponíveis na última extração
        print("\n" + "=" * 80)
        print("[4] VERIFICANDO VARIÁVEIS DE EXTRAÇÃO DISPONÍVEIS")
        print("=" * 80)

        result = conn.execute(text("""
            SELECT slug, tipo_dado
            FROM extraction_variables
            WHERE ativo = true
            ORDER BY slug
        """))
        variaveis = result.fetchall()

        print(f"\nTotal de variáveis de extração: {len(variaveis)}")
        for v in variaveis:
            print(f"  - {v[0]} ({v[1]})")


if __name__ == "__main__":
    auditar()
