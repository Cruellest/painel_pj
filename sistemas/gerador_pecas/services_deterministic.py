# sistemas/gerador_pecas/services_deterministic.py
"""
Serviços para geração e avaliação de regras determinísticas.

Este módulo implementa:
- Geração de regras determinísticas (AST JSON) a partir de linguagem natural
- Avaliação de regras no runtime (sem LLM)
- Validação de variáveis usadas nas regras
- Sincronização do uso de variáveis em prompts
"""

import json
import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from services.gemini_service import gemini_service
from .models_extraction import ExtractionVariable, PromptVariableUsage

logger = logging.getLogger(__name__)


# Modelo obrigatório conforme especificação
GEMINI_MODEL = "gemini-3-flash-preview"


class DeterministicRuleGenerator:
    """
    Gerador de regras determinísticas usando IA.

    Converte condições em linguagem natural para AST JSON
    que pode ser avaliado sem LLM no runtime.
    """

    def __init__(self, db: Session):
        self.db = db

    async def gerar_regra(
        self,
        condicao_texto: str,
        contexto: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Gera uma regra determinística a partir de texto em linguagem natural.

        Args:
            condicao_texto: Condição em linguagem natural
            contexto: Contexto adicional (ex: tipo de peça, grupo)

        Returns:
            Dict com success, regra (AST), variaveis_usadas ou erro
        """
        try:
            # 1. Busca variáveis disponíveis para contexto
            variaveis_disponiveis = self._buscar_variaveis_disponiveis()

            # 2. Monta prompt para a IA
            prompt = self._montar_prompt_geracao(
                condicao_texto,
                variaveis_disponiveis,
                contexto
            )

            # 3. Chama o Gemini
            logger.info(f"Gerando regra determinística: '{condicao_texto[:100]}...'")

            response = await gemini_service.generate(
                prompt=prompt,
                system_prompt=self._get_system_prompt(),
                model=GEMINI_MODEL,
                temperature=0.1
            )

            if not response.success:
                logger.error(f"Erro na chamada Gemini: {response.error}")
                return {"success": False, "erro": f"Erro na IA: {response.error}"}

            # 4. Parseia a resposta JSON
            resultado = self._extrair_json_resposta(response.content)

            if not resultado:
                logger.error(f"Resposta IA não é JSON válido: {response.content[:500]}")
                return {"success": False, "erro": "A IA não retornou um JSON válido"}

            # 4.1 Verifica se IA indicou variáveis insuficientes
            if resultado.get("erro") == "variaveis_insuficientes":
                logger.info("IA indicou variáveis insuficientes para a condição")
                return {
                    "success": False,
                    "erro": "variaveis_insuficientes",
                    "mensagem": resultado.get("mensagem", "Não há variáveis suficientes para expressar esta condição"),
                    "variaveis_necessarias": resultado.get("variaveis_necessarias", [])
                }

            regra = resultado.get("regra")
            variaveis_usadas = resultado.get("variaveis_usadas", [])

            if not regra:
                return {"success": False, "erro": "Regra não encontrada na resposta"}

            # 5. Valida a regra
            validacao = self._validar_regra(regra, variaveis_disponiveis)

            if not validacao["valid"]:
                return {
                    "success": False,
                    "erro": "Regra inválida",
                    "detalhes": validacao["errors"],
                    "variaveis_faltantes": validacao.get("variaveis_faltantes", []),
                    "sugestoes_variaveis": validacao.get("sugestoes_variaveis", [])
                }

            logger.info(f"Regra gerada com sucesso: {len(variaveis_usadas)} variáveis usadas")

            return {
                "success": True,
                "regra": regra,
                "variaveis_usadas": variaveis_usadas,
                "regra_texto_original": condicao_texto
            }

        except Exception as e:
            logger.exception(f"Erro ao gerar regra: {e}")
            return {"success": False, "erro": str(e)}

    def _get_system_prompt(self) -> str:
        """Retorna o prompt de sistema para geração de regras."""
        return """Você é um especialista em converter condições em linguagem natural para regras estruturadas (AST JSON).

Sua tarefa é converter uma condição textual em uma estrutura JSON que pode ser avaliada programaticamente.

OPERADORES DISPONÍVEIS:
- "equals": Igualdade exata
- "not_equals": Diferente de
- "contains": Contém texto (case insensitive)
- "not_contains": Não contém texto
- "starts_with": Começa com
- "ends_with": Termina com
- "greater_than": Maior que (números)
- "less_than": Menor que (números)
- "greater_or_equal": Maior ou igual
- "less_or_equal": Menor ou igual
- "is_empty": Está vazio/nulo
- "is_not_empty": Não está vazio
- "in_list": Está na lista
- "not_in_list": Não está na lista
- "matches_regex": Corresponde ao regex
- "exists": Variável existe e foi extraída (útil para variáveis condicionais)
- "not_exists": Variável não existe ou não foi extraída

OPERADORES LÓGICOS:
- "and": Todas as condições devem ser verdadeiras
- "or": Pelo menos uma condição deve ser verdadeira
- "not": Negação

FORMATO DA REGRA (AST JSON):
{
    "type": "condition" | "and" | "or" | "not",
    "variable": "nome_variavel",  // apenas para type=condition
    "operator": "equals" | "contains" | etc,  // apenas para type=condition
    "value": "valor_comparacao",  // apenas para type=condition
    "conditions": [...]  // para and/or/not
}

EXEMPLOS:

1. "O valor da causa é maior que 100000"
{
    "type": "condition",
    "variable": "valor_causa",
    "operator": "greater_than",
    "value": 100000
}

2. "O autor é idoso ou hipossuficiente"
{
    "type": "or",
    "conditions": [
        {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": true},
        {"type": "condition", "variable": "autor_hipossuficiente", "operator": "equals", "value": true}
    ]
}

3. "O medicamento é de alto custo e não está na lista RENAME"
{
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "medicamento_alto_custo", "operator": "equals", "value": true},
        {"type": "condition", "variable": "medicamento_rename", "operator": "equals", "value": false}
    ]
}

4. "Quando for pleiteado medicamento e ele for não incorporado ao SUS ou não incorporado para patologia" (agrupamento lógico)
{
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "pleiteado_medicamento", "operator": "equals", "value": true},
        {
            "type": "or",
            "conditions": [
                {"type": "condition", "variable": "nao_incorporado_sus", "operator": "equals", "value": true},
                {"type": "condition", "variable": "nao_incorporado_patologia", "operator": "equals", "value": true}
            ]
        }
    ]
}

5. "O autor é idoso ou (o valor é alto e urgente)" (agrupamento com OR externo)
{
    "type": "or",
    "conditions": [
        {"type": "condition", "variable": "autor_idoso", "operator": "equals", "value": true},
        {
            "type": "and",
            "conditions": [
                {"type": "condition", "variable": "valor_alto", "operator": "equals", "value": true},
                {"type": "condition", "variable": "urgente", "operator": "equals", "value": true}
            ]
        }
    ]
}

FORMATO DE RESPOSTA (JSON estrito):

CASO 1 - Se existirem variáveis suficientes para expressar a condição:
{
    "regra": { ... AST conforme exemplos acima ... },
    "variaveis_usadas": ["var1", "var2"]
}

CASO 2 - Se NÃO existirem variáveis suficientes (OBRIGATÓRIO preencher todos os campos):
{
    "erro": "variaveis_insuficientes",
    "mensagem": "Explique detalhadamente quais variáveis estão faltando e por quê. Ex: 'Para expressar esta condição, seriam necessárias variáveis que identifiquem se foi pleiteada cirurgia e se o laudo médico é de especialista do SUS, mas essas variáveis não existem no sistema.'",
    "variaveis_necessarias": [
        {
            "slug_sugerido": "nome_em_snake_case",
            "descricao": "Descrição clara e completa do que essa variável representa",
            "tipo_sugerido": "boolean"
        }
    ]
}

REGRAS CRÍTICAS:
1. Use APENAS variáveis que existem na lista fornecida
2. Se não houver variáveis suficientes, SEMPRE retorne CASO 2 com TODOS os campos preenchidos
3. No CASO 2, liste TODAS as variáveis que precisariam ser criadas para atender a condição
4. A "mensagem" deve ser explicativa para o usuário entender o problema
5. Retorne APENAS JSON válido, sem texto adicional
6. Variáveis devem estar em snake_case"""

    def _buscar_variaveis_disponiveis(self) -> List[Dict]:
        """Busca todas as variáveis disponíveis no sistema."""
        variaveis = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.ativo == True
        ).all()

        return [
            {
                "slug": v.slug,
                "label": v.label,
                "tipo": v.tipo,
                "descricao": v.descricao,
                "opcoes": v.opcoes
            }
            for v in variaveis
        ]

    def _montar_prompt_geracao(
        self,
        condicao_texto: str,
        variaveis: List[Dict],
        contexto: Optional[str] = None
    ) -> str:
        """Monta o prompt para geração da regra."""
        variaveis_formatadas = []
        for v in variaveis:
            info = f"- {v['slug']}: {v['label']} (tipo: {v['tipo']})"
            if v.get('descricao'):
                info += f" - {v['descricao']}"
            if v.get('opcoes'):
                info += f" [opções: {', '.join(v['opcoes'])}]"
            variaveis_formatadas.append(info)

        prompt = f"""Converta a seguinte condição em linguagem natural para uma regra determinística (AST JSON):

CONDIÇÃO: {condicao_texto}
"""

        if contexto:
            prompt += f"\nCONTEXTO: {contexto}\n"

        prompt += f"""
VARIÁVEIS DISPONÍVEIS:
{chr(10).join(variaveis_formatadas) if variaveis_formatadas else "(nenhuma variável cadastrada)"}

INSTRUÇÕES:
1. Use APENAS variáveis da lista acima
2. Se a condição menciona algo que não existe nas variáveis, use a mais próxima ou retorne erro
3. Retorne APENAS o JSON, sem explicações"""

        return prompt

    def _extrair_json_resposta(self, resposta: str) -> Optional[Dict]:
        """Extrai JSON da resposta da IA."""
        resposta = resposta.strip()

        # Remove marcadores de código
        if resposta.startswith("```json"):
            resposta = resposta[7:]
        elif resposta.startswith("```"):
            resposta = resposta[3:]

        if resposta.endswith("```"):
            resposta = resposta[:-3]

        resposta = resposta.strip()

        try:
            return json.loads(resposta)
        except json.JSONDecodeError:
            # Tenta encontrar JSON
            match = re.search(r'\{[\s\S]*\}', resposta)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return None

    def _inferir_tipo_variavel(self, slug: str) -> str:
        """
        Infere o tipo de uma variável baseado no seu nome (slug).

        Usado para sugerir o tipo quando a variável não existe no sistema.

        Args:
            slug: Nome da variável em snake_case

        Returns:
            Tipo sugerido: text, boolean, number, currency, date
        """
        slug_lower = slug.lower()

        # Palavras-chave para valores monetários
        if any(x in slug_lower for x in ["valor", "custo", "preco", "montante", "total"]):
            return "currency"

        # Palavras-chave para datas
        if any(x in slug_lower for x in ["data", "date", "dia", "nascimento", "vencimento"]):
            return "date"

        # Palavras-chave para booleanos
        if any(x in slug_lower for x in [
            "idoso", "ativo", "possui", "tem_", "eh_", "e_", "is_",
            "sim_nao", "aprovado", "deferido", "urgente", "prioritario",
            "incorporado", "registrado", "valido", "existente"
        ]):
            return "boolean"

        # Palavras-chave para números
        if any(x in slug_lower for x in [
            "quantidade", "numero", "qtd", "num_", "count", "total_",
            "idade", "prazo", "dias", "meses", "anos"
        ]):
            return "number"

        # Default: texto
        return "text"

    def _validar_regra(
        self,
        regra: Dict,
        variaveis_disponiveis: List[Dict]
    ) -> Dict[str, Any]:
        """Valida a regra gerada."""
        erros = []
        variaveis_faltantes = []
        slugs_disponiveis = {v["slug"] for v in variaveis_disponiveis}

        def validar_no(no: Dict, caminho: str = ""):
            tipo = no.get("type")

            if not tipo:
                erros.append(f"{caminho}: falta 'type'")
                return

            if tipo == "condition":
                # Valida condição simples
                var = no.get("variable")
                if not var:
                    erros.append(f"{caminho}: falta 'variable'")
                elif var not in slugs_disponiveis:
                    variaveis_faltantes.append(var)
                    erros.append(f"{caminho}: variável '{var}' não existe")

                if not no.get("operator"):
                    erros.append(f"{caminho}: falta 'operator'")

            elif tipo in ("and", "or"):
                # Valida operadores lógicos
                conditions = no.get("conditions", [])
                if not conditions:
                    erros.append(f"{caminho}: '{tipo}' precisa de 'conditions'")
                else:
                    for i, cond in enumerate(conditions):
                        validar_no(cond, f"{caminho}.conditions[{i}]")

            elif tipo == "not":
                # Valida negação
                conditions = no.get("conditions", [])
                if not conditions:
                    erros.append(f"{caminho}: 'not' precisa de 'conditions'")
                else:
                    for i, cond in enumerate(conditions):
                        validar_no(cond, f"{caminho}.conditions[{i}]")

            else:
                erros.append(f"{caminho}: tipo '{tipo}' desconhecido")

        validar_no(regra, "raiz")

        # Gera sugestões para variáveis faltantes
        variaveis_faltantes_unicas = list(set(variaveis_faltantes))
        sugestoes_variaveis = []

        for var in variaveis_faltantes_unicas:
            sugestoes_variaveis.append({
                "slug": var,
                "label_sugerido": var.replace("_", " ").title(),
                "tipo_sugerido": self._inferir_tipo_variavel(var)
            })

        return {
            "valid": len(erros) == 0,
            "errors": erros,
            "variaveis_faltantes": variaveis_faltantes_unicas,
            "sugestoes_variaveis": sugestoes_variaveis
        }


class DeterministicRuleEvaluator:
    """
    Avaliador de regras determinísticas no runtime.

    Executa regras AST JSON sem chamar LLM.
    Suporta variáveis condicionais que podem estar ausentes.
    """

    # Marcador para variáveis não aplicáveis
    NOT_APPLICABLE = "__NOT_APPLICABLE__"

    def __init__(self):
        pass

    def preprocessar_dados_condicionais(
        self,
        dados: Dict[str, Any],
        variaveis_condicionais: List[Dict]
    ) -> Dict[str, Any]:
        """
        Pré-processa dados marcando variáveis condicionais como não aplicáveis
        quando suas condições não são satisfeitas.

        Args:
            dados: Dicionário com valores extraídos
            variaveis_condicionais: Lista de dicts com {slug, depends_on, operator, value}

        Returns:
            Dados processados com variáveis não aplicáveis marcadas
        """
        dados_processados = dados.copy()

        for var in variaveis_condicionais:
            slug = var.get("slug")
            depends_on = var.get("depends_on")
            operator = var.get("operator", "equals")
            value = var.get("value")

            if not slug or not depends_on:
                continue

            # Avalia se a condição da variável é satisfeita
            condicao_satisfeita = self._avaliar_condicao_dependencia(
                depends_on, operator, value, dados_processados
            )

            if not condicao_satisfeita:
                # Marca variável como não aplicável
                dados_processados[slug] = self.NOT_APPLICABLE

        return dados_processados

    def _avaliar_condicao_dependencia(
        self,
        depends_on: str,
        operator: str,
        value: Any,
        dados: Dict[str, Any]
    ) -> bool:
        """Avalia se uma condição de dependência é satisfeita."""
        valor_pai = dados.get(depends_on)

        # Se pai não existe, condição não é satisfeita
        if valor_pai is None:
            return False

        # Se pai é não aplicável, condição não é satisfeita
        if valor_pai == self.NOT_APPLICABLE:
            return False

        # Avalia operador
        if operator == "exists":
            return True  # Já verificamos que pai existe

        if operator == "not_exists":
            return False  # Já verificamos que pai existe

        if operator == "equals":
            return self._comparar_igual(valor_pai, value)

        if operator == "not_equals":
            return not self._comparar_igual(valor_pai, value)

        if operator == "in_list":
            if not isinstance(value, list):
                value = [value]
            return valor_pai in value

        if operator == "not_in_list":
            if not isinstance(value, list):
                value = [value]
            return valor_pai not in value

        if operator == "greater_than":
            return self._comparar_numerico(valor_pai, value, ">")

        if operator == "less_than":
            return self._comparar_numerico(valor_pai, value, "<")

        # Operador desconhecido = assume verdadeiro
        return True

    def avaliar(self, regra: Dict, dados: Dict[str, Any]) -> bool:
        """
        Avalia uma regra determinística com os dados fornecidos.

        Args:
            regra: AST JSON da regra
            dados: Dicionário com valores das variáveis

        Returns:
            True se a regra é satisfeita, False caso contrário
        """
        try:
            return self._avaliar_no(regra, dados)
        except Exception as e:
            logger.error(f"Erro ao avaliar regra: {e}")
            return False

    def _avaliar_no(self, no: Dict, dados: Dict[str, Any]) -> bool:
        """Avalia um nó da árvore de regras."""
        tipo = no.get("type")

        if tipo == "condition":
            return self._avaliar_condicao(no, dados)

        elif tipo == "and":
            conditions = no.get("conditions", [])
            return all(self._avaliar_no(c, dados) for c in conditions)

        elif tipo == "or":
            conditions = no.get("conditions", [])
            return any(self._avaliar_no(c, dados) for c in conditions)

        elif tipo == "not":
            # Aceita tanto 'condition' (singular) quanto 'conditions' (plural)
            condition = no.get("condition")
            if condition:
                return not self._avaliar_no(condition, dados)
            conditions = no.get("conditions", [])
            # NOT é verdadeiro se NENHUMA condição for verdadeira
            return not any(self._avaliar_no(c, dados) for c in conditions)

        else:
            logger.warning(f"Tipo de nó desconhecido: {tipo}")
            return False

    def _avaliar_condicao(self, condicao: Dict, dados: Dict[str, Any]) -> bool:
        """
        Avalia uma condição simples.

        Suporta variáveis condicionais que podem estar ausentes quando
        sua condição pai não é satisfeita.
        """
        variavel = condicao.get("variable")
        operador = condicao.get("operator")
        valor_esperado = condicao.get("value")

        # Obtém valor atual da variável
        valor_atual = dados.get(variavel)

        # Tratamento especial para variáveis condicionais ausentes
        # Se a variável não existe e o operador não é exists/not_exists,
        # tratamos como condição não satisfeita (exceto para is_empty)
        if valor_atual is None and operador not in ("exists", "not_exists", "is_empty", "is_not_empty"):
            # Verifica se é uma variável marcada como não aplicável
            if variavel in dados and dados[variavel] == "__NOT_APPLICABLE__":
                # Variável é condicional e sua condição pai não foi satisfeita
                # Para operadores de comparação, retorna False
                return False

        # Avalia operador
        return self._aplicar_operador(operador, valor_atual, valor_esperado)

    def _aplicar_operador(
        self,
        operador: str,
        valor_atual: Any,
        valor_esperado: Any
    ) -> bool:
        """Aplica um operador de comparação."""
        if operador == "equals":
            return self._comparar_igual(valor_atual, valor_esperado)

        elif operador == "not_equals":
            return not self._comparar_igual(valor_atual, valor_esperado)

        elif operador == "contains":
            if valor_atual is None:
                return False
            return str(valor_esperado).lower() in str(valor_atual).lower()

        elif operador == "not_contains":
            if valor_atual is None:
                return True
            return str(valor_esperado).lower() not in str(valor_atual).lower()

        elif operador == "starts_with":
            if valor_atual is None:
                return False
            return str(valor_atual).lower().startswith(str(valor_esperado).lower())

        elif operador == "ends_with":
            if valor_atual is None:
                return False
            return str(valor_atual).lower().endswith(str(valor_esperado).lower())

        elif operador == "greater_than":
            return self._comparar_numerico(valor_atual, valor_esperado, ">")

        elif operador == "less_than":
            return self._comparar_numerico(valor_atual, valor_esperado, "<")

        elif operador == "greater_or_equal":
            return self._comparar_numerico(valor_atual, valor_esperado, ">=")

        elif operador == "less_or_equal":
            return self._comparar_numerico(valor_atual, valor_esperado, "<=")

        elif operador == "is_empty":
            return valor_atual is None or valor_atual == "" or valor_atual == []

        elif operador == "is_not_empty":
            return valor_atual is not None and valor_atual != "" and valor_atual != []

        elif operador == "in_list":
            if not isinstance(valor_esperado, list):
                valor_esperado = [valor_esperado]
            return valor_atual in valor_esperado

        elif operador == "not_in_list":
            if not isinstance(valor_esperado, list):
                valor_esperado = [valor_esperado]
            return valor_atual not in valor_esperado

        elif operador == "matches_regex":
            if valor_atual is None:
                return False
            try:
                return bool(re.match(valor_esperado, str(valor_atual), re.IGNORECASE))
            except re.error:
                return False

        elif operador == "exists":
            # Variável existe e foi extraída (não é None nem marcada como não aplicável)
            return valor_atual is not None and valor_atual != "__NOT_APPLICABLE__"

        elif operador == "not_exists":
            # Variável não existe, não foi extraída, ou é não aplicável
            return valor_atual is None or valor_atual == "__NOT_APPLICABLE__"

        else:
            logger.warning(f"Operador desconhecido: {operador}")
            return False

    def _comparar_igual(self, a: Any, b: Any) -> bool:
        """Compara igualdade com normalização."""
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False

        # Normaliza strings
        if isinstance(a, str) and isinstance(b, str):
            return a.lower().strip() == b.lower().strip()

        # Normaliza booleanos
        if isinstance(b, bool):
            if isinstance(a, str):
                return a.lower() in ("true", "sim", "yes", "1") if b else a.lower() in ("false", "não", "nao", "no", "0")

        return a == b

    def _parse_numero(self, valor: str) -> float:
        """
        Converte string para número, suportando formato brasileiro.

        Exemplos suportados:
        - "250000" -> 250000.0
        - "250.000,00" -> 250000.0
        - "R$ 250.000,00" -> 250000.0
        - "250,50" -> 250.5
        """
        # Remove símbolos de moeda e espaços
        valor = valor.replace("R$", "").replace("$", "").strip()

        # Detecta formato brasileiro (ponto como separador de milhar, vírgula como decimal)
        # Se tem ponto E vírgula, assume formato brasileiro
        if "." in valor and "," in valor:
            # Remove pontos (milhares) e substitui vírgula por ponto (decimal)
            valor = valor.replace(".", "").replace(",", ".")
        elif "," in valor and "." not in valor:
            # Apenas vírgula: pode ser decimal brasileiro
            # Se tem mais de 2 dígitos após a vírgula, provavelmente é milhar
            partes = valor.split(",")
            if len(partes) == 2 and len(partes[1]) <= 2:
                # Vírgula como decimal
                valor = valor.replace(",", ".")
            else:
                # Vírgula como milhar
                valor = valor.replace(",", "")

        return float(valor)

    def _comparar_numerico(self, a: Any, b: Any, op: str) -> bool:
        """Compara valores numéricos."""
        try:
            # Converte para float (suporta formato brasileiro: R$ 250.000,00)
            if isinstance(a, str):
                a = self._parse_numero(a)
            if isinstance(b, str):
                b = self._parse_numero(b)

            a = float(a) if a is not None else 0
            b = float(b) if b is not None else 0

            if op == ">":
                return a > b
            elif op == "<":
                return a < b
            elif op == ">=":
                return a >= b
            elif op == "<=":
                return a <= b

        except (ValueError, TypeError):
            return False

        return False


class PromptVariableUsageSync:
    """
    Sincronizador de uso de variáveis em prompts.

    Atualiza automaticamente a tabela de uso quando regras são modificadas.
    """

    def __init__(self, db: Session):
        self.db = db

    def atualizar_uso(
        self,
        prompt_id: int,
        regra: Optional[Dict],
        regra_secundaria: Optional[Dict] = None
    ) -> List[str]:
        """
        Atualiza o registro de variáveis usadas por um prompt.

        Args:
            prompt_id: ID do prompt
            regra: AST JSON da regra PRIMÁRIA (ou None se modo LLM)
            regra_secundaria: AST JSON da regra SECUNDÁRIA/fallback (opcional)

        Returns:
            Lista de slugs de variáveis usadas (primária + secundária)
        """
        # Remove registros anteriores
        self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.prompt_id == prompt_id
        ).delete()

        variaveis = set()

        # Extrai variáveis da regra primária
        if regra:
            variaveis.update(self._extrair_variaveis(regra))

        # Extrai variáveis da regra secundária
        if regra_secundaria:
            variaveis.update(self._extrair_variaveis(regra_secundaria))

        if not variaveis:
            self.db.commit()
            return []

        # Cria novos registros
        for slug in variaveis:
            uso = PromptVariableUsage(
                prompt_id=prompt_id,
                variable_slug=slug
            )
            self.db.add(uso)

        self.db.commit()
        return list(variaveis)

    def _extrair_variaveis(self, no: Dict, variaveis: Set[str] = None) -> Set[str]:
        """Extrai todas as variáveis usadas em uma regra."""
        if variaveis is None:
            variaveis = set()

        tipo = no.get("type")

        if tipo == "condition":
            var = no.get("variable")
            if var:
                variaveis.add(var)

        elif tipo in ("and", "or", "not"):
            for cond in no.get("conditions", []):
                self._extrair_variaveis(cond, variaveis)

        return variaveis

    def obter_prompts_por_variavel(self, variable_slug: str) -> List[Dict]:
        """
        Retorna todos os prompts que usam uma variável específica.
        """
        from admin.models_prompts import PromptModulo

        usos = self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.variable_slug == variable_slug
        ).all()

        prompt_ids = [u.prompt_id for u in usos]

        if not prompt_ids:
            return []

        prompts = self.db.query(PromptModulo).filter(
            PromptModulo.id.in_(prompt_ids)
        ).all()

        return [
            {
                "id": p.id,
                "nome": p.nome,
                "titulo": p.titulo,
                "tipo": p.tipo,
                "modo_ativacao": p.modo_ativacao,
                "ativo": p.ativo
            }
            for p in prompts
        ]


def verificar_variaveis_existem(regra: Dict, dados: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Verifica se TODAS as variáveis usadas na regra EXISTEM nos dados.

    IMPORTANTE: Distingue entre:
    - Variável inexistente (chave não presente no dict) -> retorna False
    - Variável existente com valor False/None -> retorna True

    Args:
        regra: AST JSON da regra
        dados: Dicionário com dados extraídos

    Returns:
        Tupla (todas_existem, lista_variaveis_usadas)
    """
    variaveis = _extrair_variaveis_regra(regra)
    todas_existem = all(var in dados for var in variaveis)
    return todas_existem, list(variaveis)


def avaliar_ativacao_prompt(
    prompt_id: int,
    modo_ativacao: str,
    regra_deterministica: Optional[Dict],
    dados_extracao: Dict[str, Any],
    db: Session,
    regra_secundaria: Optional[Dict] = None,
    fallback_habilitado: bool = False
) -> Dict[str, Any]:
    """
    Função de conveniência para avaliar se um prompt deve ser ativado.

    Suporta regra primária e secundária (fallback controlado):
    1. Se regra primária existe:
       - Verifica se as variáveis da primária EXISTEM nos dados
       - Se existem: avalia primária (prevalece mesmo se false/null)
       - Se NÃO existem: avalia secundária (se habilitada)
    2. Secundária NUNCA sobrepõe primária

    Args:
        prompt_id: ID do prompt
        modo_ativacao: 'llm' ou 'deterministic'
        regra_deterministica: AST JSON da regra PRIMÁRIA (se modo deterministic)
        dados_extracao: Dados extraídos do processo
        db: Sessão do banco
        regra_secundaria: AST JSON da regra SECUNDÁRIA/fallback (opcional)
        fallback_habilitado: Se deve avaliar regra secundária quando primária não existe

    Returns:
        Dict com ativar, modo, detalhes, regra_usada
    """
    if modo_ativacao == "deterministic" and regra_deterministica:
        avaliador = DeterministicRuleEvaluator()

        # 1. Verifica se variáveis da regra primária EXISTEM nos dados
        variaveis_primaria_existem, vars_primaria = verificar_variaveis_existem(
            regra_deterministica, dados_extracao
        )

        logger.info(
            f"[DETERMINISTIC] Prompt {prompt_id}: "
            f"variáveis primária existem={variaveis_primaria_existem}, "
            f"vars={vars_primaria}"
        )

        # 2. Se variáveis da primária EXISTEM -> avalia primária (encerra decisão)
        if variaveis_primaria_existem:
            resultado = avaliador.avaliar(regra_deterministica, dados_extracao)

            logger.info(
                f"[DETERMINISTIC] Prompt {prompt_id}: "
                f"regra PRIMÁRIA avaliada = {resultado}"
            )

            _registrar_log_ativacao(
                db=db,
                prompt_id=prompt_id,
                modo="deterministic_primary",
                resultado=resultado,
                variaveis_usadas=vars_primaria
            )

            return {
                "ativar": resultado,
                "modo": "deterministic",
                "regra_usada": "primaria",
                "detalhes": f"Avaliado por regra primária (variáveis existem: {vars_primaria})"
            }

        # 3. Se variáveis da primária NÃO EXISTEM -> tenta secundária (se habilitada)
        if fallback_habilitado and regra_secundaria:
            variaveis_secundaria_existem, vars_secundaria = verificar_variaveis_existem(
                regra_secundaria, dados_extracao
            )

            logger.info(
                f"[DETERMINISTIC] Prompt {prompt_id}: "
                f"FALLBACK para secundária, vars existem={variaveis_secundaria_existem}, "
                f"vars={vars_secundaria}"
            )

            if variaveis_secundaria_existem:
                resultado = avaliador.avaliar(regra_secundaria, dados_extracao)

                logger.info(
                    f"[DETERMINISTIC] Prompt {prompt_id}: "
                    f"regra SECUNDÁRIA avaliada = {resultado}"
                )

                _registrar_log_ativacao(
                    db=db,
                    prompt_id=prompt_id,
                    modo="deterministic_secondary",
                    resultado=resultado,
                    variaveis_usadas=vars_secundaria
                )

                return {
                    "ativar": resultado,
                    "modo": "deterministic",
                    "regra_usada": "secundaria",
                    "detalhes": f"Avaliado por regra secundária/fallback (primária inexistente: {vars_primaria})"
                }
            else:
                # Nem primária nem secundária têm variáveis disponíveis
                logger.warning(
                    f"[DETERMINISTIC] Prompt {prompt_id}: "
                    f"NEM primária NEM secundária têm variáveis disponíveis"
                )

                return {
                    "ativar": None,  # Indeterminado - não é possível avaliar
                    "modo": "deterministic",
                    "regra_usada": "nenhuma",
                    "detalhes": f"Nenhuma regra aplicável - variáveis inexistentes (primária: {vars_primaria}, secundária: {vars_secundaria})"
                }

        # 4. Variáveis da primária não existem e não há secundária/fallback
        logger.info(
            f"[DETERMINISTIC] Prompt {prompt_id}: "
            f"regra primária INAPLICÁVEL (vars não existem), sem fallback"
        )

        return {
            "ativar": None,  # Indeterminado - não é possível avaliar
            "modo": "deterministic",
            "regra_usada": "nenhuma",
            "detalhes": f"Regra primária inaplicável (variáveis inexistentes: {vars_primaria}), fallback desabilitado"
        }

    else:
        # Modo LLM - retorna None para indicar que precisa chamar LLM
        return {
            "ativar": None,
            "modo": "llm",
            "regra_usada": None,
            "detalhes": "Requer avaliação por LLM"
        }


def _extrair_variaveis_regra(no: Dict) -> Set[str]:
    """Helper para extrair variáveis de uma regra."""
    variaveis = set()
    tipo = no.get("type")

    if tipo == "condition":
        var = no.get("variable")
        if var:
            variaveis.add(var)
    elif tipo in ("and", "or", "not"):
        for cond in no.get("conditions", []):
            variaveis.update(_extrair_variaveis_regra(cond))

    return variaveis


def _registrar_log_ativacao(
    db: Session,
    prompt_id: int,
    modo: str,
    resultado: bool,
    variaveis_usadas: List[str]
):
    """Registra log de ativação de prompt."""
    from .models_extraction import PromptActivationLog

    log = PromptActivationLog(
        prompt_id=prompt_id,
        modo_ativacao=modo,
        resultado=resultado,
        variaveis_usadas=variaveis_usadas
    )
    db.add(log)
    db.commit()
