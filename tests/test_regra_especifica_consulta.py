#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Teste de validação da regra específica por tipo de peça.

Cenário: Módulo 71 (orçamento_pacote) tem uma regra específica para Contestação
que deve ativar quando peticao_inicial_pedido_consulta = true.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal

# Importa todos os modelos para resolver relacionamentos SQLAlchemy
from auth.models import User
from admin.models_prompt_groups import PromptGroup, PromptSubgroup, PromptSubcategoria
from admin.models_prompts import RegraDeterministicaTipoPeca, PromptModulo
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
from sistemas.gerador_pecas.models_extraction import ExtractionQuestion, ExtractionModel, ExtractionVariable

from sistemas.gerador_pecas.services_deterministic import (
    avaliar_ativacao_prompt,
    _existe_regra_especifica_ativa
)


def main():
    db = SessionLocal()

    print("=" * 60)
    print("TESTE: Avaliação de regra específica para Contestação")
    print("=" * 60)
    print()

    # Simula dados que seriam extraídos do PDF de Petição Inicial
    dados_extracao = {
        'peticao_inicial_pedido_consulta': True,  # A variável que deveria ativar a regra
        'peticao_inicial_pedido_cirurgia': False,
        'peticao_inicial_pedido_medicamento': True,
    }

    print("Dados de extração simulados:")
    for k, v in dados_extracao.items():
        print(f"  {k}: {v}")
    print()

    # Verifica se existe regra específica para contestação
    modulo_id = 71  # O módulo que tem a regra específica
    tipo_peca = 'contestacao'

    existe = _existe_regra_especifica_ativa(db, modulo_id, tipo_peca)
    print(f"Existe regra específica ativa para módulo {modulo_id} e tipo {tipo_peca}? {existe}")
    print()

    # Busca o módulo para pegar regra global
    modulo = db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
    if not modulo:
        print(f"ERRO: Módulo {modulo_id} não encontrado!")
        db.close()
        return

    print(f"Módulo: {modulo.nome}")
    print(f"Título: {modulo.titulo}")
    print(f"Regra global: {modulo.regra_deterministica}")
    print()

    # Avalia ativação
    print("=" * 60)
    print("Avaliando ativação do prompt...")
    print("=" * 60)
    
    resultado = avaliar_ativacao_prompt(
        prompt_id=modulo_id,
        modo_ativacao='deterministic',
        regra_deterministica=modulo.regra_deterministica,
        dados_extracao=dados_extracao,
        db=db,
        tipo_peca=tipo_peca
    )

    print()
    print("RESULTADO:")
    print(f"  ativar: {resultado['ativar']}")
    print(f"  modo: {resultado['modo']}")
    print(f"  regra_usada: {resultado.get('regra_usada', 'N/A')}")
    print(f"  detalhes: {resultado.get('detalhes', 'N/A')}")
    print()

    # Validação
    if resultado['ativar'] is True and 'especifica' in resultado.get('regra_usada', ''):
        print("✅ SUCESSO: Regra específica foi avaliada e ativou o módulo!")
    elif resultado['ativar'] is True:
        print("⚠️ AVISO: Módulo ativado, mas pela regra GLOBAL, não pela específica!")
    else:
        print("❌ FALHA: Módulo NÃO foi ativado (esperado: ativar)")
        print("   Verifique se a regra específica está sendo avaliada corretamente.")

    db.close()


if __name__ == "__main__":
    main()
