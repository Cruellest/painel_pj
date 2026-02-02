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

from services.gemini_service import gemini_service, get_thinking_level
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

            # Obtém thinking_level da config
            thinking_level = get_thinking_level(self.db, "gerador_pecas")

            response = await gemini_service.generate(
                prompt=prompt,
                system_prompt=self._get_system_prompt(),
                model=GEMINI_MODEL,
                temperature=0.1,
                thinking_level=thinking_level  # Configurável em /admin/prompts-config
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
        Analisa, normaliza e gera nomenclatura para perguntas em lote.

        Este método:
        - Recebe textos brutos de perguntas (podem conter instruções internas)
        - Reescreve cada pergunta de forma clara e institucional
        - Gera nome_base_variavel para cada pergunta
        - Identifica dependências entre perguntas
        - Retorna tudo indexado por posição na lista original

        Args:
            perguntas: Lista de textos das perguntas (brutas)
            nomes_variaveis: Lista de nomes sugeridos (pode conter None)
            categoria_nome: Nome da categoria para contexto

        Returns:
            Dict com:
            - success: bool
            - perguntas_normalizadas: Dict[str, Dict] mapeando índice -> {texto_final, nome_base_variavel}
            - dependencias: Dict[str, Dict] mapeando índice -> info de dependência
            - grafo: estrutura de visualização
            - erro: mensagem de erro (se success=False)
        """
        # Caso especial: apenas 1 pergunta - ainda precisa normalizar
        if not perguntas:
            return {"success": True, "perguntas_normalizadas": {}, "dependencias": {}, "grafo": None}

        try:
            # Monta prompt para IA
            prompt = self._montar_prompt_batch(perguntas, nomes_variaveis, categoria_nome)

            logger.info(f"Analisando e normalizando {len(perguntas)} perguntas em lote")

            # Obtém thinking_level da config
            thinking_level = get_thinking_level(self.db, "gerador_pecas")

            # Calcula tokens necessários: ~200 tokens por pergunta na resposta JSON
            max_tokens_resposta = max(4096, len(perguntas) * 250)

            response = await gemini_service.generate(
                prompt=prompt,
                system_prompt=self._get_system_prompt_batch(),
                model=GEMINI_MODEL,
                temperature=0.1,
                thinking_level=thinking_level,  # Configurável em /admin/prompts-config
                max_tokens=max_tokens_resposta  # Garante resposta completa para muitas perguntas
            )

            if not response.success:
                logger.error(f"Erro na chamada Gemini: {response.error}")
                return {"success": False, "erro": f"Erro na IA: {response.error}"}

            # Parseia resposta
            resultado = self._extrair_json_resposta(response.content)

            if not resultado:
                logger.error(f"Resposta IA não é JSON válido: {response.content[:500]}")
                return {"success": False, "erro": "A IA não retornou um JSON válido"}

            # Processa perguntas normalizadas (OBRIGATÓRIO)
            perguntas_normalizadas = resultado.get("perguntas_normalizadas", [])
            if not perguntas_normalizadas:
                logger.error("IA não retornou perguntas_normalizadas")
                return {
                    "success": False,
                    "erro": "A IA não retornou as perguntas normalizadas. Tente novamente."
                }

            # ═══════════════════════════════════════════════════════════════
            # VALIDAÇÃO RIGOROSA 1:1 - A IA NÃO PODE CRIAR PERGUNTAS EXTRAS
            # ═══════════════════════════════════════════════════════════════
            #
            # Regra: O número de perguntas retornadas DEVE ser EXATAMENTE igual
            # ao número de perguntas fornecidas pelo usuário.
            #
            # A IA pode: reescrever, normalizar, criar dependências, definir variáveis
            # A IA NÃO pode: adicionar, dividir, fundir ou remover perguntas
            # ═══════════════════════════════════════════════════════════════

            n_fornecidas = len(perguntas)
            n_retornadas = len(perguntas_normalizadas)

            # Validação 1: Quantidade exata
            if n_retornadas != n_fornecidas:
                logger.error(
                    f"[VALIDAÇÃO 1:1 FALHOU] Quantidade incorreta de perguntas. "
                    f"Fornecidas: {n_fornecidas}, Retornadas pela IA: {n_retornadas}. "
                    f"Perguntas originais: {perguntas[:5]}..."  # Log primeiras 5 para debug
                )
                return {
                    "success": False,
                    "erro": (
                        f"A IA retornou {n_retornadas} perguntas, mas foram fornecidas {n_fornecidas}. "
                        f"Nenhuma pergunta foi criada. A IA não pode adicionar ou remover perguntas."
                    )
                }

            # Validação 2: Índices únicos e dentro do range
            indices_encontrados = []
            indices_duplicados = []
            indices_fora_range = []

            for pn in perguntas_normalizadas:
                idx = pn.get("indice")
                if idx is None:
                    indices_fora_range.append("null")
                    continue
                if not isinstance(idx, int):
                    indices_fora_range.append(str(idx))
                    continue
                if idx < 0 or idx >= n_fornecidas:
                    indices_fora_range.append(str(idx))
                    continue
                if idx in indices_encontrados:
                    indices_duplicados.append(idx)
                else:
                    indices_encontrados.append(idx)

            if indices_duplicados:
                logger.error(
                    f"[VALIDAÇÃO 1:1 FALHOU] Índices duplicados: {indices_duplicados}. "
                    f"N fornecidas: {n_fornecidas}"
                )
                return {
                    "success": False,
                    "erro": (
                        f"A IA retornou índices duplicados: {indices_duplicados}. "
                        f"Nenhuma pergunta foi criada."
                    )
                }

            if indices_fora_range:
                logger.error(
                    f"[VALIDAÇÃO 1:1 FALHOU] Índices fora do range [0, {n_fornecidas-1}]: {indices_fora_range}. "
                )
                return {
                    "success": False,
                    "erro": (
                        f"A IA retornou índices inválidos: {indices_fora_range}. "
                        f"Índices válidos: 0 a {n_fornecidas-1}. Nenhuma pergunta foi criada."
                    )
                }

            # Validação 3: Todos os índices presentes
            indices_faltando = set(range(n_fornecidas)) - set(indices_encontrados)
            if indices_faltando:
                logger.error(
                    f"[VALIDAÇÃO 1:1 FALHOU] Índices faltando: {sorted(indices_faltando)}. "
                    f"Encontrados: {sorted(indices_encontrados)}"
                )
                return {
                    "success": False,
                    "erro": (
                        f"A IA não retornou os índices: {sorted(indices_faltando)}. "
                        f"Todas as {n_fornecidas} perguntas devem ser processadas. Nenhuma pergunta foi criada."
                    )
                }

            logger.info(
                f"[VALIDAÇÃO 1:1 OK] {n_fornecidas} perguntas fornecidas, "
                f"{n_retornadas} retornadas, todos os índices válidos."
            )

            # Processa perguntas normalizadas validadas
            perguntas_map = {}
            erros_validacao = []

            for pn in perguntas_normalizadas:
                idx = pn.get("indice")

                texto_final = pn.get("texto_final", "").strip()
                nome_base = pn.get("nome_base_variavel", "").strip()
                tipo_sugerido = pn.get("tipo_sugerido", "").strip().lower() if pn.get("tipo_sugerido") else ""
                opcoes_sugeridas = pn.get("opcoes_sugeridas")

                # Validações obrigatórias
                if not texto_final:
                    erros_validacao.append(f"Pergunta {idx}: texto_final vazio")
                    continue

                if not nome_base:
                    erros_validacao.append(f"Pergunta {idx}: nome_base_variavel não definido")
                    continue

                # Normaliza nome_base_variavel (remove acentos, caracteres inválidos)
                nome_base = self._normalizar_nome_variavel(nome_base)

                if not nome_base:
                    erros_validacao.append(f"Pergunta {idx}: nome_base_variavel inválido após normalização")
                    continue

                # Valida tipo_sugerido
                tipos_validos = ["text", "number", "date", "boolean", "choice", "list", "currency"]
                if tipo_sugerido and tipo_sugerido not in tipos_validos:
                    tipo_sugerido = "text"  # Fallback para text se tipo inválido

                # Se tipo é choice mas não tem opções, avisa no log
                if tipo_sugerido == "choice" and not opcoes_sugeridas:
                    logger.warning(f"Pergunta {idx}: tipo 'choice' sem opcoes_sugeridas")

                perguntas_map[str(idx)] = {
                    "texto_final": texto_final,
                    "nome_base_variavel": nome_base,
                    "texto_original": pn.get("texto_original", perguntas[idx]),
                    "tipo_sugerido": tipo_sugerido or None,
                    "opcoes_sugeridas": opcoes_sugeridas if isinstance(opcoes_sugeridas, list) else None
                }

            # Verifica se todas as perguntas foram processadas com sucesso
            if len(perguntas_map) != n_fornecidas:
                faltando = set(range(n_fornecidas)) - set(int(k) for k in perguntas_map.keys())
                if faltando:
                    erros_validacao.append(f"Perguntas com dados inválidos: {sorted(faltando)}")

            if erros_validacao:
                logger.error(f"Erros de validação de conteúdo: {erros_validacao}")
                return {
                    "success": False,
                    "erro": f"Erros na normalização: {'; '.join(erros_validacao)}"
                }

            # Converte dependências para mapa indexado
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

            logger.info(
                f"Normalizadas {len(perguntas_map)} perguntas, "
                f"{len(dependencias_map)} com dependências"
            )

            return {
                "success": True,
                "perguntas_normalizadas": perguntas_map,
                "dependencias": dependencias_map,
                "grafo": grafo
            }

        except Exception as e:
            logger.exception(f"Erro ao analisar dependências em lote: {e}")
            return {"success": False, "erro": str(e)}

    def _normalizar_nome_variavel(self, nome: str) -> str:
        """
        Normaliza o nome da variável removendo acentos e caracteres inválidos.

        Args:
            nome: Nome bruto da variável

        Returns:
            Nome normalizado (lowercase, sem acentos, apenas [a-z0-9_])
        """
        import unicodedata

        if not nome:
            return ""

        # Remove acentos
        nome = unicodedata.normalize('NFD', nome)
        nome = ''.join(c for c in nome if unicodedata.category(c) != 'Mn')

        # Converte para minúsculas
        nome = nome.lower()

        # Substitui espaços e hífens por underscore
        nome = re.sub(r'[\s\-]+', '_', nome)

        # Remove caracteres não permitidos
        nome = re.sub(r'[^a-z0-9_]', '', nome)

        # Remove underscores duplicados
        nome = re.sub(r'_+', '_', nome)

        # Remove underscores no início e fim
        nome = nome.strip('_')

        return nome
    
    def _get_system_prompt_batch(self) -> str:
        """Prompt de sistema para análise, normalização e nomenclatura de perguntas em lote."""
        return """Você é um especialista em questionários jurídicos e fluxos condicionais para a Procuradoria-Geral do Estado.

Sua tarefa é processar uma lista de perguntas de extração de dados e:
1. **REESCREVER** cada pergunta de forma clara, técnica e institucional
2. **GERAR** um nome base de variável para cada pergunta
3. **DEFINIR** o tipo de dado correto para cada pergunta
4. **IDENTIFICAR** dependências entre perguntas
5. **SUGERIR** a ordem correta de aplicação

═══════════════════════════════════════════════════════════════
REGRA CRÍTICA: NORMALIZAÇÃO DAS PERGUNTAS
═══════════════════════════════════════════════════════════════

O usuário pode escrever perguntas "bagunçadas" com instruções internas como:
- "(pergunta mãe)"
- "(essa depende da anterior)"
- "se sim, perguntar..."
- "usar só se aplicável"
- Notas pessoais entre parênteses

Você DEVE:
1. REMOVER todas as instruções/metalinguagem do texto
2. REESCREVER a pergunta em português claro, direto e técnico
3. MANTER o sentido jurídico original
4. GARANTIR que a pergunta final seja adequada para uso formal

═══════════════════════════════════════════════════════════════
REGRA CRÍTICA: TIPO DE DADO (tipo_sugerido)
═══════════════════════════════════════════════════════════════

Para cada pergunta, você DEVE definir o tipo_sugerido seguindo estas regras:

1. **boolean**: OBRIGATÓRIO quando a resposta for SIM/NÃO
   - Exemplos: "Foi concedida liminar?", "O autor é idoso?", "Há prescrição?"
   - NUNCA use "text" para perguntas de sim/não

2. **choice**: OBRIGATÓRIO quando a resposta for um conjunto fechado de alternativas
   - DEVE incluir "opcoes_sugeridas" com as alternativas
   - Opções em minúsculo, sem acentos, com underscore se necessário
   - Exemplos: resultado, periodicidade, natureza, tipo de ação

3. **text**: APENAS quando a resposta for inevitavelmente livre
   - Listas descritivas, fundamentos, nomes, descrições abertas

4. **list**: Para respostas que são listas de itens

5. **number**: Valores numéricos puros

6. **currency**: Valores monetários (R$)

7. **date**: Datas

TIPOS DISPONÍVEIS: text, number, date, boolean, choice, list, currency

═══════════════════════════════════════════════════════════════
REGRA CRÍTICA: NOME BASE DA VARIÁVEL
═══════════════════════════════════════════════════════════════

Para cada pergunta, você DEVE gerar um nome_base_variavel seguindo estas regras:
- Apenas letras minúsculas, números e underscore (_)
- Sem acentos ou caracteres especiais
- Nome curto (2-4 palavras) mas semanticamente claro
- Deve ser compreensível SEM ler a pergunta
- NÃO incluir prefixo da categoria (o sistema adiciona automaticamente)

═══════════════════════════════════════════════════════════════
REGRAS DE DEPENDÊNCIAS
═══════════════════════════════════════════════════════════════

1. Perguntas iniciais/de classificação geralmente são independentes
2. Perguntas de detalhamento dependem das de classificação
3. Use o nome_base_variavel para referenciar dependências
4. dependency_value deve respeitar o tipo da variável pai:
   - boolean → true/false
   - choice → valor exatamente igual a uma das opcoes
5. O índice é 0-based (primeira pergunta = 0)

FORMATO DE RESPOSTA (JSON estrito):
{
    "perguntas_normalizadas": [
        {
            "indice": 0,
            "texto_original": "é ação de medicamento? (pergunta mãe)",
            "texto_final": "Trata-se de ação judicial envolvendo medicamentos?",
            "nome_base_variavel": "medicamento",
            "tipo_sugerido": "boolean"
        },
        {
            "indice": 1,
            "texto_original": "qual o resultado da decisão? (deferida/indeferida/parcial)",
            "texto_final": "Qual foi o resultado da decisão judicial?",
            "nome_base_variavel": "resultado_decisao",
            "tipo_sugerido": "choice",
            "opcoes_sugeridas": ["deferida", "parcialmente_deferida", "indeferida"]
        },
        {
            "indice": 2,
            "texto_original": "tem registro anvisa?? (só se for medicamento)",
            "texto_final": "O medicamento possui registro válido na ANVISA?",
            "nome_base_variavel": "medicamento_registro_anvisa",
            "tipo_sugerido": "boolean"
        }
    ],
    "dependencias": [
        {
            "indice": 2,
            "depends_on": "medicamento",
            "operator": "equals",
            "value": true,
            "justificativa": "Só pergunta ANVISA se for ação de medicamento"
        }
    ],
    "ordem_recomendada": [0, 1, 2],
    "arvore": {
        "medicamento": ["medicamento_registro_anvisa"]
    }
}

═══════════════════════════════════════════════════════════════
REGRA PROIBITIVA: NÃO CRIE PERGUNTAS EXTRAS
═══════════════════════════════════════════════════════════════

VOCÊ NÃO PODE:
- Adicionar perguntas novas que não estejam na lista original
- Dividir uma pergunta em duas ou mais
- Fundir duas perguntas em uma
- Remover perguntas (exceto linhas vazias já filtradas)

O array perguntas_normalizadas DEVE conter EXATAMENTE o mesmo número
de perguntas que foi enviado, com os mesmos índices (0 a N-1).
Se violar esta regra, a operação será REJEITADA.

IMPORTANTE:
- perguntas_normalizadas é OBRIGATÓRIO e deve conter TODAS as perguntas
- Cada pergunta DEVE ter: texto_final, nome_base_variavel, tipo_sugerido
- Se tipo_sugerido for "choice", DEVE incluir opcoes_sugeridas
- Perguntas sem dependência NÃO devem aparecer na lista de dependências"""

    def _montar_prompt_batch(
        self,
        perguntas: List[str],
        nomes_variaveis: List[Optional[str]],
        categoria_nome: str
    ) -> str:
        """Monta o prompt para análise, normalização e nomenclatura de perguntas em lote."""
        perguntas_formatadas = []

        for i, (pergunta, nome_var) in enumerate(zip(perguntas, nomes_variaveis)):
            linha = f"{i}: \"{pergunta}\""
            if nome_var:
                linha += f" (sugestão de variável: {nome_var})"
            perguntas_formatadas.append(linha)

        total_perguntas = len(perguntas)

        return f"""Processe as seguintes {total_perguntas} perguntas de extração para a categoria "{categoria_nome}".

PERGUNTAS BRUTAS (podem conter instruções internas do usuário):
{chr(10).join(perguntas_formatadas)}

═══════════════════════════════════════════════════════════════
ATENÇÃO: VOCÊ DEVE PROCESSAR TODAS AS {total_perguntas} PERGUNTAS!
═══════════════════════════════════════════════════════════════

TAREFAS OBRIGATÓRIAS:
1. Para CADA uma das {total_perguntas} perguntas (índices 0 a {total_perguntas - 1}), retorne em perguntas_normalizadas:
   - indice: posição original (0-based)
   - texto_original: a pergunta como foi digitada
   - texto_final: pergunta REESCRITA de forma clara, técnica e institucional
   - nome_base_variavel: nome curto e semântico para a variável

2. Identifique dependências entre perguntas (se houver)

3. Sugira a ordem ideal de aplicação

REGRAS DE NORMALIZAÇÃO:
- Remova TODA metalinguagem: "(pergunta mãe)", "se sim...", "(depende de...)", etc.
- Reescreva em português formal adequado para documentos jurídicos
- Mantenha o sentido original da pergunta
- Use letras maiúsculas no início e ponto de interrogação no final

REGRAS PARA nome_base_variavel:
- Apenas letras minúsculas, números e underscore
- Sem acentos ou caracteres especiais
- Máximo 4 palavras separadas por underscore
- Deve ser autoexplicativo sem ler a pergunta

═══════════════════════════════════════════════════════════════
CRÍTICO: VALIDAÇÃO DE QUANTIDADE
═══════════════════════════════════════════════════════════════

O array perguntas_normalizadas DEVE conter EXATAMENTE {total_perguntas} objetos.
Cada objeto DEVE ter um campo "indice" único de 0 a {total_perguntas - 1}.

PROIBIDO:
- Criar perguntas adicionais (retornar mais que {total_perguntas})
- Dividir uma pergunta em múltiplas
- Fundir perguntas
- Omitir perguntas (retornar menos que {total_perguntas})
- Repetir índices

Se você retornar quantidade diferente de {total_perguntas}, a operação será REJEITADA.

Retorne APENAS JSON válido no formato especificado."""

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
