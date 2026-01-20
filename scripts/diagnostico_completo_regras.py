"""
Script de diagnostico COMPLETO para investigar falhas de ativacao de modulos deterministicos.

Processo de teste: 08683554520258120001
Modulo: evt_tema_1033

Este script:
1. Busca o modulo pelo nome/slug
2. Analisa a estrutura da regra (OR/AND, aninhamentos)
3. Simula avaliacao com dados reais
4. Identifica EXATAMENTE onde esta o problema
5. Sugere correcao

EXECUCAO: python scripts/diagnostico_completo_regras.py
"""

import sys
import os
import json
from typing import Dict, Any, List, Tuple, Optional, Set
from datetime import datetime

# Configura encoding para UTF-8
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal

# Importa na ordem correta para evitar erro de relacionamento
# (models_extraction referencia CategoriaResumoJSON, precisa vir antes)
from auth.models import User
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
from sistemas.gerador_pecas.models_extraction import (
    ExtractionQuestion, ExtractionModel, ExtractionVariable,
    PromptVariableUsage, PromptActivationLog
)
from admin.models_prompt_groups import PromptGroup, PromptSubgroup, PromptSubcategoria
from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca
from sistemas.gerador_pecas.services_deterministic import (
    DeterministicRuleEvaluator,
    verificar_variaveis_existem,
    pode_avaliar_regra,
    _extrair_variaveis_regra,
    avaliar_ativacao_prompt,
    resolve_activation_mode_from_db,
    tem_regras_deterministicas
)


def formatar_json(obj, indent=2):
    """Formata JSON para exibicao legivel."""
    return json.dumps(obj, indent=indent, ensure_ascii=False)


def analisar_estrutura_regra(regra: Dict, nivel: int = 0) -> Dict:
    """
    Analisa a estrutura de uma regra e retorna informacoes detalhadas.

    Returns:
        Dict com: tipo, operador_raiz, profundidade, variaveis, estrutura
    """
    if not regra:
        return {"tipo": "vazia", "variaveis": set()}

    tipo = regra.get("type")
    indent = "  " * nivel

    info = {
        "tipo": tipo,
        "nivel": nivel,
        "variaveis": set()
    }

    if tipo == "condition":
        var = regra.get("variable")
        op = regra.get("operator")
        val = regra.get("value")
        info["variaveis"].add(var)
        info["condicao"] = f"{var} {op} {val}"
        return info

    elif tipo in ("and", "or"):
        conditions = regra.get("conditions", [])
        info["num_filhos"] = len(conditions)
        info["filhos"] = []

        for c in conditions:
            filho_info = analisar_estrutura_regra(c, nivel + 1)
            info["filhos"].append(filho_info)
            info["variaveis"].update(filho_info["variaveis"])

        return info

    elif tipo == "not":
        conditions = regra.get("conditions", [])
        condition = regra.get("condition")
        if condition:
            conditions = [condition]

        info["num_filhos"] = len(conditions)
        info["filhos"] = []

        for c in conditions:
            filho_info = analisar_estrutura_regra(c, nivel + 1)
            info["filhos"].append(filho_info)
            info["variaveis"].update(filho_info["variaveis"])

        return info

    return info


def imprimir_estrutura_regra(regra: Dict, nivel: int = 0):
    """Imprime a estrutura de uma regra de forma visual."""
    if not regra:
        print("  (regra vazia)")
        return

    tipo = regra.get("type")
    indent = "  " * nivel

    if tipo == "condition":
        var = regra.get("variable")
        op = regra.get("operator")
        val = regra.get("value")
        print(f"{indent}|- CONDICAO: {var} {op} {val}")

    elif tipo in ("and", "or"):
        conditions = regra.get("conditions", [])
        cor = "[AND]" if tipo == "and" else "[OR]"
        print(f"{indent}{cor} ({len(conditions)} condicoes):")
        for i, c in enumerate(conditions):
            imprimir_estrutura_regra(c, nivel + 1)

    elif tipo == "not":
        conditions = regra.get("conditions", [])
        condition = regra.get("condition")
        if condition:
            conditions = [condition]
        print(f"{indent}[NOT]:")
        for c in conditions:
            imprimir_estrutura_regra(c, nivel + 1)


def avaliar_regra_com_detalhes(regra: Dict, dados: Dict[str, Any], nivel: int = 0) -> Tuple[bool, List[str]]:
    """
    Avalia uma regra e retorna detalhes de cada passo.

    Returns:
        Tupla (resultado, lista_de_logs)
    """
    logs = []
    avaliador = DeterministicRuleEvaluator()

    if not regra:
        return False, ["Regra vazia"]

    tipo = regra.get("type")
    indent = "  " * nivel

    if tipo == "condition":
        var = regra.get("variable")
        op = regra.get("operator")
        val = regra.get("value")

        valor_atual = dados.get(var, "<<NAO EXISTE>>")
        existe = var in dados

        # Avalia a condicao
        resultado = avaliador._avaliar_condicao(regra, dados)

        status = "[OK]" if resultado else "[X]"
        existe_str = "existe" if existe else "NAO EXISTE"

        log = f"{indent}{status} {var} {op} {val} | atual={valor_atual} ({existe_str}) -> {resultado}"
        logs.append(log)

        return resultado, logs

    elif tipo == "and":
        conditions = regra.get("conditions", [])
        logs.append(f"{indent}[AND] ({len(conditions)} condicoes):")

        resultados = []
        for c in conditions:
            res, sub_logs = avaliar_regra_com_detalhes(c, dados, nivel + 1)
            logs.extend(sub_logs)
            resultados.append(res)

        resultado_final = all(resultados) if resultados else False
        logs.append(f"{indent}   -> AND resultado: {resultado_final}")

        return resultado_final, logs

    elif tipo == "or":
        conditions = regra.get("conditions", [])
        logs.append(f"{indent}[OR] ({len(conditions)} condicoes):")

        resultados = []
        for c in conditions:
            res, sub_logs = avaliar_regra_com_detalhes(c, dados, nivel + 1)
            logs.extend(sub_logs)
            resultados.append(res)

        resultado_final = any(resultados) if resultados else False
        logs.append(f"{indent}   -> OR resultado: {resultado_final}")

        return resultado_final, logs

    elif tipo == "not":
        conditions = regra.get("conditions", [])
        condition = regra.get("condition")
        if condition:
            conditions = [condition]

        logs.append(f"{indent}[NOT]:")

        resultados = []
        for c in conditions:
            res, sub_logs = avaliar_regra_com_detalhes(c, dados, nivel + 1)
            logs.extend(sub_logs)
            resultados.append(res)

        resultado_final = not any(resultados) if resultados else True
        logs.append(f"{indent}   -> NOT resultado: {resultado_final}")

        return resultado_final, logs

    return False, [f"Tipo desconhecido: {tipo}"]


def verificar_variaveis_para_or(regra: Dict, dados: Dict[str, Any]) -> Tuple[bool, List[str], List[str]]:
    """
    Verifica variaveis para regras OR de forma inteligente.

    Para regras OR: pelo menos UMA variavel deve existir E ter potencial de ser True
    Para regras AND: TODAS variaveis devem existir

    Returns:
        Tupla (pode_avaliar, vars_existentes, vars_faltantes)
    """
    if not regra:
        return False, [], []

    tipo = regra.get("type")

    if tipo == "condition":
        var = regra.get("variable")
        if var in dados:
            return True, [var], []
        else:
            return False, [], [var]

    elif tipo == "or":
        conditions = regra.get("conditions", [])
        todas_vars_existentes = []
        todas_vars_faltantes = []
        alguma_pode_avaliar = False

        for c in conditions:
            pode, existentes, faltantes = verificar_variaveis_para_or(c, dados)
            todas_vars_existentes.extend(existentes)
            todas_vars_faltantes.extend(faltantes)
            if pode:
                alguma_pode_avaliar = True

        # Para OR: basta UMA poder ser avaliada
        return alguma_pode_avaliar, todas_vars_existentes, todas_vars_faltantes

    elif tipo == "and":
        conditions = regra.get("conditions", [])
        todas_vars_existentes = []
        todas_vars_faltantes = []
        todas_podem_avaliar = True

        for c in conditions:
            pode, existentes, faltantes = verificar_variaveis_para_or(c, dados)
            todas_vars_existentes.extend(existentes)
            todas_vars_faltantes.extend(faltantes)
            if not pode:
                todas_podem_avaliar = False

        # Para AND: TODAS devem poder ser avaliadas
        return todas_podem_avaliar, todas_vars_existentes, todas_vars_faltantes

    elif tipo == "not":
        conditions = regra.get("conditions", [])
        condition = regra.get("condition")
        if condition:
            conditions = [condition]

        # NOT e avaliavel se sua condicao interna e avaliavel
        if conditions:
            return verificar_variaveis_para_or(conditions[0], dados)
        return True, [], []

    return False, [], []


def diagnosticar_modulo(nome_ou_slug: str, dados_simulados: Dict[str, Any], tipo_peca: str = "contestacao"):
    """Executa diagnostico completo de um modulo."""
    db = SessionLocal()

    try:
        print("=" * 100)
        print(f"DIAGNOSTICO COMPLETO - MODULO: {nome_ou_slug}")
        print(f"Tipo de peca: {tipo_peca}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("=" * 100)

        # 1. BUSCA O MODULO
        print("\n" + "-" * 80)
        print("[1] BUSCANDO MODULO NO BANCO DE DADOS")
        print("-" * 80)

        modulo = db.query(PromptModulo).filter(
            PromptModulo.nome == nome_ou_slug
        ).first()

        if not modulo:
            modulo = db.query(PromptModulo).filter(
                PromptModulo.titulo.ilike(f"%{nome_ou_slug}%")
            ).first()

        if not modulo:
            modulo = db.query(PromptModulo).filter(
                PromptModulo.nome.ilike(f"%{nome_ou_slug}%")
            ).first()

        if not modulo:
            print(f"[X] MODULO NAO ENCONTRADO: {nome_ou_slug}")
            print("\nModulos deterministicos disponiveis:")
            modulos = db.query(PromptModulo).filter(
                PromptModulo.tipo == "conteudo",
                PromptModulo.modo_ativacao == "deterministic"
            ).limit(30).all()
            for m in modulos:
                print(f"  - {m.nome}: {m.titulo}")
            return

        print(f"[OK] Modulo encontrado!")
        print(f"  ID: {modulo.id}")
        print(f"  Nome (slug): {modulo.nome}")
        print(f"  Titulo: {modulo.titulo}")
        print(f"  Tipo: {modulo.tipo}")
        print(f"  Categoria: {modulo.categoria}")
        print(f"  Modo de ativacao (salvo): {modulo.modo_ativacao}")
        print(f"  Ativo: {modulo.ativo}")
        print(f"  Fallback habilitado: {modulo.fallback_habilitado}")

        # 2. VERIFICA MODO DE ATIVACAO REAL (REGRA DE OURO)
        print("\n" + "-" * 80)
        print("[2] VERIFICANDO MODO DE ATIVACAO (REGRA DE OURO)")
        print("-" * 80)

        modo_real = resolve_activation_mode_from_db(
            db=db,
            modulo_id=modulo.id,
            modo_ativacao_salvo=modulo.modo_ativacao,
            regra_primaria=modulo.regra_deterministica,
            regra_secundaria=modulo.regra_deterministica_secundaria,
            fallback_habilitado=modulo.fallback_habilitado
        )

        tem_regras = tem_regras_deterministicas(
            regra_primaria=modulo.regra_deterministica,
            regra_secundaria=modulo.regra_deterministica_secundaria,
            fallback_habilitado=modulo.fallback_habilitado
        )

        print(f"  Modo salvo no banco: {modulo.modo_ativacao}")
        print(f"  Modo REAL (apos regra de ouro): {modo_real}")
        print(f"  Tem regras deterministicas: {tem_regras}")

        if modo_real != modulo.modo_ativacao:
            print(f"  [!] INCONSISTENCIA: modo salvo != modo real!")

        # 3. ANALISA REGRA GLOBAL PRIMARIA
        print("\n" + "-" * 80)
        print("[3] REGRA GLOBAL PRIMARIA")
        print("-" * 80)

        todas_existem = True
        lista_vars = []

        if modulo.regra_deterministica:
            print("\n  Estrutura da regra:")
            imprimir_estrutura_regra(modulo.regra_deterministica)

            estrutura = analisar_estrutura_regra(modulo.regra_deterministica)
            print(f"\n  Tipo raiz: {estrutura['tipo']}")
            print(f"  Variaveis usadas: {estrutura['variaveis']}")

            print(f"\n  JSON completo:")
            print(f"  {formatar_json(modulo.regra_deterministica)}")
        else:
            print("  [X] SEM REGRA GLOBAL PRIMARIA")

        # 4. ANALISA REGRA SECUNDARIA (FALLBACK)
        print("\n" + "-" * 80)
        print("[4] REGRA GLOBAL SECUNDARIA (FALLBACK)")
        print("-" * 80)

        if modulo.regra_deterministica_secundaria:
            print("\n  Estrutura da regra secundaria:")
            imprimir_estrutura_regra(modulo.regra_deterministica_secundaria)
            print(f"\n  JSON: {formatar_json(modulo.regra_deterministica_secundaria)}")
        else:
            print("  (sem regra secundaria)")
        print(f"  Fallback habilitado: {modulo.fallback_habilitado}")

        # 5. ANALISA REGRAS ESPECIFICAS POR TIPO DE PECA
        print("\n" + "-" * 80)
        print("[5] REGRAS ESPECIFICAS POR TIPO DE PECA")
        print("-" * 80)

        regras_especificas = db.query(RegraDeterministicaTipoPeca).filter(
            RegraDeterministicaTipoPeca.modulo_id == modulo.id
        ).all()

        if regras_especificas:
            for r in regras_especificas:
                status = "[OK] ATIVA" if r.ativo else "[X] INATIVA"
                print(f"\n  Tipo: {r.tipo_peca} ({status})")
                if r.ativo:
                    imprimir_estrutura_regra(r.regra_deterministica)
        else:
            print("  (nenhuma regra especifica por tipo de peca)")

        # 6. DADOS DE ENTRADA PARA SIMULACAO
        print("\n" + "-" * 80)
        print("[6] DADOS DE ENTRADA PARA SIMULACAO")
        print("-" * 80)

        print(f"\n  Dados fornecidos ({len(dados_simulados)} variaveis):")
        for k, v in dados_simulados.items():
            print(f"    {k}: {v} ({type(v).__name__})")

        # 7. TESTE DE verificar_variaveis_existem (FUNCAO ATUAL - POSSIVEL BUG)
        print("\n" + "-" * 80)
        print("[7] TESTE: verificar_variaveis_existem (FUNCAO ATUAL)")
        print("-" * 80)

        if modulo.regra_deterministica:
            todas_existem, lista_vars = verificar_variaveis_existem(
                modulo.regra_deterministica,
                dados_simulados
            )

            print(f"\n  Resultado: todas_existem = {todas_existem}")
            print(f"  Variaveis na regra: {lista_vars}")

            print("\n  Analise por variavel:")
            for var in lista_vars:
                existe = var in dados_simulados
                valor = dados_simulados.get(var, "<<NAO EXISTE>>")
                status = "[OK]" if existe else "[X]"
                print(f"    {status} {var} = {valor}")

            if not todas_existem:
                print("\n  [!] ATENCAO: verificar_variaveis_existem retornou False!")
                print("     Isso BLOQUEIA a avaliacao da regra!")
                print("     Se a regra for OR, isso e um BUG - apenas UMA variavel precisa existir.")

        # 8. TESTE: Verificacao inteligente para OR (usando nova funcao oficial)
        print("\n" + "-" * 80)
        print("[8] TESTE: Verificacao INTELIGENTE (pode_avaliar_regra - CORRECAO)")
        print("-" * 80)

        if modulo.regra_deterministica:
            # Usa a nova funcao oficial que considera estrutura OR/AND
            pode_avaliar, vars_existentes, vars_faltantes = pode_avaliar_regra(
                modulo.regra_deterministica,
                dados_simulados
            )

            print(f"\n  Pode avaliar (nova funcao): {pode_avaliar}")
            print(f"  Variaveis existentes: {vars_existentes}")
            print(f"  Variaveis faltantes: {vars_faltantes}")

            if pode_avaliar and not todas_existem:
                print("\n  [OK] CORRECAO FUNCIONANDO!")
                print("     A nova funcao pode_avaliar_regra PERMITE a avaliacao")
                print("     mesmo que nem todas as variaveis existam (regra OR).")

        # 9. AVALIACAO DIRETA DA REGRA (ignorando verificar_variaveis_existem)
        print("\n" + "-" * 80)
        print("[9] AVALIACAO DIRETA DA REGRA (DeterministicRuleEvaluator)")
        print("-" * 80)

        if modulo.regra_deterministica:
            avaliador = DeterministicRuleEvaluator()

            print("\n  Avaliacao detalhada:")
            resultado, logs = avaliar_regra_com_detalhes(
                modulo.regra_deterministica,
                dados_simulados
            )

            for log in logs:
                print(f"  {log}")

            print(f"\n  RESULTADO FINAL DA AVALIACAO: {resultado}")

            # Compara com o resultado do avaliador oficial
            resultado_oficial = avaliador.avaliar(modulo.regra_deterministica, dados_simulados)
            print(f"  Resultado do avaliador oficial: {resultado_oficial}")

            if resultado != resultado_oficial:
                print("  [!] DIVERGENCIA entre avaliacao manual e oficial!")

        # 10. TESTE VIA avaliar_ativacao_prompt (FLUXO REAL)
        print("\n" + "-" * 80)
        print("[10] TESTE VIA avaliar_ativacao_prompt (FLUXO COMPLETO)")
        print("-" * 80)

        resultado_completo = avaliar_ativacao_prompt(
            prompt_id=modulo.id,
            modo_ativacao=modulo.modo_ativacao,
            regra_deterministica=modulo.regra_deterministica,
            dados_extracao=dados_simulados,
            db=db,
            regra_secundaria=modulo.regra_deterministica_secundaria,
            fallback_habilitado=modulo.fallback_habilitado,
            tipo_peca=tipo_peca
        )

        print(f"\n  Resultado completo:")
        print(f"  {formatar_json(resultado_completo)}")

        # 11. CONCLUSAO E DIAGNOSTICO
        print("\n" + "=" * 100)
        print("CONCLUSAO DO DIAGNOSTICO")
        print("=" * 100)

        ativar = resultado_completo.get("ativar")

        if ativar is True:
            print("\n[OK] O modulo SERIA ATIVADO corretamente.")
            print(f"  Regra usada: {resultado_completo.get('regra_usada')}")
            print(f"  Detalhes: {resultado_completo.get('detalhes')}")

        elif ativar is False:
            print("\n[X] O modulo NAO seria ativado.")
            print(f"  Regra usada: {resultado_completo.get('regra_usada')}")
            print(f"  Detalhes: {resultado_completo.get('detalhes')}")

            # Verifica se a avaliacao direta daria resultado diferente
            if modulo.regra_deterministica:
                avaliador = DeterministicRuleEvaluator()
                resultado_direto = avaliador.avaliar(modulo.regra_deterministica, dados_simulados)
                if resultado_direto:
                    print("\n  [!] INCONSISTENCIA!")
                    print("     O avaliador direto retorna TRUE, mas o fluxo completo retorna FALSE.")
                    print("     Isso indica um bug no fluxo de avaliacao!")

        else:  # ativar is None
            print("\n[!] O modulo ficou INDETERMINADO (ativar=None).")
            print(f"  Regra usada: {resultado_completo.get('regra_usada')}")
            print(f"  Detalhes: {resultado_completo.get('detalhes')}")

            # Diagnostico detalhado
            print("\n  ANALISE DA CAUSA:")

            if modulo.regra_deterministica:
                avaliador = DeterministicRuleEvaluator()
                resultado_direto = avaliador.avaliar(modulo.regra_deterministica, dados_simulados)

                print(f"  - O avaliador direto retornaria: {resultado_direto}")

                if resultado_direto:
                    print("\n  [BUG] BUG CONFIRMADO!")
                    print("     A regra DEVERIA ativar (avaliador retorna True),")
                    print("     mas o fluxo completo esta bloqueando a avaliacao!")
                    print("\n     CAUSA RAIZ PROVAVEL:")
                    print("     A funcao verificar_variaveis_existem() exige que TODAS as variaveis")
                    print("     existam nos dados, mas para regras OR isso e incorreto.")
                    print("     Para regras OR, basta UMA variavel existir e satisfazer a condicao.")
                    print("\n     SOLUCAO:")
                    print("     Modificar verificar_variaveis_existem() ou criar uma nova funcao")
                    print("     que analise a estrutura da regra (OR/AND) antes de decidir se")
                    print("     pode ou nao avaliar.")

        print("\n" + "=" * 100)

    finally:
        db.close()


def main():
    """Executa diagnostico para o modulo evt_tema_1033."""

    # Dados simulados do processo 08683554520258120001
    # NOTA: Ajuste estes dados conforme o caso real
    dados_processo = {
        "peticao_inicial_pedido_cirurgia": True,
        # Outras variaveis que podem estar no processo:
        # "decisoes_afastamento_tema_1033_stf": False,
    }

    print("\n" + "=" * 100)
    print("DIAGNOSTICO DE ATIVACAO DE MODULOS DETERMINISTICOS")
    print("Processo: 08683554520258120001")
    print("=" * 100)

    diagnosticar_modulo(
        nome_ou_slug="evt_tema_1033",
        dados_simulados=dados_processo,
        tipo_peca="contestacao"
    )


if __name__ == "__main__":
    main()

