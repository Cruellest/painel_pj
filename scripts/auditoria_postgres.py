"""
Auditoria completa dos módulos no PostgreSQL.
Lista todos os módulos e seu modo de ativação.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from database.connection import engine
from sqlalchemy import text

def auditar():
    with engine.connect() as conn:
        print('=' * 100)
        print('AUDITORIA COMPLETA - MODULOS DE CONTEUDO (PostgreSQL)')
        print('=' * 100)

        # Busca todos os módulos de conteúdo
        result = conn.execute(text('''
            SELECT id, nome, titulo, modo_ativacao,
                   CASE WHEN regra_deterministica IS NOT NULL THEN true ELSE false END as tem_regra
            FROM prompt_modulos
            WHERE tipo = 'conteudo'
            ORDER BY id
        '''))

        todos = list(result)

        det_count = 0
        llm_count = 0
        det_sem_regra = []
        llm_com_regra = []

        print()
        print('DETERMINISTICOS (modo_ativacao = deterministic):')
        print('-' * 100)
        for row in todos:
            modo = row[3] or 'llm'
            tem_regra = row[4]

            if modo == 'deterministic':
                det_count += 1
                status = '[OK]' if tem_regra else '[SEM REGRA!]'
                print(f'  ID {row[0]:3} | {row[1]:40} | {status}')
                if not tem_regra:
                    det_sem_regra.append(row[1])

        print()
        print('LLM (modo_ativacao = llm ou null):')
        print('-' * 100)
        for row in todos:
            modo = row[3] or 'llm'
            tem_regra = row[4]

            if modo != 'deterministic':
                llm_count += 1
                status = '[TEM REGRA - INCONSISTENTE!]' if tem_regra else ''
                print(f'  ID {row[0]:3} | {row[1]:40} | {status}')
                if tem_regra:
                    llm_com_regra.append(row[1])

        print()
        print('=' * 100)
        print('RESUMO:')
        print(f'  - Deterministicos: {det_count}')
        print(f'  - LLM: {llm_count}')
        print(f'  - Total: {det_count + llm_count}')
        print()

        if det_sem_regra:
            print(f'  ALERTA: {len(det_sem_regra)} modulos deterministicos SEM regra:')
            for nome in det_sem_regra:
                print(f'    - {nome}')

        if llm_com_regra:
            print(f'  ALERTA: {len(llm_com_regra)} modulos LLM COM regra (inconsistente):')
            for nome in llm_com_regra:
                print(f'    - {nome}')

        if not det_sem_regra and not llm_com_regra:
            print('  [OK] Todos os modulos estao consistentes!')

        print('=' * 100)

        return len(det_sem_regra) == 0 and len(llm_com_regra) == 0

if __name__ == '__main__':
    sucesso = auditar()
    exit(0 if sucesso else 1)
