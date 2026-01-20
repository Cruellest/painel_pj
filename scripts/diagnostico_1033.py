"""
Script de diagnóstico para investigar o bug de ativação do módulo Tema 1033 (STF).

Processo: 08703941520258120001
Variável: peticao_inicial_pedido_cirurgia = true (deveria ativar o módulo)

Este script:
1. Busca o módulo 1033 e sua regra
2. Verifica se há regra específica para contestação
3. Simula a avaliação com os dados do processo
4. Identifica a causa do bug
"""

import sys
import os
import json

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal

# Importa na ordem correta para evitar erro de relacionamento
from auth.models import User
from admin.models_prompt_groups import PromptGroup, PromptSubgroup, PromptSubcategoria
from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca
from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleEvaluator,
    verificar_variaveis_existem,
    _extrair_variaveis_regra,
    avaliar_ativacao_prompt
)


def formatar_json(obj):
    """Formata JSON para exibição legível."""
    return json.dumps(obj, indent=2, ensure_ascii=False)


def diagnosticar_modulo_1033():
    """Executa diagnóstico completo do módulo 1033."""
    db = SessionLocal()

    try:
        print("=" * 80)
        print("DIAGNÓSTICO DO BUG - MÓDULO TEMA 1033 (STF)")
        print("=" * 80)

        # 1. Busca o módulo pelo nome/título
        print("\n[1] BUSCANDO MÓDULO 1033...")
        modulo = db.query(PromptModulo).filter(
            PromptModulo.titulo.ilike("%1033%")
        ).first()

        if not modulo:
            modulo = db.query(PromptModulo).filter(
                PromptModulo.nome.ilike("%1033%")
            ).first()

        if not modulo:
            print("❌ Módulo 1033 NÃO ENCONTRADO!")
            print("\nListando todos os módulos de conteúdo com regras determinísticas:")
            modulos = db.query(PromptModulo).filter(
                PromptModulo.tipo == "conteudo",
                PromptModulo.modo_ativacao == "deterministic"
            ).all()
            for m in modulos[:20]:
                print(f"  - ID={m.id}: {m.titulo} ({m.nome})")
            return

        print(f"✓ Módulo encontrado!")
        print(f"  ID: {modulo.id}")
        print(f"  Nome: {modulo.nome}")
        print(f"  Título: {modulo.titulo}")
        print(f"  Modo de ativação: {modulo.modo_ativacao}")
        print(f"  Ativo: {modulo.ativo}")

        # 2. Analisa a regra global primária
        print("\n[2] REGRA GLOBAL PRIMÁRIA:")
        if modulo.regra_deterministica:
            print(formatar_json(modulo.regra_deterministica))

            # Extrai variáveis
            variaveis = _extrair_variaveis_regra(modulo.regra_deterministica)
            print(f"\n  Variáveis usadas na regra: {variaveis}")
        else:
            print("  ❌ SEM REGRA GLOBAL PRIMÁRIA")

        # 3. Verifica regra secundária
        print("\n[3] REGRA GLOBAL SECUNDÁRIA (FALLBACK):")
        if modulo.regra_deterministica_secundaria:
            print(formatar_json(modulo.regra_deterministica_secundaria))
        else:
            print("  (sem regra secundária)")
        print(f"  Fallback habilitado: {modulo.fallback_habilitado}")

        # 4. Verifica regras específicas por tipo de peça
        print("\n[4] REGRAS ESPECÍFICAS POR TIPO DE PEÇA:")
        regras_especificas = db.query(RegraDeterministicaTipoPeca).filter(
            RegraDeterministicaTipoPeca.modulo_id == modulo.id
        ).all()

        if regras_especificas:
            for r in regras_especificas:
                print(f"\n  Tipo: {r.tipo_peca} (ativo={r.ativo})")
                print(f"  Regra: {formatar_json(r.regra_deterministica)}")
        else:
            print("  (nenhuma regra específica)")

        # 5. Simula os dados do processo
        print("\n[5] SIMULAÇÃO COM DADOS DO PROCESSO 08703941520258120001:")

        # Dados extraídos do processo (conforme mencionado no bug report)
        dados_simulados = {
            "peticao_inicial_pedido_cirurgia": True,
            "decisoes_afastamento_tema_1033_stf": False
        }

        print(f"  Dados de entrada: {formatar_json(dados_simulados)}")

        # 6. Testa verificar_variaveis_existem
        print("\n[6] TESTE DE verificar_variaveis_existem:")
        if modulo.regra_deterministica:
            todas_existem, lista_vars = verificar_variaveis_existem(
                modulo.regra_deterministica,
                dados_simulados
            )
            print(f"  Todas existem: {todas_existem}")
            print(f"  Variáveis da regra: {lista_vars}")

            # Verifica quais variáveis faltam
            for var in lista_vars:
                existe = var in dados_simulados
                valor = dados_simulados.get(var, "<<NÃO EXISTE>>")
                status = "✓" if existe else "❌"
                print(f"    {status} {var} = {valor}")

            if not todas_existem:
                print("\n  ⚠️  PROBLEMA IDENTIFICADO!")
                print("     A função verificar_variaveis_existem exige que TODAS as variáveis")
                print("     existam, mas para regras OR apenas UMA precisa existir.")
                print("     Este é o BUG que impede a avaliação da regra!")

        # 7. Testa avaliação direta (se todas existissem)
        print("\n[7] TESTE DE AVALIAÇÃO DIRETA (ignorando verificar_variaveis_existem):")
        if modulo.regra_deterministica:
            avaliador = DeterministicRuleEvaluator()

            # Simula dados com variáveis faltantes como False
            dados_completos = dados_simulados.copy()
            for var in lista_vars:
                if var not in dados_completos:
                    dados_completos[var] = None  # Simula variável inexistente

            resultado = avaliador.avaliar(modulo.regra_deterministica, dados_completos)
            print(f"  Resultado da avaliação: {resultado}")

            # Avalia condição por condição
            print("\n  Avaliação detalhada por condição:")
            avaliar_condicoes_detalhado(modulo.regra_deterministica, dados_completos, avaliador)

        # 8. Teste completo via avaliar_ativacao_prompt
        print("\n[8] TESTE VIA avaliar_ativacao_prompt (fluxo real):")
        resultado_completo = avaliar_ativacao_prompt(
            prompt_id=modulo.id,
            modo_ativacao=modulo.modo_ativacao,
            regra_deterministica=modulo.regra_deterministica,
            dados_extracao=dados_simulados,
            db=db,
            regra_secundaria=modulo.regra_deterministica_secundaria,
            fallback_habilitado=modulo.fallback_habilitado,
            tipo_peca="contestacao"  # Tipo de peça do caso
        )

        print(f"  Resultado: {formatar_json(resultado_completo)}")

        # 9. Conclusão
        print("\n" + "=" * 80)
        print("CONCLUSÃO DO DIAGNÓSTICO:")
        print("=" * 80)

        if resultado_completo.get("ativar") is True:
            print("✓ O módulo SERIA ativado corretamente.")
        elif resultado_completo.get("ativar") is False:
            print("❌ O módulo NÃO seria ativado.")
            print(f"   Motivo: {resultado_completo.get('detalhes')}")
        else:
            print("⚠️  O módulo ficou INDETERMINADO (ativar=None).")
            print(f"   Motivo: {resultado_completo.get('detalhes')}")
            print("\n   CAUSA RAIZ PROVÁVEL:")
            print("   A função verificar_variaveis_existem() está bloqueando a avaliação")
            print("   porque NEM TODAS as variáveis da regra OR existem nos dados.")
            print("   Solução: Modificar a lógica para regras OR - avaliar mesmo quando")
            print("   apenas ALGUMAS variáveis existem.")

    finally:
        db.close()


def avaliar_condicoes_detalhado(regra, dados, avaliador, nivel=0):
    """Avalia e exibe cada condição individualmente."""
    indent = "    " * (nivel + 1)
    tipo = regra.get("type")

    if tipo == "condition":
        var = regra.get("variable")
        op = regra.get("operator")
        val = regra.get("value")
        valor_atual = dados.get(var, "<<NÃO EXISTE>>")
        resultado = avaliador._avaliar_condicao(regra, dados)
        status = "✓" if resultado else "❌"
        print(f"{indent}{status} {var} {op} {val} (atual: {valor_atual}) → {resultado}")

    elif tipo in ("and", "or"):
        conditions = regra.get("conditions", [])
        print(f"{indent}[{tipo.upper()}] ({len(conditions)} condições):")
        resultados = []
        for c in conditions:
            r = avaliar_condicoes_detalhado(c, dados, avaliador, nivel + 1)
            if r is not None:
                resultados.append(r)

        if tipo == "and":
            resultado = all(resultados) if resultados else False
        else:
            resultado = any(resultados) if resultados else False
        print(f"{indent}  → Resultado {tipo.upper()}: {resultado}")
        return resultado

    elif tipo == "not":
        conditions = regra.get("conditions", [])
        print(f"{indent}[NOT]:")
        for c in conditions:
            avaliar_condicoes_detalhado(c, dados, avaliador, nivel + 1)

    return avaliador._avaliar_no(regra, dados) if tipo == "condition" else None


if __name__ == "__main__":
    diagnosticar_modulo_1033()
