# scripts/debug_orcamento_pacote.py
"""
Script para investigar bug: modulo orcamento_pacote nao ativou
Processo: 08001042920268120101
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Banco de producao
DATABASE_URL = os.environ.get(
    "DATABASE_URL_PROD",
    "postgresql://postgres:dfDpTUMqyxdZAHAPMOEAhaRBkCVxuJws@yamanote.proxy.rlwy.net:48085/railway"
)

PROCESSO = "08001042920268120101"
MODULO_NOME = "orçamento_pacote"


def main():
    print("=" * 80)
    print("INVESTIGACAO: Modulo orcamento_pacote nao ativou")
    print(f"Processo: {PROCESSO}")
    print("=" * 80)

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # 1. Buscar geracao do processo
        print("\n[1] BUSCANDO GERACAO DO PROCESSO")
        print("-" * 40)

        result = session.execute(text("""
            SELECT
                id,
                numero_cnj,
                tipo_peca,
                dados_processo,
                prompt_enviado,
                criado_em
            FROM geracoes_pecas
            WHERE numero_cnj LIKE :cnj
            ORDER BY criado_em DESC
            LIMIT 3
        """), {"cnj": f"%{PROCESSO[-14:]}%"})

        rows = result.fetchall()

        if not rows:
            print(f"[ERRO] Nenhuma geracao encontrada para o processo {PROCESSO}")
            return

        for i, row in enumerate(rows):
            print(f"\n--- Geracao {i+1} ---")
            print(f"ID: {row.id}")
            print(f"Processo: {row.numero_cnj}")
            print(f"Tipo Peca: {row.tipo_peca}")
            print(f"Data: {row.criado_em}")

            # Verifica se orcamento_pacote esta no prompt
            if row.prompt_enviado:
                if MODULO_NOME in row.prompt_enviado or "ORCAMENTO DO TIPO" in row.prompt_enviado.upper():
                    print(f"  [OK] Referencia ao modulo encontrada no prompt")
                else:
                    print(f"  [ERRO] Modulo {MODULO_NOME} NAO encontrado no prompt")

        # Usa a geracao mais recente para analise
        geracao = rows[0]
        geracao_id = geracao.id
        dados_processo = geracao.dados_processo or {}

        # 2. Verificar variaveis do snapshot
        print("\n[2] SNAPSHOT DE VARIAVEIS")
        print("-" * 40)

        if dados_processo:
            print(f"Total de variaveis: {len(dados_processo)}")

            # Variaveis criticas para o modulo
            vars_criticas = [
                'peticao_inicial_pedido_cirurgia',
                'pareceres_analisou_cirurgia',
                'peticao_inicial_pedido_procedimento',
                'pareceres_analisou_procedimento',
                'peticao_inicial_pedido_medicamento',
                'pareceres_analisou_medicamento'
            ]

            print("\nVariaveis criticas:")
            for var in vars_criticas:
                valor = dados_processo.get(var, "NAO EXISTE")
                if valor is True:
                    status = "[OK]"
                elif valor is False:
                    status = "[FALSO]"
                else:
                    status = "[???]"
                print(f"  {status} {var}: {valor}")
        else:
            print("[ERRO] dados_processo esta VAZIO!")

        # 3. Buscar regra do modulo orcamento_pacote
        print("\n[3] REGRA DO MODULO orcamento_pacote")
        print("-" * 40)

        result = session.execute(text("""
            SELECT
                id,
                titulo,
                nome,
                modo_ativacao,
                regra_deterministica,
                categoria,
                ativo
            FROM prompt_modulos
            WHERE nome = :nome
        """), {"nome": MODULO_NOME})

        modulo = result.fetchone()

        if modulo:
            print(f"ID: {modulo.id}")
            print(f"Titulo: {modulo.titulo}")
            print(f"Nome: {modulo.nome}")
            print(f"Modo ativacao: {modulo.modo_ativacao}")
            print(f"Categoria: {modulo.categoria}")
            print(f"Ativo: {modulo.ativo}")

            # Busca tipos de peca associados
            tipos_result = session.execute(text("""
                SELECT tipo_peca FROM prompt_modulo_tipo_peca
                WHERE modulo_id = :modulo_id AND ativo = true
            """), {"modulo_id": modulo.id})
            tipos_peca = [r[0] for r in tipos_result.fetchall()]
            print(f"Tipos peca permitidos: {tipos_peca}")

            if modulo.regra_deterministica:
                print(f"\nRegra deterministica (JSON):")
                print(json.dumps(modulo.regra_deterministica, indent=2, ensure_ascii=False))
            else:
                print("\n[WARN] Sem regra deterministica definida!")
        else:
            print(f"[ERRO] Modulo {MODULO_NOME} nao encontrado!")
            return

        # 4. Simular avaliacao da regra
        print("\n[4] SIMULACAO DA AVALIACAO")
        print("-" * 40)

        if modulo and modulo.regra_deterministica and dados_processo:
            regra = modulo.regra_deterministica

            # Avalia cada condicao individualmente
            if regra.get('type') in ['and', 'or']:
                operador = regra.get('type').upper()
                conditions = regra.get('conditions', [])
                print(f"Operador: {operador}")
                print(f"Condicoes: {len(conditions)}")

                resultados = []
                for i, cond in enumerate(conditions):
                    if cond.get('type') == 'condition':
                        var = cond.get('variable')
                        expected = cond.get('value')
                        actual = dados_processo.get(var)

                        # Normaliza para comparacao
                        if expected == 1:
                            expected_norm = True
                        elif expected == 0:
                            expected_norm = False
                        else:
                            expected_norm = expected

                        match = actual == expected_norm
                        resultados.append(match)

                        status = "[OK]" if match else "[FALHOU]"
                        print(f"  [{i+1}] {status} {var} == {expected}")
                        print(f"       Esperado: {expected_norm} | Atual: {actual}")
                    elif cond.get('type') in ['and', 'or']:
                        # Sub-grupo
                        sub_op = cond.get('type').upper()
                        sub_conds = cond.get('conditions', [])
                        print(f"  [{i+1}] Sub-grupo {sub_op} com {len(sub_conds)} condicoes:")

                        sub_results = []
                        for j, sub_cond in enumerate(sub_conds):
                            if sub_cond.get('type') == 'condition':
                                var = sub_cond.get('variable')
                                expected = sub_cond.get('value')
                                actual = dados_processo.get(var)

                                if expected == 1:
                                    expected_norm = True
                                elif expected == 0:
                                    expected_norm = False
                                else:
                                    expected_norm = expected

                                match = actual == expected_norm
                                sub_results.append(match)

                                status = "[OK]" if match else "[FALHOU]"
                                print(f"       [{j+1}] {status} {var} == {expected}")
                                print(f"            Esperado: {expected_norm} | Atual: {actual}")

                        if sub_op == 'AND':
                            sub_final = all(sub_results) if sub_results else False
                        else:
                            sub_final = any(sub_results) if sub_results else False

                        resultados.append(sub_final)
                        print(f"       Sub-grupo resultado: {sub_final}")

                # Resultado final
                if operador == 'AND':
                    final = all(resultados) if resultados else False
                else:
                    final = any(resultados) if resultados else False

                result_str = "[ATIVA]" if final else "[NAO ATIVA]"
                print(f"\nResultado final ({operador}): {result_str}")

            # Avalia com o evaluator real
            try:
                from sistemas.gerador_pecas.services_deterministic import DeterministicRuleEvaluator
                evaluator = DeterministicRuleEvaluator(session)
                resultado_real = evaluator.avaliar(regra, dados_processo)
                result_str = "[ATIVA]" if resultado_real else "[NAO ATIVA]"
                print(f"Avaliacao pelo engine real: {result_str}")
            except Exception as e:
                print(f"[ERRO] Falha ao usar evaluator real: {e}")

        # 5. Verificar filtros por tipo de peca
        print("\n[5] VERIFICACAO DE FILTROS")
        print("-" * 40)

        if modulo:
            if tipos_peca:
                print(f"Tipos de peca permitidos: {tipos_peca}")

                if geracao.tipo_peca:
                    if geracao.tipo_peca in tipos_peca or not tipos_peca:
                        print(f"  [OK] Tipo '{geracao.tipo_peca}' esta permitido")
                    else:
                        print(f"  [ERRO] Tipo '{geracao.tipo_peca}' NAO esta na lista!")
            else:
                print("Tipos de peca: todos (sem restricao)")

        # 6. Verificar se ha outros modulos de cirurgia que ativaram
        print("\n[6] OUTROS MODULOS RELACIONADOS A CIRURGIA/ORCAMENTO")
        print("-" * 40)

        result = session.execute(text("""
            SELECT
                id,
                titulo,
                nome,
                modo_ativacao,
                regra_deterministica
            FROM prompt_modulos
            WHERE (
                titulo ILIKE '%cirurgia%'
                OR titulo ILIKE '%orcamento%'
                OR nome ILIKE '%cirurgia%'
                OR nome ILIKE '%orcamento%'
            )
            AND ativo = true
            ORDER BY nome
        """))

        modulos_relacionados = result.fetchall()
        print(f"Modulos relacionados encontrados: {len(modulos_relacionados)}")

        for m in modulos_relacionados:
            # Verifica se esta no prompt da geracao
            if geracao.prompt_enviado and (m.nome in geracao.prompt_enviado or m.titulo in geracao.prompt_enviado):
                ativou = "[ATIVADO]"
            else:
                ativou = "[NAO ATIVADO]"

            print(f"  {ativou} {m.nome}: {m.titulo[:60]}...")

            # Se nao ativou, mostra a regra
            if "NAO ATIVADO" in ativou and m.regra_deterministica:
                regra = m.regra_deterministica
                if regra.get('type') in ['and', 'or']:
                    conditions = regra.get('conditions', [])
                    vars_usadas = []
                    for c in conditions:
                        if c.get('type') == 'condition':
                            vars_usadas.append(c.get('variable'))
                        elif c.get('type') in ['and', 'or']:
                            for sc in c.get('conditions', []):
                                if sc.get('type') == 'condition':
                                    vars_usadas.append(sc.get('variable'))
                    print(f"       Variaveis: {vars_usadas}")

        print("\n" + "=" * 80)
        print("FIM DA INVESTIGACAO")
        print("=" * 80)

    except Exception as e:
        print(f"\n[ERRO] Erro: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
