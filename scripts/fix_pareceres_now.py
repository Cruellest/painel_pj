#!/usr/bin/env python3
"""Script para restaurar slugs da categoria pareceres."""
import sys
sys.path.insert(0, '.')

from sqlalchemy import text
from database.connection import SessionLocal

CATEGORIA_ID = 5

JSON_ANTIGO = {
    'pareceres_analisou_medicamento': {'type': 'boolean', 'description': 'O parecer analisou medicamento?'},
    'pareceres_medicamento_sem_anvisa': {'type': 'boolean', 'description': 'O parecer analisou pedido de medicamento sem registro na ANVISA?'},
    'pareceres_medicamentos_sem_anvisa_lista': {'type': 'list', 'description': 'Quais medicamentos sem registro na ANVISA foram analisados no parecer?'},
    'pareceres_medicamento_nao_incorporado_sus': {'type': 'boolean', 'description': 'O parecer analisou pedido de medicamento não incorporado ao SUS?'},
    'pareceres_medicamentos_nao_incorporados_lista': {'type': 'list', 'description': 'Quais medicamentos não incorporados ao SUS foram analisados no parecer?'},
    'pareceres_evidencias_cientificas_alto_nivel': {'type': 'boolean', 'description': 'Existe evidências científicas de alto nível que justifique o fornecimento?'},
    'pareceres_recomendacao_negativa_conitec': {'type': 'text', 'description': 'Algum medicamento não incorporado já teve recomendação negativa da CONITEC'},
    'pareceres_medicamento_oncologico': {'type': 'boolean', 'description': 'O parecer analisou pedido de medicamento oncológico?'},
    'pareceres_medicamentos_oncologicos_lista': {'type': 'list', 'description': 'Quais medicamentos oncológicos foram analisados no parecer?'},
    'pareceres_medicamento_oncologico_incorporado': {'type': 'boolean', 'description': 'Trata-se de medicamento oncológico incorporado'},
    'pareceres_medicamento_oncologico_compra_centralizada': {'type': 'boolean', 'description': 'Trata-se de medicamento oncológico de compra centralizada'},
    'pareceres_medicamento_incorporado_sus': {'type': 'boolean', 'description': 'O parecer analisou pedido de medicamento incorporado ao SUS?'},
    'pareceres_medicamento_cbaf': {'type': 'boolean', 'description': 'O parecer analisou medicamentos do CBAF?'},
    'pareceres_medicamentos_cbaf_lista': {'type': 'list', 'description': 'Quais medicamentos do CBAF foram analisados no parecer?'},
    'pareceres_medicamento_ceaf': {'type': 'boolean', 'description': 'O parecer analisou medicamentos do CEAF?'},
    'pareceres_medicamentos_ceaf_lista': {'type': 'list', 'description': 'Quais medicamentos do CEAF foram analisados no parecer?'},
    'pareceres_medicamento_cesaf': {'type': 'boolean', 'description': 'O parecer analisou medicamento do CESAF?'},
    'pareceres_medicamentos_cesaf_lista': {'type': 'list', 'description': 'Quais medicamentos do CESAF foram analisados no parecer?'},
    'pareceres_patologia_diversa_incorporada': {'type': 'boolean', 'description': 'O parecer analisou medicamento incorporado para patologia diversa?'},
    'pareceres_medicamentos_patologia_diversa_lista': {'type': 'list', 'description': 'Quais medicamentos incorporados para patologia diversa foram analisados?'},
    'pareceres_dosagem_diversa_incorporada': {'type': 'boolean', 'description': 'O parecer analisou medicamento incorporado com dosagem diversa?'},
    'pareceres_medicamentos_dosagem_diversa_lista': {'type': 'list', 'description': 'Quais medicamentos incorporados com dosagem diversa foram analisados?'},
    'pareceres_dispensacao_diversa_incorporada': {'type': 'boolean', 'description': 'O parecer analisou medicamento incorporado com forma de dispensação diversa?'},
    'pareceres_medicamentos_dispensacao_diversa_lista': {'type': 'list', 'description': 'Quais medicamentos incorporados com forma de dispensação diversa foram analisados?'},
    'pareceres_tratamento_autismo': {'type': 'boolean', 'description': 'O parecer analisou pedido de tratamento específico para autismo?'},
    'pareceres_tratamentos_autismo_lista': {'type': 'list', 'description': 'Quais foram os tratamentos solicitados para autismo?'},
    'pareceres_terapia_especifica_autismo': {'type': 'boolean', 'description': 'O parecer analisou solicitação de terapia específica para autismo?'},
    'pareceres_patologias_parte_autora': {'type': 'list', 'description': 'Quais patologias da parte autora foram consideradas pelo parecer?'},
    'pareceres_analisou_canabidiol': {'type': 'boolean', 'description': 'O parecer analisou pedido de canabidiol?'},
    'pareceres_autorizacao_sanitaria_canabidiol': {'type': 'boolean', 'description': 'O parecer informou se a parte tem autorização sanitária para importar o canabidiol?'},
    'pareceres_analisou_insulina': {'type': 'boolean', 'description': 'O parecer analisou pedido de insulina?'},
    'pareceres_tipo_insulina': {'type': 'choice', 'description': 'O parecer identificou solicitação de qual tipo de insulina?'},
    'pareceres_paciente_diabetico': {'type': 'boolean', 'description': 'O paciente é portador de diabetes?'},
    'pareceres_tipo_diabetes': {'type': 'choice', 'description': 'Qual o tipo de diabetes?'},
    'pareceres_medicamento_off_label': {'type': 'boolean', 'description': 'O parecer analisou pedido de medicamento off-label?'},
    'pareceres_nome_medicamento_off_label': {'type': 'text', 'description': 'Liste o nome do medicamento off-label'},
    'pareceres_analisou_cirurgia': {'type': 'boolean', 'description': 'O parecer analisou pedido de cirurgia?'},
    'pareceres_qual_cirurgia': {'type': 'text', 'description': 'Qual cirurgia foi analisada no parecer?'},
    'pareceres_natureza_cirurgia': {'type': 'choice', 'description': 'A cirurgia é eletiva ou de urgência?'},
    'pareceres_laudo_medico_sus': {'type': 'boolean', 'description': 'O laudo analisado foi emitido por médico vinculado ao SUS?'},
    'pareceres_cirurgia_ofertada_sus': {'type': 'boolean', 'description': 'A cirurgia é ofertada pelo SUS?'},
    'pareceres_analisou_exame': {'type': 'boolean', 'description': 'O parecer analisou pedido de exame?'},
    'pareceres_qual_exame': {'type': 'text', 'description': 'Qual exame foi analisado no parecer?'},
    'pareceres_exame_ofertado_sus': {'type': 'boolean', 'description': 'O exame é ofertado pelo SUS?'},
    'pareceres_analisou_consulta': {'type': 'boolean', 'description': 'O parecer analisou pedido de consulta médica?'},
    'pareceres_especialidade_consulta': {'type': 'text', 'description': 'Qual especialidade?'},
    'pareceres_inserido_sisreg': {'type': 'boolean', 'description': 'O paciente está inserido no SISREG?'},
    'pareceres_tempo_sisreg_dias': {'type': 'number', 'description': 'Há quanto tempo (em dias)?'},
    'pareceres_inserido_core': {'type': 'boolean', 'description': 'O paciente está inserido no CORE?'},
    'pareceres_tempo_core_dias': {'type': 'number', 'description': 'Há quanto tempo (em dias)?'},
    'pareceres_analisou_dieta': {'type': 'boolean', 'description': 'O parecer analisou pedido de fornecimento de dieta ou suplemento?'},
    'pareceres_dieta_marca_especifica': {'type': 'boolean', 'description': 'O pedido era de dieta ou suplemento de marca específica?'},
    'pareceres_analisou_home_care': {'type': 'boolean', 'description': 'O parecer analisou pedido de home care?'},
    'pareceres_pedidos_home_care': {'type': 'text', 'description': 'Quais foram os pedidos de home care?'},
    'pareceres_pedido_enfermeiro_24h': {'type': 'boolean', 'description': 'Tem pedido de enfermeiro 24 horas?'},
    'pareceres_analisou_transferencia': {'type': 'boolean', 'description': 'O parecer analisou pedido de transferência hospitalar?'},
    'pareceres_paciente_transferido': {'type': 'boolean', 'description': 'O paciente já foi transferido?'},
    'pareceres_data_transferencia': {'type': 'date', 'description': 'Tem data de transferência informada?'},
    'pareceres_conclusao_parecer': {'type': 'text', 'description': 'Descreva qual foi a conclusão do parecer em relação a cada um dos pedidos'},
    'pareceres_fundamentos_parecer': {'type': 'text', 'description': 'Descreva quais foram os fundamentos do parecer'},
    'pareceres_conclusao_parecer_nat': {'type': 'text', 'description': 'Transcreva toda conclusão do parecer do NAT'}
}

def main():
    db = SessionLocal()

    try:
        # Cria indice de descricoes
        desc_to_slug = {}
        for slug, info in JSON_ANTIGO.items():
            desc = info.get('description', '').lower()
            desc_key = desc.split('?')[0].strip() if '?' in desc else desc[:60]
            if desc_key:
                desc_to_slug[desc_key] = slug

        # Busca variaveis da categoria usando raw SQL
        result = db.execute(text(
            "SELECT id, slug, descricao, label, tipo FROM extraction_variables WHERE categoria_id = :cat_id"
        ), {"cat_id": CATEGORIA_ID})
        variaveis = result.fetchall()
        print(f'Variaveis na categoria {CATEGORIA_ID}: {len(variaveis)}')

        variaveis_atualizadas = 0
        variaveis_removidas = 0
        slugs_usados = set()

        for var_id, slug_antigo, descricao, label, tipo in variaveis:
            # Se ja esta no JSON, mantem
            if slug_antigo in JSON_ANTIGO:
                slugs_usados.add(slug_antigo)
                continue

            # Tenta encontrar por descricao
            desc_var = (descricao or label or '').lower()
            desc_key = desc_var.split('?')[0].strip() if '?' in desc_var else desc_var[:60]

            slug_correto = None
            for desc_json, slug_json in desc_to_slug.items():
                if desc_key and len(desc_key) > 10:
                    if desc_key in desc_json or desc_json in desc_key:
                        slug_correto = slug_json
                        break

            if slug_correto:
                if slug_correto in slugs_usados:
                    print(f'[REMOVER] {slug_antigo} (duplicata de {slug_correto})')
                    db.execute(text("DELETE FROM extraction_variables WHERE id = :id"), {"id": var_id})
                    variaveis_removidas += 1
                else:
                    print(f'[ATUALIZAR] {slug_antigo} -> {slug_correto}')
                    tipo_novo = JSON_ANTIGO[slug_correto].get('type', tipo)
                    db.execute(text(
                        "UPDATE extraction_variables SET slug = :slug, tipo = :tipo WHERE id = :id"
                    ), {"slug": slug_correto, "tipo": tipo_novo, "id": var_id})
                    slugs_usados.add(slug_correto)
                    variaveis_atualizadas += 1
            else:
                print(f'[???] {slug_antigo}')

        # Sincroniza perguntas
        result = db.execute(text("""
            SELECT p.id, p.nome_variavel_sugerido, v.slug
            FROM extraction_questions p
            LEFT JOIN extraction_variables v ON v.source_question_id = p.id
            WHERE p.categoria_id = :cat_id AND p.ativo = true
        """), {"cat_id": CATEGORIA_ID})
        perguntas = result.fetchall()

        perguntas_sincronizadas = 0
        for perg_id, nome_var, var_slug in perguntas:
            if var_slug and nome_var != var_slug:
                db.execute(text(
                    "UPDATE extraction_questions SET nome_variavel_sugerido = :slug WHERE id = :id"
                ), {"slug": var_slug, "id": perg_id})
                perguntas_sincronizadas += 1

        db.commit()

        print()
        print('=' * 50)
        print(f'Variaveis atualizadas: {variaveis_atualizadas}')
        print(f'Variaveis removidas: {variaveis_removidas}')
        print(f'Perguntas sincronizadas: {perguntas_sincronizadas}')
        print('=' * 50)
        print('CONCLUIDO!')

    except Exception as e:
        db.rollback()
        print(f'ERRO: {e}')
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == '__main__':
    main()
