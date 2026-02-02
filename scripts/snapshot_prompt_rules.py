#!/usr/bin/env python3
# scripts/snapshot_prompt_rules.py
"""
Script para extrair regras determinísticas do banco de produção.

Gera um snapshot local (JSON) que é usado pelos testes automatizados.
Os testes NÃO dependem do banco de produção em runtime.

Uso:
    python scripts/snapshot_prompt_rules.py

Saída:
    tests/fixtures/prompt_rules_snapshot.json
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

# Adiciona raiz do projeto ao path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_database_url() -> str:
    """
    Obtém URL do banco de dados do ambiente.

    Prioridade:
    1. DATABASE_URL_PROD (para snapshots de produção)
    2. DATABASE_URL (fallback)
    """
    # Prioriza URL de produção se definida
    url = os.getenv("DATABASE_URL_PROD") or os.getenv("DATABASE_URL")

    if not url:
        raise ValueError(
            "DATABASE_URL ou DATABASE_URL_PROD não definida no ambiente. "
            "Configure no .env ou variável de ambiente."
        )

    # Aviso se estiver usando SQLite (provavelmente é banco local)
    if "sqlite" in url.lower():
        print("AVISO: Usando banco SQLite (provavelmente local).")
        print("Para produção, defina DATABASE_URL_PROD com a URL do PostgreSQL.")
        resposta = input("Continuar mesmo assim? (s/N): ")
        if resposta.lower() != 's':
            raise ValueError("Abortado pelo usuário. Configure DATABASE_URL_PROD.")

    return url


def extrair_variaveis_regra(regra: Dict) -> Set[str]:
    """Extrai todas as variáveis usadas em uma regra AST."""
    variaveis = set()

    if not regra:
        return variaveis

    tipo = regra.get("type")

    if tipo == "condition":
        var = regra.get("variable")
        if var:
            variaveis.add(var)
    elif tipo in ("and", "or", "not"):
        for cond in regra.get("conditions", []):
            variaveis.update(extrair_variaveis_regra(cond))

    return variaveis


def analisar_estrutura_regra(regra: Dict, caminho: str = "raiz") -> Dict[str, Any]:
    """
    Analisa a estrutura de uma regra para gerar casos de teste.

    Retorna informações sobre:
    - Operadores lógicos usados (AND/OR/NOT)
    - Condições individuais
    - Profundidade de aninhamento
    - Operadores de comparação
    """
    if not regra:
        return {
            "tipo": None,
            "caminho": caminho,
            "condicoes": [],
            "operadores_logicos": [],
            "operadores_comparacao": [],
            "profundidade": 0,
            "variaveis": []
        }

    analise = {
        "tipo": regra.get("type"),
        "caminho": caminho,
        "condicoes": [],
        "operadores_logicos": [],
        "operadores_comparacao": [],
        "profundidade": 0,
        "variaveis": []
    }

    tipo = regra.get("type")

    if tipo == "condition":
        analise["condicoes"].append({
            "variable": regra.get("variable"),
            "operator": regra.get("operator"),
            "value": regra.get("value"),
            "caminho": caminho
        })
        analise["operadores_comparacao"].append(regra.get("operator"))
        analise["variaveis"].append(regra.get("variable"))

    elif tipo in ("and", "or", "not"):
        analise["operadores_logicos"].append(tipo)

        for i, cond in enumerate(regra.get("conditions", [])):
            sub_caminho = f"{caminho}.conditions[{i}]"
            sub_analise = analisar_estrutura_regra(cond, sub_caminho)

            analise["condicoes"].extend(sub_analise["condicoes"])
            analise["operadores_logicos"].extend(sub_analise["operadores_logicos"])
            analise["operadores_comparacao"].extend(sub_analise["operadores_comparacao"])
            analise["variaveis"].extend(sub_analise["variaveis"])
            analise["profundidade"] = max(
                analise["profundidade"],
                sub_analise["profundidade"] + 1
            )

    return analise


def gerar_casos_teste_regra(regra: Dict, analise: Dict) -> List[Dict[str, Any]]:
    """
    Gera casos de teste para uma regra baseado na sua estrutura.

    Estratégia:
    - Para cada condição: 1 caso positivo + 1 caso negativo
    - Para AND: caso onde todas são true, caso onde uma é false
    - Para OR: caso onde uma é true, caso onde todas são false
    - Para operadores numéricos: valores de borda
    """
    casos = []

    if not regra:
        return casos

    tipo_raiz = regra.get("type")

    if tipo_raiz == "condition":
        # Condição simples: positivo e negativo
        casos.extend(_gerar_casos_condicao_simples(regra))

    elif tipo_raiz == "and":
        # AND: todas true = true, uma false = false
        casos.extend(_gerar_casos_and(regra))

    elif tipo_raiz == "or":
        # OR: uma true = true, todas false = false
        casos.extend(_gerar_casos_or(regra))

    elif tipo_raiz == "not":
        # NOT: inverte o resultado
        casos.extend(_gerar_casos_not(regra))

    return casos


def _gerar_valor_positivo(operador: str, valor: Any) -> Any:
    """Gera um valor que satisfaz a condição."""
    if operador == "equals":
        return valor
    elif operador == "not_equals":
        if isinstance(valor, bool):
            return not valor
        elif isinstance(valor, (int, float)):
            return valor + 1
        else:
            return f"{valor}_diferente"
    elif operador == "greater_than":
        return valor + 1 if isinstance(valor, (int, float)) else valor
    elif operador == "less_than":
        return valor - 1 if isinstance(valor, (int, float)) else valor
    elif operador == "greater_or_equal":
        return valor
    elif operador == "less_or_equal":
        return valor
    elif operador == "contains":
        return f"texto com {valor} no meio"
    elif operador == "not_contains":
        return "texto sem a palavra"
    elif operador == "is_empty":
        return None
    elif operador == "is_not_empty":
        return "valor_presente"
    elif operador == "in_list":
        return valor[0] if isinstance(valor, list) and valor else valor
    elif operador == "not_in_list":
        return "valor_fora_da_lista"
    elif operador == "exists":
        return "valor_existe"
    elif operador == "not_exists":
        return None  # Variável não presente
    else:
        return valor


def _gerar_valor_negativo(operador: str, valor: Any) -> Any:
    """
    Gera um valor que NÃO satisfaz a condição.

    IMPORTANTE: Para valores booleanos, sempre usa True/False explícitos,
    nunca 0/1 (que são normalizados para False/True pelo motor).
    """
    if operador == "equals":
        if isinstance(valor, bool):
            return not valor  # True → False, False → True
        elif valor is True or str(valor).lower() == "true":
            return False  # String "true" ou True → False explícito
        elif valor is False or str(valor).lower() == "false":
            return True  # String "false" ou False → True explícito
        elif isinstance(valor, (int, float)):
            return valor + 999
        else:
            return f"{valor}_diferente"
    elif operador == "not_equals":
        return valor
    elif operador == "greater_than":
        # CORRIGIDO: não usa 0 como fallback (seria normalizado para False)
        return valor - 1 if isinstance(valor, (int, float)) else -999
    elif operador == "less_than":
        return valor + 1 if isinstance(valor, (int, float)) else 999
    elif operador == "greater_or_equal":
        # CORRIGIDO: não usa 0 como fallback
        return valor - 1 if isinstance(valor, (int, float)) else -999
    elif operador == "less_or_equal":
        return valor + 1 if isinstance(valor, (int, float)) else 999
    elif operador == "contains":
        return "texto completamente diferente"
    elif operador == "not_contains":
        return f"texto com {valor} incluso"
    elif operador == "is_empty":
        return "valor_presente"
    elif operador == "is_not_empty":
        return None
    elif operador == "in_list":
        return "valor_fora_da_lista"
    elif operador == "not_in_list":
        return valor[0] if isinstance(valor, list) and valor else valor
    elif operador == "exists":
        return None  # Variável não presente
    elif operador == "not_exists":
        return "valor_existe"
    else:
        if isinstance(valor, bool):
            return not valor
        return "valor_invalido"  # CORRIGIDO: não usa None (poderia satisfazer equals:false)


def _gerar_casos_condicao_simples(condicao: Dict) -> List[Dict]:
    """
    Gera casos de teste para uma condição simples.

    IMPORTANTE sobre caso null/ausente:
    - O motor trata variável ausente como None → normalizado para False
    - Para regras `equals: false`, variável ausente SATISFAZ a condição (False == false → True)
    - Para regras `equals: true`, variável ausente NÃO satisfaz (False == true → False)
    """
    var = condicao.get("variable")
    op = condicao.get("operator")
    val = condicao.get("value")

    casos = []

    # Caso positivo (deve ativar)
    casos.append({
        "nome": f"positivo_{var}_{op}",
        "descricao": f"Variável '{var}' satisfaz condição '{op}' com valor esperado",
        "dados": {var: _gerar_valor_positivo(op, val)},
        "esperado": True,
        "tipo_caso": "positivo"
    })

    # Caso negativo (não deve ativar)
    casos.append({
        "nome": f"negativo_{var}_{op}",
        "descricao": f"Variável '{var}' NÃO satisfaz condição '{op}'",
        "dados": {var: _gerar_valor_negativo(op, val)},
        "esperado": False,
        "tipo_caso": "negativo"
    })

    # Casos de borda para operadores numéricos
    if op in ("greater_than", "less_than", "greater_or_equal", "less_or_equal"):
        if isinstance(val, (int, float)):
            # Valor exatamente igual (borda)
            casos.append({
                "nome": f"borda_{var}_{op}_igual",
                "descricao": f"Valor de borda: exatamente {val}",
                "dados": {var: val},
                "esperado": op in ("greater_or_equal", "less_or_equal"),
                "tipo_caso": "borda"
            })

    # Caso null/ausente
    if op not in ("is_empty", "not_exists"):
        # CORRIGIDO: Determinar resultado esperado baseado na semântica da regra
        # Variável ausente → None → normalizado para False pelo motor
        # Se regra é "equals: false", então False == false → True
        # Se regra é "equals: true", então False == true → False
        esperado_null = False  # Padrão

        if op == "equals":
            # Se valor esperado é False (ou equivalente), ausente satisfaz
            if val is False or (isinstance(val, str) and val.lower() == "false"):
                esperado_null = True
        elif op == "not_equals":
            # Se valor esperado é False, ausente NÃO satisfaz (False != false → False)
            # Se valor esperado é True, ausente satisfaz (False != true → True)
            if val is True or (isinstance(val, str) and val.lower() == "true"):
                esperado_null = True
            elif val is False or (isinstance(val, str) and val.lower() == "false"):
                esperado_null = False

        casos.append({
            "nome": f"null_{var}",
            "descricao": f"Variável '{var}' é null/ausente (esperado: {'True' if esperado_null else 'False'})",
            "dados": {},  # Variável não presente
            "esperado": esperado_null,
            "tipo_caso": "null"
        })

    return casos


def _gerar_dados_para_resultado(condicao: Dict, resultado_desejado: bool) -> Dict[str, Any]:
    """
    Gera dados que fazem uma condição (simples ou composta) avaliar para o resultado desejado.

    IMPORTANTE para estruturas aninhadas:
    - Para fazer AND=True: todas as sub-condições devem ser True
    - Para fazer AND=False: basta UMA sub-condição ser False
    - Para fazer OR=True: basta UMA sub-condição ser True
    - Para fazer OR=False: todas as sub-condições devem ser False
    """
    dados = {}
    tipo = condicao.get("type")

    if tipo == "condition":
        var = condicao.get("variable")
        op = condicao.get("operator")
        val = condicao.get("value")
        if resultado_desejado:
            dados[var] = _gerar_valor_positivo(op, val)
        else:
            dados[var] = _gerar_valor_negativo(op, val)

    elif tipo == "and":
        sub_conds = condicao.get("conditions", [])
        if resultado_desejado:
            # Para AND=True: todas devem ser True
            for sub in sub_conds:
                dados.update(_gerar_dados_para_resultado(sub, True))
        else:
            # Para AND=False: basta a primeira ser False (as outras podem ser True)
            if sub_conds:
                dados.update(_gerar_dados_para_resultado(sub_conds[0], False))
                for sub in sub_conds[1:]:
                    dados.update(_gerar_dados_para_resultado(sub, True))

    elif tipo == "or":
        sub_conds = condicao.get("conditions", [])
        if resultado_desejado:
            # Para OR=True: basta a primeira ser True (as outras podem ser False)
            if sub_conds:
                dados.update(_gerar_dados_para_resultado(sub_conds[0], True))
                for sub in sub_conds[1:]:
                    dados.update(_gerar_dados_para_resultado(sub, False))
        else:
            # Para OR=False: todas devem ser False
            for sub in sub_conds:
                dados.update(_gerar_dados_para_resultado(sub, False))

    elif tipo == "not":
        sub_conds = condicao.get("conditions", [])
        if sub_conds:
            # NOT inverte o resultado
            dados.update(_gerar_dados_para_resultado(sub_conds[0], not resultado_desejado))

    return dados


def _gerar_casos_and(regra: Dict) -> List[Dict]:
    """
    Gera casos de teste para operador AND.

    CORRIGIDO: Agora lida corretamente com estruturas aninhadas (AND com OR interno, etc.)
    """
    conditions = regra.get("conditions", [])
    casos = []

    # Caso: todas as condições verdadeiras
    # Para AND=True, todas as sub-condições devem ser True
    dados_todas_true = _gerar_dados_para_resultado(regra, True)

    casos.append({
        "nome": "and_todas_true",
        "descricao": "AND: todas as condições são verdadeiras",
        "dados": dados_todas_true,
        "esperado": True,
        "tipo_caso": "positivo"
    })

    # Caso: primeira condição falsa
    if conditions:
        # Gera dados onde a primeira condição é falsa e o resto é verdadeiro
        dados_primeira_false = {}
        primeira = conditions[0]

        # Primeira condição: False (recursivamente)
        dados_primeira_false.update(_gerar_dados_para_resultado(primeira, False))

        # Resto das condições: True
        for cond in conditions[1:]:
            dados_primeira_false.update(_gerar_dados_para_resultado(cond, True))

        casos.append({
            "nome": "and_primeira_false",
            "descricao": "AND: primeira condição é falsa",
            "dados": dados_primeira_false,
            "esperado": False,
            "tipo_caso": "negativo"
        })

    # Caso: última condição falsa
    if len(conditions) > 1:
        # Gera dados onde a última condição é falsa e o resto é verdadeiro
        dados_ultima_false = {}
        ultima = conditions[-1]

        # Condições anteriores: True
        for cond in conditions[:-1]:
            dados_ultima_false.update(_gerar_dados_para_resultado(cond, True))

        # Última condição: False (recursivamente)
        dados_ultima_false.update(_gerar_dados_para_resultado(ultima, False))

        casos.append({
            "nome": "and_ultima_false",
            "descricao": "AND: última condição é falsa",
            "dados": dados_ultima_false,
            "esperado": False,
            "tipo_caso": "negativo"
        })

    return casos


def _gerar_casos_or(regra: Dict) -> List[Dict]:
    """
    Gera casos de teste para operador OR.

    CORRIGIDO: Agora lida corretamente com estruturas aninhadas (OR com AND interno, etc.)
    """
    conditions = regra.get("conditions", [])
    casos = []

    # Caso: todas falsas
    # Para OR=False, todas as sub-condições devem ser False
    dados_todas_false = _gerar_dados_para_resultado(regra, False)

    casos.append({
        "nome": "or_todas_false",
        "descricao": "OR: todas as condições são falsas",
        "dados": dados_todas_false,
        "esperado": False,
        "tipo_caso": "negativo"
    })

    # Caso: apenas primeira verdadeira
    if conditions:
        # Gera dados onde a primeira condição é verdadeira e o resto é falso
        dados_primeira_true = {}
        primeira = conditions[0]

        # Primeira condição: True (recursivamente)
        dados_primeira_true.update(_gerar_dados_para_resultado(primeira, True))

        # Resto das condições: False
        for cond in conditions[1:]:
            dados_primeira_true.update(_gerar_dados_para_resultado(cond, False))

        casos.append({
            "nome": "or_primeira_true",
            "descricao": "OR: apenas primeira condição é verdadeira",
            "dados": dados_primeira_true,
            "esperado": True,
            "tipo_caso": "positivo"
        })

    # Caso: apenas última verdadeira
    if len(conditions) > 1:
        # Gera dados onde a última condição é verdadeira e o resto é falso
        dados_ultima_true = {}
        ultima = conditions[-1]

        # Condições anteriores: False
        for cond in conditions[:-1]:
            dados_ultima_true.update(_gerar_dados_para_resultado(cond, False))

        # Última condição: True (recursivamente)
        dados_ultima_true.update(_gerar_dados_para_resultado(ultima, True))

        casos.append({
            "nome": "or_ultima_true",
            "descricao": "OR: apenas última condição é verdadeira",
            "dados": dados_ultima_true,
            "esperado": True,
            "tipo_caso": "positivo"
        })

    return casos


def _gerar_casos_not(regra: Dict) -> List[Dict]:
    """
    Gera casos de teste para operador NOT.

    CORRIGIDO: Agora lida corretamente com estruturas aninhadas.
    """
    conditions = regra.get("conditions", [])
    casos = []

    if not conditions:
        return casos

    # NOT inverte: se condição interna é true, resultado é false
    # Para NOT: queremos testar quando a condição interna é True (NOT retorna False)
    # e quando a condição interna é False (NOT retorna True)

    # Caso: condição interna True → NOT retorna False
    dados_interno_true = _gerar_dados_para_resultado(conditions[0], True)

    casos.append({
        "nome": "not_interno_true",
        "descricao": "NOT: condição interna é verdadeira (resultado = false)",
        "dados": dados_interno_true,
        "esperado": False,
        "tipo_caso": "negativo"
    })

    # Caso: condição interna False → NOT retorna True
    dados_interno_false = _gerar_dados_para_resultado(conditions[0], False)

    casos.append({
        "nome": "not_interno_false",
        "descricao": "NOT: condição interna é falsa (resultado = true)",
        "dados": dados_interno_false,
        "esperado": True,
        "tipo_caso": "positivo"
    })

    return casos


def _extrair_condicoes_folha(regra: Dict) -> List[Dict]:
    """Extrai todas as condições folha (não aninhadas) de uma regra."""
    condicoes = []

    if regra.get("type") == "condition":
        condicoes.append(regra)
    else:
        for cond in regra.get("conditions", []):
            condicoes.extend(_extrair_condicoes_folha(cond))

    return condicoes


def extrair_regras_producao(db_url: str) -> Dict[str, Any]:
    """
    Conecta ao banco de produção e extrai todas as regras determinísticas.

    Retorna um dicionário com:
    - regras: lista de regras com metadados
    - variaveis: variáveis usadas
    - estatisticas: contagens e métricas
    - timestamp: momento da extração
    """
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Importa modelos (ordem importante para resolver dependências)
        from auth.models import User
        from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON
        from admin.models_prompt_groups import PromptGroup, PromptSubgroup
        from admin.models_prompts import PromptModulo
        from sistemas.gerador_pecas.models_extraction import ExtractionVariable

        # Busca todos os prompts com regras determinísticas VÁLIDAS
        # (modo_ativacao='deterministic' E regra_deterministica não é NULL/vazio)
        prompts_raw = db.query(PromptModulo).filter(
            PromptModulo.modo_ativacao == "deterministic"
        ).all()

        # Filtra apenas prompts com regra primária válida
        prompts = [p for p in prompts_raw if p.regra_deterministica]

        print(f"Total com modo deterministic: {len(prompts_raw)}")
        print(f"Com regra primaria valida: {len(prompts)}")
        if len(prompts_raw) > len(prompts):
            invalidos = [p.nome for p in prompts_raw if not p.regra_deterministica]
            print(f"AVISO: {len(invalidos)} prompts sem regra definida: {invalidos}")

        print(f"Encontrados {len(prompts)} prompts com regras determinísticas")

        regras = []
        todas_variaveis = set()
        operadores_usados = set()

        for prompt in prompts:
            regra_primaria = prompt.regra_deterministica
            regra_secundaria = prompt.regra_deterministica_secundaria

            # Analisa regra primária
            variaveis_primaria = extrair_variaveis_regra(regra_primaria)
            analise_primaria = analisar_estrutura_regra(regra_primaria)
            casos_teste_primaria = gerar_casos_teste_regra(regra_primaria, analise_primaria)

            todas_variaveis.update(variaveis_primaria)
            operadores_usados.update(analise_primaria.get("operadores_comparacao", []))
            operadores_usados.update(analise_primaria.get("operadores_logicos", []))

            regra_info = {
                "prompt_id": prompt.id,
                "prompt_nome": prompt.nome,
                "prompt_titulo": prompt.titulo,
                "prompt_tipo": prompt.tipo,
                "prompt_ativo": prompt.ativo,
                "group_id": prompt.group_id,
                "categoria": prompt.categoria,
                "regra_primaria": regra_primaria,
                "regra_texto_original": prompt.regra_texto_original,
                "variaveis_primaria": list(variaveis_primaria),
                "analise_primaria": analise_primaria,
                "casos_teste_primaria": casos_teste_primaria,
                "fallback_habilitado": prompt.fallback_habilitado,
            }

            # Analisa regra secundária se existir
            if regra_secundaria:
                variaveis_secundaria = extrair_variaveis_regra(regra_secundaria)
                analise_secundaria = analisar_estrutura_regra(regra_secundaria)
                casos_teste_secundaria = gerar_casos_teste_regra(regra_secundaria, analise_secundaria)

                todas_variaveis.update(variaveis_secundaria)
                operadores_usados.update(analise_secundaria.get("operadores_comparacao", []))
                operadores_usados.update(analise_secundaria.get("operadores_logicos", []))

                regra_info["regra_secundaria"] = regra_secundaria
                regra_info["regra_secundaria_texto_original"] = prompt.regra_secundaria_texto_original
                regra_info["variaveis_secundaria"] = list(variaveis_secundaria)
                regra_info["analise_secundaria"] = analise_secundaria
                regra_info["casos_teste_secundaria"] = casos_teste_secundaria

            regras.append(regra_info)

        # Busca informações das variáveis
        variaveis_info = []
        for slug in todas_variaveis:
            var = db.query(ExtractionVariable).filter(
                ExtractionVariable.slug == slug
            ).first()

            if var:
                variaveis_info.append({
                    "slug": var.slug,
                    "label": var.label,
                    "tipo": var.tipo,
                    "descricao": var.descricao,
                    "fonte": "extracao"
                })
            else:
                # Pode ser variável de sistema
                variaveis_info.append({
                    "slug": slug,
                    "label": slug.replace("_", " ").title(),
                    "tipo": "unknown",
                    "descricao": None,
                    "fonte": "sistema_ou_nao_encontrada"
                })

        # Estatísticas
        estatisticas = {
            "total_prompts_deterministicos": len(prompts),
            "total_prompts_ativos": len([p for p in prompts if p.ativo]),
            "total_variaveis_usadas": len(todas_variaveis),
            "total_operadores_usados": len(operadores_usados),
            "operadores": list(operadores_usados),
            "prompts_com_fallback": len([p for p in prompts if p.fallback_habilitado]),
            "total_casos_teste_gerados": sum(
                len(r.get("casos_teste_primaria", [])) +
                len(r.get("casos_teste_secundaria", []))
                for r in regras
            )
        }

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "versao_snapshot": "1.0",
            "regras": regras,
            "variaveis": variaveis_info,
            "estatisticas": estatisticas
        }

    finally:
        db.close()
        engine.dispose()


def salvar_snapshot(dados: Dict, caminho: Path):
    """Salva o snapshot em arquivo JSON."""
    caminho.parent.mkdir(parents=True, exist_ok=True)

    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False, default=str)

    print(f"Snapshot salvo em: {caminho}")


def gerar_relatorio_cobertura(dados: Dict, caminho_relatorio: Path):
    """Gera relatório de cobertura das regras."""
    caminho_relatorio.parent.mkdir(parents=True, exist_ok=True)

    linhas = [
        "# Relatório de Cobertura - Regras Determinísticas",
        "",
        f"**Gerado em:** {dados['timestamp']}",
        "",
        "## Estatísticas Gerais",
        "",
        f"- Total de prompts determinísticos: {dados['estatisticas']['total_prompts_deterministicos']}",
        f"- Prompts ativos: {dados['estatisticas']['total_prompts_ativos']}",
        f"- Variáveis usadas: {dados['estatisticas']['total_variaveis_usadas']}",
        f"- Prompts com fallback: {dados['estatisticas']['prompts_com_fallback']}",
        f"- Casos de teste gerados: {dados['estatisticas']['total_casos_teste_gerados']}",
        "",
        "## Operadores Utilizados",
        "",
    ]

    for op in sorted(dados['estatisticas']['operadores']):
        linhas.append(f"- `{op}`")

    linhas.extend([
        "",
        "## Cobertura por Regra",
        "",
        "| ID | Nome | Ativo | Variáveis | Casos Teste | Status |",
        "|---|---|---|---|---|---|"
    ])

    for regra in dados['regras']:
        num_casos = len(regra.get('casos_teste_primaria', []))
        if regra.get('casos_teste_secundaria'):
            num_casos += len(regra['casos_teste_secundaria'])

        # Verifica cobertura mínima (1 positivo + 1 negativo)
        casos_primaria = regra.get('casos_teste_primaria', [])
        tem_positivo = any(c['tipo_caso'] == 'positivo' for c in casos_primaria)
        tem_negativo = any(c['tipo_caso'] == 'negativo' for c in casos_primaria)

        if tem_positivo and tem_negativo:
            status = "COBERTA"
        elif tem_positivo or tem_negativo:
            status = "PARCIAL"
        else:
            status = "NAO_COBERTA"

        linhas.append(
            f"| {regra['prompt_id']} | {regra['prompt_nome'][:30]} | "
            f"{'Sim' if regra['prompt_ativo'] else 'Nao'} | "
            f"{len(regra['variaveis_primaria'])} | {num_casos} | {status} |"
        )

    linhas.extend([
        "",
        "## Detalhes das Regras",
        ""
    ])

    for regra in dados['regras']:
        linhas.extend([
            f"### Prompt {regra['prompt_id']}: {regra['prompt_nome']}",
            "",
            f"**Título:** {regra['prompt_titulo']}",
            f"**Tipo:** {regra['prompt_tipo']}",
            f"**Ativo:** {'Sim' if regra['prompt_ativo'] else 'Não'}",
            "",
            "**Regra (texto original):**",
            f"> {regra.get('regra_texto_original', 'N/A')}",
            "",
            "**Variáveis utilizadas:**",
        ])

        for var in regra['variaveis_primaria']:
            linhas.append(f"- `{var}`")

        linhas.extend([
            "",
            "**Casos de teste gerados:**",
            ""
        ])

        for caso in regra.get('casos_teste_primaria', []):
            linhas.append(f"- [{caso['tipo_caso'].upper()}] {caso['descricao']}")

        if regra.get('regra_secundaria'):
            linhas.extend([
                "",
                "**Regra secundária (fallback):**",
                f"> {regra.get('regra_secundaria_texto_original', 'N/A')}",
                ""
            ])

        linhas.append("")

    with open(caminho_relatorio, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))

    print(f"Relatório de cobertura salvo em: {caminho_relatorio}")


def main():
    """Executa a extração de regras do banco de produção."""
    print("=" * 60)
    print("SNAPSHOT DE REGRAS DETERMINÍSTICAS - PRODUÇÃO")
    print("=" * 60)
    print()

    # Obtém URL do banco
    try:
        db_url = get_database_url()
        # Não loga a URL por segurança
        print("Conectando ao banco de dados...")
    except ValueError as e:
        print(f"ERRO: {e}")
        sys.exit(1)

    # Extrai regras
    print("Extraindo regras determinísticas...")
    dados = extrair_regras_producao(db_url)

    # Caminhos de saída
    caminho_snapshot = PROJECT_ROOT / "tests" / "fixtures" / "prompt_rules_snapshot.json"
    caminho_relatorio = PROJECT_ROOT / "tests" / "reports" / "prompt_rules_coverage.md"

    # Salva snapshot
    salvar_snapshot(dados, caminho_snapshot)

    # Gera relatório
    gerar_relatorio_cobertura(dados, caminho_relatorio)

    # Resumo
    print()
    print("=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"Regras extraídas: {dados['estatisticas']['total_prompts_deterministicos']}")
    print(f"Variáveis mapeadas: {dados['estatisticas']['total_variaveis_usadas']}")
    print(f"Casos de teste gerados: {dados['estatisticas']['total_casos_teste_gerados']}")
    print()
    print("Arquivos gerados:")
    print(f"  - {caminho_snapshot}")
    print(f"  - {caminho_relatorio}")
    print()
    print("Execute os testes com:")
    print("  pytest tests/test_prompt_rules_activation.py -v")
    print()


if __name__ == "__main__":
    main()
