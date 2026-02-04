#!/usr/bin/env python3
"""
Script de diagnóstico para investigar por que módulos com regras determinísticas
estão aparecendo como "Indeterminado" no ambiente de teste.

Executa:
    python scripts/debug_ativacao_modulos.py

Ou com nome de módulo específico:
    python scripts/debug_ativacao_modulos.py prel_nao_comparecimento
"""

import sys
import os
import json
from typing import Optional, Dict, Any

# Adiciona diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal

# Importa init_db para carregar todos os modelos
from database import init_db

from admin.models_prompt_groups import PromptGroup
from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca
from sistemas.gerador_pecas.services_deterministic import (
    tem_regras_deterministicas,
    resolve_activation_mode,
    resolve_activation_mode_from_db,
    avaliar_ativacao_prompt
)


def debug_modulo(db, modulo: PromptModulo, tipo_peca: str = "contestacao"):
    """Debug detalhado de um módulo específico."""
    print(f"\n{'='*80}")
    print(f"MÓDULO: {modulo.nome} (ID: {modulo.id})")
    print(f"{'='*80}")

    # Info básica
    print(f"\n[1] INFORMAÇÕES BÁSICAS:")
    print(f"    - Título: {modulo.titulo}")
    print(f"    - Tipo: {modulo.tipo}")
    print(f"    - Ativo: {modulo.ativo}")
    print(f"    - modo_ativacao (salvo): {modulo.modo_ativacao}")
    print(f"    - fallback_habilitado: {modulo.fallback_habilitado}")

    # Regra global primária
    print(f"\n[2] REGRA GLOBAL PRIMÁRIA:")
    if modulo.regra_deterministica:
        print(f"    - Existe: Sim")
        print(f"    - Tipo: {type(modulo.regra_deterministica)}")
        print(f"    - Valor: {json.dumps(modulo.regra_deterministica, indent=6, ensure_ascii=False)}")

        # Verifica se tem campo "type"
        if isinstance(modulo.regra_deterministica, dict):
            if modulo.regra_deterministica.get("type"):
                print(f"    - Campo 'type': '{modulo.regra_deterministica.get('type')}' [OK]")
            else:
                print(f"    - Campo 'type': AUSENTE [PROBLEMA!]")
                print(f"    - Chaves presentes: {list(modulo.regra_deterministica.keys())}")
        else:
            print(f"    - ATENÇÃO: regra não é dict, é {type(modulo.regra_deterministica)}")

        print(f"    - Texto original: {modulo.regra_texto_original}")
    else:
        print(f"    - Existe: Não")

    # Regra global secundária
    print(f"\n[3] REGRA GLOBAL SECUNDÁRIA:")
    if modulo.regra_deterministica_secundaria:
        print(f"    - Existe: Sim")
        print(f"    - Valor: {json.dumps(modulo.regra_deterministica_secundaria, indent=6, ensure_ascii=False)}")
    else:
        print(f"    - Existe: Não")

    # Regras por tipo de peça
    print(f"\n[4] REGRAS ESPECÍFICAS POR TIPO DE PEÇA:")
    regras_tipo = db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.modulo_id == modulo.id
    ).all()

    if regras_tipo:
        for r in regras_tipo:
            print(f"\n    [{r.tipo_peca}] (ID: {r.id}, Ativo: {r.ativo})")
            if r.regra_deterministica:
                print(f"        - Regra: {json.dumps(r.regra_deterministica, indent=8, ensure_ascii=False)}")
                if isinstance(r.regra_deterministica, dict) and r.regra_deterministica.get("type"):
                    print(f"        - Campo 'type': '{r.regra_deterministica.get('type')}' [OK]")
                else:
                    print(f"        - Campo 'type': AUSENTE [PROBLEMA!]")
            else:
                print(f"        - Regra: None")
            print(f"        - Texto original: {r.regra_texto_original}")
    else:
        print(f"    - Nenhuma regra específica por tipo de peça")

    # Teste tem_regras_deterministicas
    print(f"\n[5] VERIFICAÇÃO tem_regras_deterministicas():")
    regras_tipo_dicts = [
        {"regra_deterministica": r.regra_deterministica, "tipo_peca": r.tipo_peca}
        for r in regras_tipo if r.ativo and r.regra_deterministica
    ]

    resultado_tem_regras = tem_regras_deterministicas(
        regra_primaria=modulo.regra_deterministica,
        regra_secundaria=modulo.regra_deterministica_secundaria,
        fallback_habilitado=modulo.fallback_habilitado,
        regras_tipo_peca=regras_tipo_dicts
    )
    print(f"    - Resultado: {resultado_tem_regras}")

    if not resultado_tem_regras:
        print(f"    - DIAGNÓSTICO: Função retorna False porque:")

        # Verifica regra primária
        if modulo.regra_deterministica:
            if isinstance(modulo.regra_deterministica, dict):
                if not modulo.regra_deterministica.get("type"):
                    print(f"        1. Regra primária existe mas NÃO TEM campo 'type'")
            else:
                print(f"        1. Regra primária não é dict")
        else:
            print(f"        1. Regra primária é None")

        # Verifica regras tipo peça
        if not regras_tipo_dicts:
            print(f"        2. Nenhuma regra por tipo de peça ativa")
        else:
            for rt in regras_tipo_dicts:
                regra_det = rt.get("regra_deterministica", rt)
                if not (isinstance(regra_det, dict) and regra_det.get("type")):
                    print(f"        2. Regra tipo {rt.get('tipo_peca')} não tem 'type' válido")

    # Teste resolve_activation_mode_from_db
    print(f"\n[6] VERIFICAÇÃO resolve_activation_mode_from_db():")
    modo_calculado = resolve_activation_mode_from_db(
        db=db,
        modulo_id=modulo.id,
        modo_ativacao_salvo=modulo.modo_ativacao,
        regra_primaria=modulo.regra_deterministica,
        regra_secundaria=modulo.regra_deterministica_secundaria,
        fallback_habilitado=modulo.fallback_habilitado
    )
    print(f"    - Modo calculado: {modo_calculado}")
    print(f"    - Modo salvo: {modulo.modo_ativacao}")

    if modo_calculado != "deterministic" and resultado_tem_regras:
        print(f"    - INCONSISTÊNCIA: tem regras mas modo não é deterministic!")
    elif modo_calculado == "deterministic" and not resultado_tem_regras:
        print(f"    - INCONSISTÊNCIA: modo é deterministic mas sem regras!")

    # Simula avaliação COM variáveis
    print(f"\n[7] SIMULACAO avaliar_ativacao_prompt() COM variaveis (tipo_peca='{tipo_peca}'):")
    dados_teste = {
        "decisoes_audiencia_inicial": True,
        "decisoes_houve_designacao_audiencia": True,
        "decisoes_autor_nao_compareceu": True,
    }
    print(f"    - Dados de teste: {dados_teste}")

    resultado = avaliar_ativacao_prompt(
        prompt_id=modulo.id,
        modo_ativacao=modulo.modo_ativacao,
        regra_deterministica=modulo.regra_deterministica,
        dados_extracao=dados_teste,
        db=db,
        regra_secundaria=modulo.regra_deterministica_secundaria,
        fallback_habilitado=modulo.fallback_habilitado,
        tipo_peca=tipo_peca
    )
    print(f"    - Resultado: {json.dumps(resultado, indent=6, ensure_ascii=False)}")

    # Simula avaliação SEM variáveis (deve mostrar erro informativo)
    print(f"\n[8] SIMULACAO avaliar_ativacao_prompt() SEM variaveis (tipo_peca='{tipo_peca}'):")
    dados_vazios = {}
    print(f"    - Dados de teste: {dados_vazios}")

    resultado_sem_vars = avaliar_ativacao_prompt(
        prompt_id=modulo.id,
        modo_ativacao=modulo.modo_ativacao,
        regra_deterministica=modulo.regra_deterministica,
        dados_extracao=dados_vazios,
        db=db,
        regra_secundaria=modulo.regra_deterministica_secundaria,
        fallback_habilitado=modulo.fallback_habilitado,
        tipo_peca=tipo_peca
    )
    print(f"    - Resultado: {json.dumps(resultado_sem_vars, indent=6, ensure_ascii=False)}")

    # Verifica se o novo campo variaveis_faltantes esta presente
    if "variaveis_faltantes" in resultado_sem_vars:
        print(f"    - [OK] Campo 'variaveis_faltantes' presente: {resultado_sem_vars['variaveis_faltantes']}")
    else:
        print(f"    - [ATENCAO] Campo 'variaveis_faltantes' NAO presente")


def main():
    db = SessionLocal()

    try:
        print("\n" + "="*80)
        print("DIAGNÓSTICO DE ATIVAÇÃO DE MÓDULOS - DEBUG")
        print("="*80)

        # Se passou nome específico, busca apenas esse
        if len(sys.argv) > 1:
            nome_modulo = sys.argv[1]
            modulo = db.query(PromptModulo).filter(
                PromptModulo.nome == nome_modulo
            ).first()

            if modulo:
                debug_modulo(db, modulo)
            else:
                print(f"\n[ERRO] Módulo '{nome_modulo}' não encontrado")
                print("\nMódulos disponíveis:")
                modulos = db.query(PromptModulo).filter(
                    PromptModulo.tipo == "conteudo",
                    PromptModulo.ativo == True
                ).all()
                for m in modulos:
                    print(f"  - {m.nome}")
        else:
            # Lista módulos com regras que deveriam ser determinísticos
            print("\nBuscando módulos de conteúdo ativos com regras determinísticas...\n")

            modulos = db.query(PromptModulo).filter(
                PromptModulo.tipo == "conteudo",
                PromptModulo.ativo == True
            ).all()

            problematicos = []

            for modulo in modulos:
                # Verifica se tem alguma regra
                tem_regra_global = bool(
                    modulo.regra_deterministica and
                    isinstance(modulo.regra_deterministica, dict) and
                    modulo.regra_deterministica.get("type")
                )

                regras_tipo = db.query(RegraDeterministicaTipoPeca).filter(
                    RegraDeterministicaTipoPeca.modulo_id == modulo.id,
                    RegraDeterministicaTipoPeca.ativo == True
                ).all()

                tem_regra_especifica = any(
                    r.regra_deterministica and
                    isinstance(r.regra_deterministica, dict) and
                    r.regra_deterministica.get("type")
                    for r in regras_tipo
                )

                # Verifica modo calculado
                modo_calc = resolve_activation_mode_from_db(
                    db=db,
                    modulo_id=modulo.id,
                    modo_ativacao_salvo=modulo.modo_ativacao,
                    regra_primaria=modulo.regra_deterministica,
                    regra_secundaria=modulo.regra_deterministica_secundaria,
                    fallback_habilitado=modulo.fallback_habilitado
                )

                # Casos problemáticos
                status = "OK"
                problema = None

                # Caso 1: Tem regra mas modo não é deterministic
                if (tem_regra_global or tem_regra_especifica) and modo_calc != "deterministic":
                    status = "PROBLEMA"
                    problema = "Tem regra mas modo não é deterministic"

                # Caso 2: Tem regra_deterministica no banco mas sem campo 'type'
                if modulo.regra_deterministica and not tem_regra_global:
                    status = "PROBLEMA"
                    problema = f"Regra global sem 'type': {type(modulo.regra_deterministica)}"

                # Caso 3: Modo é deterministic mas sem regras
                if modo_calc == "deterministic" and not (tem_regra_global or tem_regra_especifica):
                    status = "AVISO"
                    problema = "Modo deterministic mas sem regras válidas"

                if status != "OK":
                    problematicos.append({
                        "modulo": modulo,
                        "status": status,
                        "problema": problema,
                        "tem_regra_global": tem_regra_global,
                        "tem_regra_especifica": tem_regra_especifica,
                        "modo_calculado": modo_calc
                    })
                    print(f"[{status}] {modulo.nome} (ID: {modulo.id})")
                    print(f"       -> {problema}")
                    print(f"       -> Regra global: {tem_regra_global}, Específica: {tem_regra_especifica}, Modo: {modo_calc}")

            print(f"\n{'='*80}")
            print(f"RESUMO: {len(problematicos)} módulos com problemas de {len(modulos)} analisados")
            print(f"{'='*80}")

            if problematicos:
                print("\nPara debug detalhado, execute:")
                print(f"  python scripts/debug_ativacao_modulos.py <nome_modulo>")
                print("\nExemplo:")
                print(f"  python scripts/debug_ativacao_modulos.py {problematicos[0]['modulo'].nome}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
