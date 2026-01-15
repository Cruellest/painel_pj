# sistemas/gerador_pecas/services_dependencies.py
"""
Serviços para gerenciamento de dependências entre perguntas/variáveis.

Este módulo implementa:
- Inferência de dependências via IA (Gemini)
- Validação de dependências
- Avaliação de visibilidade condicional
- Construção de grafo de dependências
"""

import json
import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from services.gemini_service import gemini_service
from .models_extraction import (
    ExtractionQuestion, ExtractionVariable, DependencyOperator
)

logger = logging.getLogger(__name__)

# Modelo obrigatório conforme especificação
GEMINI_MODEL = "gemini-3-flash-preview"


class DependencyInferenceService:
    """
    Serviço para inferir dependências entre perguntas via IA.

    Analisa o texto das perguntas e sugere quais perguntas
    dependem de quais variáveis.
    """

    def __init__(self, db: Session):
        self.db = db

    async def inferir_dependencias(
        self,
        categoria_id: int,
        perguntas: Optional[List[ExtractionQuestion]] = None
    ) -> Dict[str, Any]:
        """
        Infere dependências entre perguntas de uma categoria.

        Args:
            categoria_id: ID da categoria
            perguntas: Lista de perguntas (opcional, busca do BD se não fornecido)

        Returns:
            Dict com success, dependencias_inferidas, grafo
        """
        try:
            # Busca perguntas se não fornecidas
            if perguntas is None:
                perguntas = self.db.query(ExtractionQuestion).filter(
                    ExtractionQuestion.categoria_id == categoria_id,
                    ExtractionQuestion.ativo == True
                ).order_by(ExtractionQuestion.ordem).all()

            if not perguntas:
                return {"success": True, "dependencias_inferidas": [], "grafo": {}}

            # Busca variáveis existentes para contexto
            variaveis = self.db.query(ExtractionVariable).filter(
                ExtractionVariable.categoria_id == categoria_id,
                ExtractionVariable.ativo == True
            ).all()

            # Monta prompt para IA
            prompt = self._montar_prompt_inferencia(perguntas, variaveis)

            # Chama Gemini
            logger.info(f"Inferindo dependências para {len(perguntas)} perguntas")

            response = await gemini_service.generate(
                prompt=prompt,
                system_prompt=self._get_system_prompt(),
                model=GEMINI_MODEL,
                temperature=0.1
            )

            if not response.success:
                logger.error(f"Erro na chamada Gemini: {response.error}")
                return {"success": False, "erro": f"Erro na IA: {response.error}"}

            # Parseia resposta
            resultado = self._extrair_json_resposta(response.content)

            if not resultado:
                logger.error(f"Resposta IA não é JSON válido: {response.content[:500]}")
                return {"success": False, "erro": "A IA não retornou um JSON válido"}

            dependencias = resultado.get("dependencias", [])

            # Valida e normaliza dependências
            dependencias_validadas = self._validar_dependencias(dependencias, perguntas)

            # Constrói grafo
            grafo = self._construir_grafo(dependencias_validadas, perguntas)

            logger.info(f"Inferidas {len(dependencias_validadas)} dependências")

            return {
                "success": True,
                "dependencias_inferidas": dependencias_validadas,
                "grafo": grafo
            }

        except Exception as e:
            logger.exception(f"Erro ao inferir dependências: {e}")
            return {"success": False, "erro": str(e)}

    async def analisar_dependencias_batch(
        self,
        perguntas: List[str],
        nomes_variaveis: List[Optional[str]],
        categoria_nome: str
    ) -> Dict[str, Any]:
        """
        Analisa dependências entre perguntas em lote (antes de serem criadas).
        
        Diferente de inferir_dependencias, este método:
        - Recebe apenas textos de perguntas (não objetos do banco)
        - Retorna um mapa indexado por posição na lista original
        - É usado para criação em lote com análise de dependências
        
        Args:
            perguntas: Lista de textos das perguntas
            nomes_variaveis: Lista de nomes sugeridos (pode conter None)
            categoria_nome: Nome da categoria para contexto
            
        Returns:
            Dict com:
            - success: bool
            - dependencias: Dict[str, Dict] mapeando índice -> info de dependência
            - grafo: estrutura de visualização
        """
        if not perguntas or len(perguntas) < 2:
            return {"success": True, "dependencias": {}, "grafo": None}
        
        try:
            # Monta prompt para IA
            prompt = self._montar_prompt_batch(perguntas, nomes_variaveis, categoria_nome)
            
            logger.info(f"Analisando dependências para {len(perguntas)} perguntas em lote")
            
            response = await gemini_service.generate(
                prompt=prompt,
                system_prompt=self._get_system_prompt_batch(),
                model=GEMINI_MODEL,
                temperature=0.1
            )
            
            if not response.success:
                logger.error(f"Erro na chamada Gemini: {response.error}")
                return {"success": False, "erro": f"Erro na IA: {response.error}"}
            
            # Parseia resposta
            resultado = self._extrair_json_resposta(response.content)
            
            if not resultado:
                logger.error(f"Resposta IA não é JSON válido: {response.content[:500]}")
                return {"success": False, "erro": "A IA não retornou um JSON válido"}
            
            # Converte para mapa indexado
            dependencias_map = {}
            for dep in resultado.get("dependencias", []):
                idx = dep.get("indice")
                if idx is not None and 0 <= idx < len(perguntas):
                    dependencias_map[str(idx)] = {
                        "depends_on_variable": dep.get("depends_on"),
                        "operator": dep.get("operator", "equals"),
                        "value": dep.get("value"),
                        "justificativa": dep.get("justificativa", "")
                    }
            
            # Constrói grafo simples
            grafo = {
                "ordem_recomendada": resultado.get("ordem_recomendada", list(range(len(perguntas)))),
                "arvore": resultado.get("arvore", {})
            }
            
            logger.info(f"Analisadas {len(dependencias_map)} dependências em lote")
            
            return {
                "success": True,
                "dependencias": dependencias_map,
                "grafo": grafo
            }
            
        except Exception as e:
            logger.exception(f"Erro ao analisar dependências em lote: {e}")
            return {"success": False, "erro": str(e)}
    
    def _get_system_prompt_batch(self) -> str:
        """Prompt de sistema para análise de dependências em lote."""
        return """Você é um especialista em análise de questionários e fluxos condicionais.

Sua tarefa é analisar uma lista de perguntas de extração de dados e:
1. Identificar quais perguntas dependem de outras
2. Sugerir a ordem correta de aplicação
3. Definir as condições de dependência

EXEMPLOS DE DEPENDÊNCIAS:

Perguntas:
0: "É ação de medicamento?"
1: "O medicamento tem registro na ANVISA?"
2: "É incorporado ao SUS?"
3: "Qual alternativa foi tentada antes?"

Dependências identificadas:
- Pergunta 1 depende de pergunta 0 (só faz sentido perguntar ANVISA se for medicamento)
- Pergunta 2 depende de pergunta 1 (só pergunta SUS se tiver registro ANVISA)
- Pergunta 3 depende de pergunta 2 com valor FALSE (só pergunta alternativa se NÃO for incorporado)

REGRAS:
1. Perguntas iniciais/de classificação geralmente são independentes
2. Perguntas de detalhamento dependem das de classificação
3. Use o slug sugerido ou infira baseado na pergunta
4. O índice é 0-based (primeira pergunta = 0)

FORMATO DE RESPOSTA (JSON estrito):
{
    "dependencias": [
        {
            "indice": 1,
            "depends_on": "medicamento",
            "operator": "equals",
            "value": true,
            "justificativa": "Só pergunta ANVISA se for ação de medicamento"
        },
        {
            "indice": 3,
            "depends_on": "incorporado_sus",
            "operator": "equals",
            "value": false,
            "justificativa": "Só pergunta alternativa se não for incorporado"
        }
    ],
    "ordem_recomendada": [0, 1, 2, 3],
    "arvore": {
        "medicamento": ["registro_anvisa"],
        "registro_anvisa": ["incorporado_sus"],
        "incorporado_sus": ["alternativa_tentada"]
    }
}"""

    def _montar_prompt_batch(
        self,
        perguntas: List[str],
        nomes_variaveis: List[Optional[str]],
        categoria_nome: str
    ) -> str:
        """Monta o prompt para análise de dependências em lote."""
        perguntas_formatadas = []
        
        for i, (pergunta, nome_var) in enumerate(zip(perguntas, nomes_variaveis)):
            linha = f"{i}: \"{pergunta}\""
            if nome_var:
                linha += f" (slug sugerido: {nome_var})"
            perguntas_formatadas.append(linha)
        
        return f"""Analise as seguintes perguntas de extração para a categoria "{categoria_nome}" e identifique dependências:

PERGUNTAS:
{chr(10).join(perguntas_formatadas)}

INSTRUÇÕES:
1. Identifique quais perguntas dependem de outras (use o índice 0-based)
2. Para cada dependência, indique:
   - indice: número da pergunta dependente
   - depends_on: slug da variável da qual depende (use o sugerido ou infira)
   - operator: equals, not_equals, exists, etc.
   - value: valor esperado (true, false, ou texto)
3. Sugira a ordem ideal de aplicação
4. Retorne APENAS JSON válido

IMPORTANTE: Perguntas sem dependência não devem aparecer na lista de dependências."""

    def _get_system_prompt(self) -> str:
        """Prompt de sistema para inferência de dependências."""
        return """Você é um especialista em análise de questionários e fluxos condicionais.

Sua tarefa é analisar uma lista de perguntas e identificar quais perguntas são CONDICIONAIS,
ou seja, só devem ser feitas se uma pergunta anterior tiver uma resposta específica.

EXEMPLOS DE DEPENDÊNCIAS:

1. "O autor é idoso?" (independente)
   "Possui isenção por idade?" (depende de: autor_idoso == true)

2. "É ação de medicamento?" (independente)
   "O medicamento tem registro na ANVISA?" (depende de: medicamento == true)
   "É incorporado ao SUS?" (depende de: registro_anvisa == true)

3. "Tipo de ação?" (independente, choice)
   "Qual o medicamento solicitado?" (depende de: tipo_acao == "medicamentos")

REGRAS:
1. Identifique perguntas que claramente dependem de respostas anteriores
2. Use o nome sugerido da variável ou infira um slug baseado na pergunta
3. Para dependências, indique:
   - pergunta_id: ID da pergunta dependente
   - depends_on: slug da variável da qual depende
   - operator: equals, not_equals, in_list, exists
   - value: valor esperado para habilitar a pergunta
4. Perguntas de abertura (tipo de ação, existe algo, etc.) geralmente são independentes
5. Perguntas de detalhamento geralmente dependem de perguntas de abertura

FORMATO DE RESPOSTA (JSON estrito):
{
    "dependencias": [
        {
            "pergunta_id": 2,
            "depends_on": "medicamento",
            "operator": "equals",
            "value": true,
            "justificativa": "Só faz sentido perguntar sobre ANVISA se for ação de medicamento"
        }
    ],
    "perguntas_independentes": [1, 3],
    "arvore": {
        "medicamento": ["registro_anvisa", "tipo_medicamento"],
        "registro_anvisa": ["incorporado_sus"]
    }
}"""

    def _montar_prompt_inferencia(
        self,
        perguntas: List[ExtractionQuestion],
        variaveis: List[ExtractionVariable]
    ) -> str:
        """Monta o prompt para inferência de dependências."""
        perguntas_formatadas = []

        for p in perguntas:
            info = f"ID: {p.id}"
            info += f"\nPergunta: {p.pergunta}"

            if p.nome_variavel_sugerido:
                info += f"\nVariável sugerida: {p.nome_variavel_sugerido}"

            if p.tipo_sugerido:
                info += f"\nTipo sugerido: {p.tipo_sugerido}"

            if p.opcoes_sugeridas:
                info += f"\nOpções: {', '.join(p.opcoes_sugeridas)}"

            if p.descricao:
                info += f"\nDescrição: {p.descricao}"

            # Inclui dependência existente se houver
            if p.depends_on_variable:
                info += f"\n[Já tem dependência: {p.depends_on_variable}]"

            perguntas_formatadas.append(info)

        variaveis_formatadas = []
        for v in variaveis:
            variaveis_formatadas.append(f"- {v.slug}: {v.label} ({v.tipo})")

        return f"""Analise as seguintes perguntas e identifique dependências condicionais:

PERGUNTAS:

{chr(10).join(perguntas_formatadas)}

VARIÁVEIS JÁ EXISTENTES:

{chr(10).join(variaveis_formatadas) if variaveis_formatadas else "(nenhuma)"}

INSTRUÇÕES:
1. Identifique quais perguntas dependem de respostas de outras perguntas
2. Use os slugs das variáveis existentes ou infira novos baseados nas sugestões
3. Retorne APENAS JSON válido"""

    def _extrair_json_resposta(self, resposta: str) -> Optional[Dict]:
        """Extrai JSON da resposta da IA."""
        resposta = resposta.strip()

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
            match = re.search(r'\{[\s\S]*\}', resposta)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return None

    def _validar_dependencias(
        self,
        dependencias: List[Dict],
        perguntas: List[ExtractionQuestion]
    ) -> List[Dict]:
        """Valida e normaliza as dependências inferidas."""
        pergunta_ids = {p.id for p in perguntas}
        validadas = []

        for dep in dependencias:
            pergunta_id = dep.get("pergunta_id")

            # Verifica se pergunta existe
            if pergunta_id not in pergunta_ids:
                continue

            # Valida operador
            operator = dep.get("operator", "equals")
            if operator not in [e.value for e in DependencyOperator]:
                operator = "equals"

            validadas.append({
                "pergunta_id": pergunta_id,
                "depends_on": dep.get("depends_on"),
                "operator": operator,
                "value": dep.get("value"),
                "justificativa": dep.get("justificativa", "")
            })

        return validadas

    def _construir_grafo(
        self,
        dependencias: List[Dict],
        perguntas: List[ExtractionQuestion]
    ) -> Dict[str, List[str]]:
        """Constrói grafo de dependências para visualização."""
        grafo = {}

        # Mapeia pergunta_id para variável sugerida
        pergunta_para_var = {}
        for p in perguntas:
            var_slug = p.nome_variavel_sugerido or f"q{p.id}"
            pergunta_para_var[p.id] = var_slug

        # Constrói grafo
        for dep in dependencias:
            parent = dep.get("depends_on")
            child = pergunta_para_var.get(dep.get("pergunta_id"))

            if parent and child:
                if parent not in grafo:
                    grafo[parent] = []
                grafo[parent].append(child)

        return grafo

    async def aplicar_dependencias(
        self,
        categoria_id: int,
        dependencias: List[Dict]
    ) -> Dict[str, Any]:
        """
        Aplica dependências inferidas às perguntas.

        Args:
            categoria_id: ID da categoria
            dependencias: Lista de dependências a aplicar

        Returns:
            Dict com success, perguntas_atualizadas
        """
        try:
            atualizadas = []

            for dep in dependencias:
                pergunta = self.db.query(ExtractionQuestion).filter(
                    ExtractionQuestion.id == dep["pergunta_id"],
                    ExtractionQuestion.categoria_id == categoria_id
                ).first()

                if not pergunta:
                    continue

                # Atualiza dependência
                pergunta.depends_on_variable = dep.get("depends_on")
                pergunta.dependency_operator = dep.get("operator", "equals")
                pergunta.dependency_value = dep.get("value")
                pergunta.dependency_inferred = True
                pergunta.atualizado_em = datetime.utcnow()

                atualizadas.append({
                    "id": pergunta.id,
                    "pergunta": pergunta.pergunta,
                    "depends_on": pergunta.depends_on_variable
                })

            self.db.commit()

            logger.info(f"Aplicadas {len(atualizadas)} dependências")

            return {
                "success": True,
                "perguntas_atualizadas": atualizadas
            }

        except Exception as e:
            self.db.rollback()
            logger.exception(f"Erro ao aplicar dependências: {e}")
            return {"success": False, "erro": str(e)}


class DependencyEvaluator:
    """
    Avaliador de dependências condicionais.

    Determina se uma pergunta/variável deve ser visível/aplicável
    com base nos dados extraídos.
    """

    def __init__(self):
        pass

    def avaliar_visibilidade(
        self,
        pergunta: ExtractionQuestion,
        dados: Dict[str, Any]
    ) -> bool:
        """
        Avalia se uma pergunta deve estar visível.

        Args:
            pergunta: Pergunta a avaliar
            dados: Dados extraídos até o momento

        Returns:
            True se a pergunta deve estar visível
        """
        # Sem dependência = sempre visível
        if not pergunta.depends_on_variable and not pergunta.dependency_config:
            return True

        # Dependência simples
        if pergunta.depends_on_variable:
            return self._avaliar_condicao_simples(
                variavel=pergunta.depends_on_variable,
                operador=pergunta.dependency_operator or "equals",
                valor_esperado=pergunta.dependency_value,
                dados=dados
            )

        # Dependência complexa
        if pergunta.dependency_config:
            return self._avaliar_condicao_complexa(
                pergunta.dependency_config,
                dados
            )

        return True

    def avaliar_aplicabilidade_variavel(
        self,
        variavel: ExtractionVariable,
        dados: Dict[str, Any]
    ) -> bool:
        """
        Avalia se uma variável é aplicável (deve ser considerada).

        Args:
            variavel: Variável a avaliar
            dados: Dados extraídos

        Returns:
            True se a variável é aplicável
        """
        if not variavel.is_conditional:
            return True

        if variavel.depends_on_variable:
            # Verifica se variável pai existe e tem valor
            if variavel.depends_on_variable not in dados:
                return False

            # Avalia configuração se houver
            if variavel.dependency_config:
                return self._avaliar_condicao_complexa(
                    variavel.dependency_config,
                    dados
                )

            # Padrão: variável pai deve ser truthy
            valor_pai = dados.get(variavel.depends_on_variable)
            return bool(valor_pai)

        return True

    def _avaliar_condicao_simples(
        self,
        variavel: str,
        operador: str,
        valor_esperado: Any,
        dados: Dict[str, Any]
    ) -> bool:
        """Avalia uma condição simples."""
        valor_atual = dados.get(variavel)

        if operador == "exists":
            return variavel in dados and valor_atual is not None

        if operador == "not_exists":
            return variavel not in dados or valor_atual is None

        if operador == "equals":
            return self._comparar_igual(valor_atual, valor_esperado)

        if operador == "not_equals":
            return not self._comparar_igual(valor_atual, valor_esperado)

        if operador == "in_list":
            if not isinstance(valor_esperado, list):
                valor_esperado = [valor_esperado]
            return valor_atual in valor_esperado

        if operador == "not_in_list":
            if not isinstance(valor_esperado, list):
                valor_esperado = [valor_esperado]
            return valor_atual not in valor_esperado

        if operador == "greater_than":
            try:
                return float(valor_atual or 0) > float(valor_esperado or 0)
            except (ValueError, TypeError):
                return False

        if operador == "less_than":
            try:
                return float(valor_atual or 0) < float(valor_esperado or 0)
            except (ValueError, TypeError):
                return False

        # Operador desconhecido = assume verdadeiro
        return True

    def _avaliar_condicao_complexa(
        self,
        config: Dict,
        dados: Dict[str, Any]
    ) -> bool:
        """Avalia uma condição complexa (múltiplas condições com AND/OR)."""
        conditions = config.get("conditions", [])
        logic = config.get("logic", "and")

        if not conditions:
            return True

        resultados = []
        for cond in conditions:
            resultado = self._avaliar_condicao_simples(
                variavel=cond.get("variable"),
                operador=cond.get("operator", "equals"),
                valor_esperado=cond.get("value"),
                dados=dados
            )
            resultados.append(resultado)

        if logic == "or":
            return any(resultados)

        return all(resultados)

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


class DependencyGraphBuilder:
    """
    Construtor de grafo de dependências para visualização.
    """

    def __init__(self, db: Session):
        self.db = db

    def construir_grafo_categoria(
        self,
        categoria_id: int
    ) -> Dict[str, Any]:
        """
        Constrói grafo de dependências para uma categoria.

        Returns:
            Dict com nodes, edges, e estrutura hierárquica
        """
        perguntas = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.categoria_id == categoria_id,
            ExtractionQuestion.ativo == True
        ).order_by(ExtractionQuestion.ordem).all()

        nodes = []
        edges = []
        hierarchy = {}

        # Cria nós
        for p in perguntas:
            var_slug = p.nome_variavel_sugerido or f"q{p.id}"

            node = {
                "id": p.id,
                "slug": var_slug,
                "label": p.pergunta[:50] + "..." if len(p.pergunta) > 50 else p.pergunta,
                "tipo": p.tipo_sugerido or "text",
                "is_conditional": p.is_conditional,
                "depends_on": p.depends_on_variable,
                "dependency_summary": p.dependency_summary,
                "ordem": p.ordem
            }
            nodes.append(node)

            # Cria edge se houver dependência
            if p.depends_on_variable:
                # Encontra pergunta pai pelo slug
                for parent in perguntas:
                    parent_slug = parent.nome_variavel_sugerido or f"q{parent.id}"
                    if parent_slug == p.depends_on_variable:
                        edges.append({
                            "from": parent.id,
                            "to": p.id,
                            "label": p.dependency_summary or ""
                        })
                        break

                # Constrói hierarquia
                if p.depends_on_variable not in hierarchy:
                    hierarchy[p.depends_on_variable] = []
                hierarchy[p.depends_on_variable].append(var_slug)

        return {
            "nodes": nodes,
            "edges": edges,
            "hierarchy": hierarchy,
            "root_questions": [
                n for n in nodes if not n["is_conditional"]
            ]
        }

    def obter_perguntas_dependentes(
        self,
        variable_slug: str,
        categoria_id: int
    ) -> List[Dict]:
        """
        Retorna todas as perguntas que dependem de uma variável.
        """
        perguntas = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.categoria_id == categoria_id,
            ExtractionQuestion.depends_on_variable == variable_slug,
            ExtractionQuestion.ativo == True
        ).all()

        return [
            {
                "id": p.id,
                "pergunta": p.pergunta,
                "dependency_summary": p.dependency_summary
            }
            for p in perguntas
        ]

    def obter_cadeia_dependencias(
        self,
        pergunta_id: int
    ) -> List[str]:
        """
        Retorna a cadeia de dependências de uma pergunta.

        Ex: ["medicamento", "registro_anvisa", "incorporado"]
        """
        cadeia = []
        visitados = set()

        pergunta = self.db.query(ExtractionQuestion).get(pergunta_id)

        while pergunta and pergunta.depends_on_variable:
            if pergunta.depends_on_variable in visitados:
                break  # Evita ciclos

            cadeia.append(pergunta.depends_on_variable)
            visitados.add(pergunta.depends_on_variable)

            # Busca pergunta pai
            pergunta = self.db.query(ExtractionQuestion).filter(
                ExtractionQuestion.categoria_id == pergunta.categoria_id,
                ExtractionQuestion.nome_variavel_sugerido == pergunta.depends_on_variable
            ).first()

        return list(reversed(cadeia))
