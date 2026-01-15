# sistemas/gerador_pecas/services_extraction.py
"""
Serviços para geração de schema de extração usando IA.

Este módulo implementa:
- Geração de schema JSON a partir de perguntas em linguagem natural
- Criação automática de variáveis normalizadas
- Validação e persistência dos modelos gerados

NOTA IMPORTANTE - Fonte de Verdade (fonte_verdade_tipo):
    O matching da fonte de verdade durante a extração deve ser feito
    SEMANTICAMENTE pela LLM, não por comparação literal de strings.

    Exemplo: Se o usuário configurar fonte_verdade_tipo="parecer do NAT"
    e a LLM classificar um documento como "parecer do NATJUS", a LLM
    deve entender que são equivalentes e usar esse documento como fonte.

    Isso permite flexibilidade na nomenclatura e evita falhas por
    pequenas diferenças de escrita (abreviações, caixa, etc.).
"""

import json
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

from services.gemini_service import gemini_service
from .models_extraction import (
    ExtractionQuestion, ExtractionModel, ExtractionVariable,
    ExtractionQuestionType
)
from .models_resumo_json import CategoriaResumoJSON

logger = logging.getLogger(__name__)


# Modelo obrigatório conforme especificação
GEMINI_MODEL = "gemini-3-flash-preview"


class ExtractionSchemaGenerator:
    """
    Gerador de schema de extração usando IA.

    Responsabilidades:
    - Converter perguntas em linguagem natural para schema JSON
    - Respeitar sugestões do usuário quando coerentes
    - Criar variáveis técnicas normalizadas
    - Persistir o modelo gerado no banco de dados
    """

    def __init__(self, db: Session):
        self.db = db

    async def gerar_schema(
        self,
        categoria_id: int,
        categoria_nome: str,
        perguntas: List[ExtractionQuestion],
        user_id: int
    ) -> Dict[str, Any]:
        """
        Gera um schema JSON de extração a partir das perguntas.

        Args:
            categoria_id: ID da categoria de documento
            categoria_nome: Nome da categoria para contexto
            perguntas: Lista de perguntas de extração
            user_id: ID do usuário que está gerando

        Returns:
            Dict com success, schema_json, mapeamento_variaveis, variaveis_criadas ou erro
        """
        try:
            # 1. Monta o prompt para a IA
            prompt = self._montar_prompt_geracao(categoria_nome, perguntas)

            # 2. Chama o Gemini para gerar o schema
            logger.info(f"Gerando schema para categoria '{categoria_nome}' com {len(perguntas)} perguntas")

            response = await gemini_service.generate(
                prompt=prompt,
                system_prompt=self._get_system_prompt(),
                model=GEMINI_MODEL,
                temperature=0.1  # Baixa temperatura para consistência
            )

            if not response.success:
                logger.error(f"Erro na chamada Gemini: {response.error}")
                return {"success": False, "erro": f"Erro na IA: {response.error}"}

            # 3. Parseia a resposta JSON
            resultado_ia = self._extrair_json_resposta(response.content)

            if not resultado_ia:
                logger.error(f"Resposta IA não é JSON válido: {response.content[:500]}")
                return {"success": False, "erro": "A IA não retornou um JSON válido"}

            schema_json = resultado_ia.get("schema")
            mapeamento = resultado_ia.get("mapeamento_variaveis", {})

            if not schema_json:
                return {"success": False, "erro": "Schema não encontrado na resposta da IA"}

            # 4. Valida e normaliza o schema
            schema_validado = self._validar_schema(schema_json)

            # 5. Cria as variáveis normalizadas
            variaveis_criadas = await self._criar_variaveis(
                categoria_id=categoria_id,
                mapeamento=mapeamento,
                perguntas=perguntas
            )

            # 6. Salva o modelo de extração
            modelo = await self._salvar_modelo(
                categoria_id=categoria_id,
                schema_json=schema_validado,
                mapeamento=mapeamento,
                user_id=user_id
            )

            logger.info(f"Schema gerado com sucesso: {len(variaveis_criadas)} variáveis criadas")

            return {
                "success": True,
                "schema_json": schema_validado,
                "mapeamento_variaveis": mapeamento,
                "variaveis_criadas": variaveis_criadas,
                "modelo_id": modelo.id,
                "modelo_versao": modelo.versao
            }

        except Exception as e:
            logger.exception(f"Erro ao gerar schema: {e}")
            return {"success": False, "erro": str(e)}

    def _get_system_prompt(self) -> str:
        """Retorna o prompt de sistema para geração de schema."""
        return """Você é um especialista em modelagem de dados e extração de informações de documentos jurídicos.

Sua tarefa é criar um schema JSON de extração a partir de perguntas em linguagem natural.

REGRAS CRÍTICAS:
1. Crie EXATAMENTE UMA variável para CADA pergunta - NÃO invente campos extras
2. O número de variáveis no schema DEVE ser IGUAL ao número de perguntas fornecidas
3. Se o usuário sugeriu nome de variável, USE EXATAMENTE esse nome
4. Se o usuário sugeriu tipo de dado, USE EXATAMENTE esse tipo
5. Se o usuário sugeriu opções (para múltipla escolha), INCLUA-as no schema
6. Variáveis devem ter slugs em snake_case, sem acentos
7. NÃO adicione campos que não foram solicitados nas perguntas
8. Sempre retorne JSON válido, SEM texto adicional

TIPOS DE DADOS SUPORTADOS:
- text: Texto livre
- number: Valor numérico
- date: Data (formato YYYY-MM-DD)
- boolean: Sim/Não
- choice: Escolha única entre opções
- list: Lista de valores
- currency: Valor monetário

VARIÁVEIS CONDICIONAIS (IMPORTANTE):
- Se a pergunta tem marcação [CONDICIONAL], você DEVE incluir os campos de dependência
- No "schema", adicione: "conditional": true, "depends_on": "variavel_pai", "dependency_operator": "equals", "dependency_value": valor
- No "mapeamento_variaveis", adicione: "is_conditional": true, "depends_on": "variavel_pai", "dependency_operator": "equals", "dependency_value": valor

FORMATO DE RESPOSTA (JSON estrito):
{
    "schema": {
        "nome_variavel_1": {
            "type": "boolean",
            "description": "descrição do campo"
        },
        "nome_variavel_2": {
            "type": "text",
            "description": "descrição do campo",
            "conditional": true,
            "depends_on": "nome_variavel_1",
            "dependency_operator": "equals",
            "dependency_value": true
        }
    },
    "mapeamento_variaveis": {
        "123": {
            "slug": "nome_variavel_1",
            "label": "Label Humano",
            "tipo": "boolean",
            "descricao": "Descrição",
            "is_conditional": false
        },
        "456": {
            "slug": "nome_variavel_2",
            "label": "Label 2",
            "tipo": "text",
            "descricao": "Descrição 2",
            "is_conditional": true,
            "depends_on": "nome_variavel_1",
            "dependency_operator": "equals",
            "dependency_value": true
        }
    }
}"""

    def _montar_prompt_geracao(
        self,
        categoria_nome: str,
        perguntas: List[ExtractionQuestion]
    ) -> str:
        """Monta o prompt para geração do schema."""
        perguntas_formatadas = []

        for i, p in enumerate(perguntas, 1):
            info = f"{i}. Pergunta: {p.pergunta}"

            if p.nome_variavel_sugerido:
                info += f"\n   - Nome sugerido: {p.nome_variavel_sugerido}"

            if p.tipo_sugerido:
                info += f"\n   - Tipo sugerido: {p.tipo_sugerido}"

            if p.opcoes_sugeridas:
                info += f"\n   - Opções sugeridas: {', '.join(p.opcoes_sugeridas)}"

            if p.descricao:
                info += f"\n   - Descrição: {p.descricao}"

            # Inclui informação de dependência se existir
            if p.depends_on_variable:
                info += f"\n   - [CONDICIONAL] Depende de: {p.depends_on_variable}"
                if p.dependency_operator:
                    info += f" ({p.dependency_operator}"
                    if p.dependency_value is not None:
                        info += f" = {p.dependency_value}"
                    info += ")"

            info += f"\n   - ID da pergunta: {p.id}"

            perguntas_formatadas.append(info)

        return f"""Crie um schema JSON de extração para documentos da categoria "{categoria_nome}".

TOTAL DE PERGUNTAS: {len(perguntas)} (o schema DEVE ter EXATAMENTE {len(perguntas)} variáveis)

PERGUNTAS A SEREM CONVERTIDAS EM VARIÁVEIS:

{chr(10).join(perguntas_formatadas)}

INSTRUÇÕES OBRIGATÓRIAS:
1. Crie EXATAMENTE {len(perguntas)} variáveis no schema (uma para cada pergunta)
2. NÃO invente variáveis extras - apenas as correspondentes às perguntas acima
3. Use o ID da pergunta como chave no mapeamento_variaveis
4. Se o usuário sugeriu nome de variável, use EXATAMENTE esse nome
5. Se o usuário sugeriu tipo, use EXATAMENTE esse tipo
6. Para perguntas marcadas como [CONDICIONAL]:
   - Adicione "conditional": true no schema
   - Adicione "depends_on", "dependency_operator" e "dependency_value"
7. Retorne APENAS o JSON, sem explicações"""

    def _extrair_json_resposta(self, resposta: str) -> Optional[Dict]:
        """Extrai JSON da resposta da IA."""
        # Tenta encontrar JSON na resposta
        resposta = resposta.strip()

        # Remove marcadores de código se presentes
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
            # Tenta encontrar JSON dentro do texto
            match = re.search(r'\{[\s\S]*\}', resposta)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            return None

    def _validar_schema(self, schema: Dict) -> Dict:
        """Valida e normaliza o schema gerado."""
        schema_validado = {}

        tipos_validos = {"text", "number", "date", "boolean", "choice", "list", "currency"}

        for nome, config in schema.items():
            # Normaliza nome da variável
            nome_normalizado = self._normalizar_slug(nome)

            # Valida tipo
            tipo = config.get("type", "text")
            if tipo not in tipos_validos:
                tipo = "text"

            # Monta configuração validada
            config_validada = {
                "type": tipo,
                "description": config.get("description", "")
            }

            # Adiciona opções se for choice
            if tipo == "choice" and "options" in config:
                config_validada["options"] = config["options"]

            # Preserva informações de dependência/condicional
            if config.get("conditional"):
                config_validada["conditional"] = True
            if config.get("depends_on"):
                config_validada["depends_on"] = config["depends_on"]
            if config.get("dependency_operator"):
                config_validada["dependency_operator"] = config["dependency_operator"]
            if config.get("dependency_value") is not None:
                config_validada["dependency_value"] = config["dependency_value"]

            schema_validado[nome_normalizado] = config_validada

        return schema_validado

    def _normalizar_slug(self, nome: str) -> str:
        """Normaliza um nome para slug snake_case."""
        # Remove acentos
        acentos = {
            'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a', 'ä': 'a',
            'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
            'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
            'ó': 'o', 'ò': 'o', 'õ': 'o', 'ô': 'o', 'ö': 'o',
            'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
            'ç': 'c', 'ñ': 'n'
        }

        nome_lower = nome.lower()
        for acento, sem_acento in acentos.items():
            nome_lower = nome_lower.replace(acento, sem_acento)

        # Substitui espaços e caracteres especiais por underscore
        slug = re.sub(r'[^a-z0-9]+', '_', nome_lower)

        # Remove underscores duplicados e nas pontas
        slug = re.sub(r'_+', '_', slug).strip('_')

        return slug or "variavel"

    def _aplicar_namespace(self, slug: str, namespace: str) -> str:
        """
        Aplica namespace ao slug se ainda não tiver.

        Args:
            slug: Slug base da variável
            namespace: Prefixo do namespace

        Returns:
            Slug com namespace aplicado
        """
        # Se já tem o namespace, retorna como está
        if slug.startswith(f"{namespace}_"):
            return slug

        # Aplica o namespace
        return f"{namespace}_{slug}"

    async def _criar_variaveis(
        self,
        categoria_id: int,
        mapeamento: Dict,
        perguntas: List[ExtractionQuestion]
    ) -> List[Dict]:
        """Cria as variáveis normalizadas no banco com namespace do grupo."""
        variaveis_criadas = []
        perguntas_map = {str(p.id): p for p in perguntas}

        # Busca a categoria para obter o namespace
        categoria = self.db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.id == categoria_id
        ).first()

        # Obtém o namespace (usa property que faz fallback para nome normalizado)
        namespace = categoria.namespace if categoria else ""

        for pergunta_id, info in mapeamento.items():
            slug_base = info.get("slug")
            if not slug_base:
                continue

            # Aplica namespace ao slug
            slug = self._aplicar_namespace(slug_base, namespace) if namespace else slug_base

            # Extrai informações de dependência
            is_conditional = info.get("is_conditional", False)
            depends_on = info.get("depends_on")
            dependency_operator = info.get("dependency_operator")
            dependency_value = info.get("dependency_value")

            # Se a pergunta original tem dependência, usa ela
            pergunta = perguntas_map.get(pergunta_id)
            if pergunta and pergunta.depends_on_variable:
                is_conditional = True
                depends_on = pergunta.depends_on_variable
                dependency_operator = pergunta.dependency_operator
                dependency_value = pergunta.dependency_value

            # Aplica namespace ao depends_on também (se existir e não tiver namespace)
            if depends_on and namespace:
                depends_on = self._aplicar_namespace(depends_on, namespace)

            # Monta dependency_config se houver dependência
            dependency_config = None
            if depends_on and dependency_operator:
                dependency_config = {
                    "conditions": [{
                        "variable": depends_on,
                        "operator": dependency_operator,
                        "value": dependency_value
                    }],
                    "logic": "and"
                }

            # Verifica se já existe
            existente = self.db.query(ExtractionVariable).filter(
                ExtractionVariable.slug == slug
            ).first()

            if existente:
                # Atualiza se necessário
                existente.label = info.get("label", existente.label)
                existente.descricao = info.get("descricao", existente.descricao)
                existente.is_conditional = is_conditional
                existente.depends_on_variable = depends_on
                existente.dependency_config = dependency_config
                existente.atualizado_em = datetime.utcnow()

                variaveis_criadas.append({
                    "id": existente.id,
                    "slug": existente.slug,
                    "slug_base": slug_base,
                    "namespace": namespace,
                    "label": existente.label,
                    "tipo": existente.tipo,
                    "is_conditional": is_conditional,
                    "depends_on": depends_on,
                    "atualizado": True
                })
            else:
                # Cria nova variável
                variavel = ExtractionVariable(
                    slug=slug,
                    label=info.get("label", slug_base.replace("_", " ").title()),
                    descricao=info.get("descricao"),
                    tipo=info.get("tipo", "text"),
                    categoria_id=categoria_id,
                    opcoes=info.get("opcoes"),
                    source_question_id=int(pergunta_id) if pergunta_id.isdigit() else None,
                    is_conditional=is_conditional,
                    depends_on_variable=depends_on,
                    dependency_config=dependency_config,
                    ativo=True
                )
                self.db.add(variavel)
                self.db.flush()

                variaveis_criadas.append({
                    "id": variavel.id,
                    "slug": variavel.slug,
                    "slug_base": slug_base,
                    "namespace": namespace,
                    "label": variavel.label,
                    "tipo": variavel.tipo,
                    "is_conditional": is_conditional,
                    "depends_on": depends_on,
                    "criado": True
                })

        self.db.commit()
        return variaveis_criadas

    async def _salvar_modelo(
        self,
        categoria_id: int,
        schema_json: Dict,
        mapeamento: Dict,
        user_id: int
    ) -> ExtractionModel:
        """Salva o modelo de extração no banco."""
        # Desativa modelos anteriores
        self.db.query(ExtractionModel).filter(
            ExtractionModel.categoria_id == categoria_id,
            ExtractionModel.ativo == True
        ).update({"ativo": False})

        # Calcula próxima versão
        max_versao = self.db.query(func.max(ExtractionModel.versao)).filter(
            ExtractionModel.categoria_id == categoria_id
        ).scalar() or 0

        # Cria novo modelo
        modelo = ExtractionModel(
            categoria_id=categoria_id,
            modo="ai_generated",
            schema_json=schema_json,
            mapeamento_variaveis=mapeamento,
            versao=max_versao + 1,
            ativo=True,
            criado_por=user_id
        )
        self.db.add(modelo)
        self.db.commit()
        self.db.refresh(modelo)

        return modelo


class ExtractionSchemaValidator:
    """Validador de schemas de extração."""

    @staticmethod
    def validar_schema(schema: Dict) -> Dict[str, Any]:
        """
        Valida um schema de extração.

        Returns:
            Dict com "valid" e "errors" ou "warnings"
        """
        erros = []
        avisos = []
        tipos_validos = {"text", "number", "date", "boolean", "choice", "list", "currency"}

        if not isinstance(schema, dict):
            return {"valid": False, "errors": ["Schema deve ser um objeto JSON"]}

        if not schema:
            return {"valid": False, "errors": ["Schema não pode estar vazio"]}

        for nome, config in schema.items():
            # Valida nome
            if not re.match(r'^[a-z][a-z0-9_]*$', nome):
                avisos.append(f"Nome '{nome}' não segue padrão snake_case")

            # Valida configuração
            if not isinstance(config, dict):
                erros.append(f"Configuração de '{nome}' deve ser um objeto")
                continue

            # Valida tipo
            tipo = config.get("type")
            if not tipo:
                erros.append(f"Variável '{nome}' não tem tipo definido")
            elif tipo not in tipos_validos:
                erros.append(f"Tipo '{tipo}' inválido para '{nome}'. Use: {', '.join(tipos_validos)}")

            # Valida opções para choice
            if tipo == "choice":
                opcoes = config.get("options")
                if not opcoes or not isinstance(opcoes, list) or len(opcoes) < 2:
                    erros.append(f"Variável '{nome}' tipo choice deve ter pelo menos 2 opções")

        return {
            "valid": len(erros) == 0,
            "errors": erros,
            "warnings": avisos
        }
