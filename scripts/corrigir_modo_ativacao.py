#!/usr/bin/env python
"""
Script para corrigir divergências de modo_ativacao em módulos de prompt.

Regra: Se um módulo possui regras determinísticas (global ou por tipo de peça),
seu modo_ativacao deve ser 'deterministic', não 'llm'.

Uso:
    python scripts/corrigir_modo_ativacao.py          # Apenas auditoria (dry-run)
    python scripts/corrigir_modo_ativacao.py --fix    # Aplica correções
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def auditar_e_corrigir(aplicar_correcao: bool = False):
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        print("=" * 80)
        print("AUDITORIA DE MODO DE ATIVAÇÃO")
        print("=" * 80)

        # 1. Módulos com regra_deterministica global mas modo_ativacao != 'deterministic'
        print("\n[1] Módulos com regra GLOBAL mas modo incorreto...")
        result = conn.execute(text("""
            SELECT id, nome, titulo, modo_ativacao
            FROM prompt_modulos
            WHERE regra_deterministica IS NOT NULL
              AND regra_deterministica::text != 'null'
              AND regra_deterministica::text != '{}'
              AND (modo_ativacao IS NULL OR modo_ativacao != 'deterministic')
        """))
        modulos_global = result.fetchall()

        if not modulos_global:
            print("  [OK] Nenhum módulo com divergência em regra global.")
        else:
            print(f"  [DIVERGÊNCIA] {len(modulos_global)} módulo(s) com regra global mas modo incorreto:")
            for m in modulos_global:
                print(f"    - ID={m[0]}: {m[1]} | modo_atual={m[3] or 'NULL'}")

        # 2. Módulos com regras por tipo de peça mas modo_ativacao != 'deterministic'
        print("\n[2] Módulos com regra POR TIPO DE PEÇA mas modo incorreto...")
        result = conn.execute(text("""
            SELECT DISTINCT pm.id, pm.nome, pm.titulo, pm.modo_ativacao,
                   COUNT(r.id) as qtd_regras
            FROM prompt_modulos pm
            JOIN regra_deterministica_tipo_peca r ON r.modulo_id = pm.id
            WHERE r.ativo = true
              AND (pm.modo_ativacao IS NULL OR pm.modo_ativacao != 'deterministic')
            GROUP BY pm.id, pm.nome, pm.titulo, pm.modo_ativacao
        """))
        modulos_tipo_peca = result.fetchall()

        if not modulos_tipo_peca:
            print("  [OK] Nenhum módulo com divergência em regras por tipo de peça.")
        else:
            print(f"  [DIVERGÊNCIA] {len(modulos_tipo_peca)} módulo(s) com regras por tipo de peça mas modo incorreto:")
            for m in modulos_tipo_peca:
                print(f"    - ID={m[0]}: {m[1]} | modo_atual={m[3] or 'NULL'} | {m[4]} regra(s)")

        # 3. Consolidar IDs únicos para correção
        ids_para_corrigir = set()
        for m in modulos_global:
            ids_para_corrigir.add(m[0])
        for m in modulos_tipo_peca:
            ids_para_corrigir.add(m[0])

        total_divergencias = len(ids_para_corrigir)

        print("\n" + "=" * 80)
        if total_divergencias == 0:
            print("[RESULTADO] Nenhuma divergência encontrada. Tudo OK!")
            return

        print(f"[RESULTADO] {total_divergencias} módulo(s) com divergência de modo_ativacao")

        if not aplicar_correcao:
            print("\n[INFO] Execute com --fix para aplicar correções:")
            print("       python scripts/corrigir_modo_ativacao.py --fix")
            return

        # Aplicar correções
        print("\n[CORRIGINDO] Atualizando modo_ativacao para 'deterministic'...")
        result = conn.execute(text("""
            UPDATE prompt_modulos
            SET modo_ativacao = 'deterministic'
            WHERE id IN :ids
        """), {"ids": tuple(ids_para_corrigir)})

        conn.commit()

        print(f"[OK] {result.rowcount} módulo(s) corrigido(s)!")

        # Verificar correção
        print("\n[VERIFICANDO] Re-auditando após correção...")
        result = conn.execute(text("""
            SELECT id, nome, modo_ativacao
            FROM prompt_modulos
            WHERE id IN :ids
        """), {"ids": tuple(ids_para_corrigir)})

        for m in result.fetchall():
            status = "OK" if m[2] == 'deterministic' else "ERRO"
            print(f"  [{status}] ID={m[0]}: {m[1]} | modo_ativacao={m[2]}")


if __name__ == "__main__":
    aplicar = "--fix" in sys.argv
    auditar_e_corrigir(aplicar_correcao=aplicar)
