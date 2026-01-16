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

        MODO INCREMENTAL: Se já existem variáveis vinculadas a perguntas,
        apenas processa as perguntas NOVAS (sem variável), mantendo o schema existente.

        Args:
            categoria_id: ID da categoria de documento
            categoria_nome: Nome da categoria para contexto
            perguntas: Lista de perguntas de extração
            user_id: ID do usuário que está gerando

        Returns:
            Dict com success, schema_json, mapeamento_variaveis, variaveis_criadas ou erro
        """
        try:
            # 0. MODO INCREMENTAL: Separar perguntas novas das existentes
            perguntas_novas = []
            perguntas_existentes = []

            # Busca a categoria para obter o namespace
            categoria = self.db.query(CategoriaResumoJSON).filter(
                CategoriaResumoJSON.id == categoria_id
            ).first()
            namespace = categoria.namespace if categoria else ""

            for p in perguntas:
                # Verifica se já tem variável vinculada (por source_question_id)
                variavel_existente = self.db.query(ExtractionVariable).filter(
                    ExtractionVariable.source_question_id == p.id,
                    ExtractionVariable.ativo == True
                ).first()

                # Se não encontrou por source_question_id, tenta por slug
                if not variavel_existente and p.nome_variavel_sugerido:
                    # Tenta encontrar variável pelo slug (com e sem namespace)
                    slug_base = p.nome_variavel_sugerido.strip()
                    slug_com_namespace = self._aplicar_namespace(slug_base, namespace) if namespace else slug_base

                    variavel_existente = self.db.query(ExtractionVariable).filter(
                        ExtractionVariable.slug.in_([slug_base, slug_com_namespace]),
                        ExtractionVariable.ativo == True
                    ).first()

                    if variavel_existente:
                        # Vincula a variável à pergunta para futuras consultas
                        variavel_existente.source_question_id = p.id
                        logger.info(f"Variável '{variavel_existente.slug}' vinculada à pergunta {p.id}")

                if variavel_existente:
                    perguntas_existentes.append((p, variavel_existente))
                    # Sincroniza nome_variavel_sugerido da pergunta com o slug da variável
                    if not p.nome_variavel_sugerido or p.nome_variavel_sugerido != variavel_existente.slug:
                        p.nome_variavel_sugerido = variavel_existente.slug
                else:
                    perguntas_novas.append(p)

            logger.info(f"Geração incremental: {len(perguntas_existentes)} existentes, {len(perguntas_novas)} novas")

            # Se não há perguntas novas, retorna o schema existente
            if not perguntas_novas:
                # Monta schema a partir das variáveis existentes
                schema_existente = {}
                mapeamento_existente = {}
                for p, v in perguntas_existentes:
                    schema_existente[v.slug] = {
                        "type": v.tipo,
                        "description": v.descricao or v.label
                    }
                    mapeamento_existente[str(p.id)] = {
                        "slug": v.slug,
                        "label": v.label,
                        "tipo": v.tipo
                    }

                # Injeta dependências mesmo no schema existente
                categoria = self.db.query(CategoriaResumoJSON).filter(
                    CategoriaResumoJSON.id == categoria_id
                ).first()
                namespace = categoria.namespace if categoria else ""

                schema_existente = self._injetar_dependencias_no_schema(
                    schema_existente,
                    mapeamento_existente,
                    [p for p, v in perguntas_existentes],
                    namespace
                )

                # Injeta opções mesmo no schema existente
                schema_existente = self._injetar_opcoes_no_schema(
                    schema_existente,
                    mapeamento_existente,
                    [p for p, v in perguntas_existentes],
                    namespace
                )

                return {
                    "success": True,
                    "schema_json": schema_existente,
                    "mapeamento_variaveis": mapeamento_existente,
                    "variaveis_criadas": [],
                    "mensagem": "Nenhuma pergunta nova para processar. Schema existente mantido."
                }

            # 1. Monta o prompt APENAS para as perguntas NOVAS
            prompt = self._montar_prompt_geracao(categoria_nome, perguntas_novas)

            # 2. Chama o Gemini para gerar o schema APENAS das perguntas novas
            logger.info(f"Gerando schema incremental para categoria '{categoria_nome}' com {len(perguntas_novas)} perguntas NOVAS")

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

            schema_novo = resultado_ia.get("schema", {})
            mapeamento_novo = resultado_ia.get("mapeamento_variaveis", {})

            if not schema_novo:
                return {"success": False, "erro": "Schema não encontrado na resposta da IA"}

            # 4. Valida e normaliza o schema novo
            schema_novo_validado = self._validar_schema(schema_novo)

            # 5. MERGE: Combina schema existente com o novo
            schema_final = {}
            mapeamento_final = {}

            # Primeiro adiciona as variáveis existentes
            for p, v in perguntas_existentes:
                schema_final[v.slug] = {
                    "type": v.tipo,
                    "description": v.descricao or v.label
                }
                mapeamento_final[str(p.id)] = {
                    "slug": v.slug,
                    "label": v.label,
                    "tipo": v.tipo
                }

            # 5.0 APLICA NAMESPACE: aos slugs do schema novo (antes de fazer merge)
            # Busca categoria para obter namespace
            categoria = self.db.query(CategoriaResumoJSON).filter(
                CategoriaResumoJSON.id == categoria_id
            ).first()
            namespace = categoria.namespace if categoria else ""

            # Aplica namespace aos slugs do schema novo e mapeamento
            if namespace:
                schema_novo_com_namespace = {}
                for slug, config in schema_novo_validado.items():
                    slug_com_ns = self._aplicar_namespace(slug, namespace)
                    schema_novo_com_namespace[slug_com_ns] = config
                schema_novo_validado = schema_novo_com_namespace

                # Também atualiza o mapeamento
                for pergunta_id, info in mapeamento_novo.items():
                    if info.get("slug") and not info["slug"].startswith(f"{namespace}_"):
                        info["slug"] = self._aplicar_namespace(info["slug"], namespace)

            # Depois adiciona os campos novos
            schema_final.update(schema_novo_validado)
            mapeamento_final.update(mapeamento_novo)

            # 5.1 INJEÇÃO DE DEPENDÊNCIAS: Garante que dependências das perguntas sejam
            # refletidas no schema, independentemente do que a IA retornou
            schema_final = self._injetar_dependencias_no_schema(
                schema_final,
                mapeamento_final,
                perguntas,  # Todas as perguntas (existentes + novas)
                namespace
            )

            # 5.2 INJEÇÃO DE OPÇÕES: Garante que opções definidas pelo usuário sejam
            # refletidas no schema, independentemente do que a IA retornou
            schema_final = self._injetar_opcoes_no_schema(
                schema_final,
                mapeamento_final,
                perguntas,  # Todas as perguntas
                namespace
            )

            # 6. Cria APENAS as variáveis NOVAS
            variaveis_criadas = await self._criar_variaveis(
                categoria_id=categoria_id,
                mapeamento=mapeamento_novo,  # Apenas mapeamento novo
                perguntas=perguntas_novas     # Apenas perguntas novas
            )

            # 7. Salva o modelo de extração (com schema completo)
            modelo = await self._salvar_modelo(
                categoria_id=categoria_id,
                schema_json=schema_final,     # Schema completo (existente + novo)
                mapeamento=mapeamento_final,  # Mapeamento completo
                user_id=user_id
            )

            logger.info(f"Schema incremental gerado: {len(variaveis_criadas)} novas variáveis criadas, {len(perguntas_existentes)} mantidas")

            return {
                "success": True,
                "schema_json": schema_final,
                "mapeamento_variaveis": mapeamento_final,
                "variaveis_criadas": variaveis_criadas,
                "variaveis_mantidas": len(perguntas_existentes),
                "modelo_id": modelo.id,
                "modelo_versao": modelo.versao,
                "modo": "incremental" if perguntas_existentes else "completo"
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

    def _injetar_dependencias_no_schema(
        self,
        schema: Dict,
        mapeamento: Dict,
        perguntas: List[ExtractionQuestion],
        namespace: str
    ) -> Dict:
        """
        Injeta dependências das perguntas no schema JSON.

        Garante que as dependências configuradas nas perguntas sejam refletidas
        no schema final, independentemente do que a IA retornou.

        Args:
            schema: Schema JSON gerado
            mapeamento: Mapeamento pergunta_id -> info da variável
            perguntas: Lista de perguntas
            namespace: Namespace da categoria

        Returns:
            Schema com dependências injetadas
        """
        # Cria mapeamento de pergunta_id -> slug no schema
        pergunta_id_to_slug = {}
        for pergunta_id, info in mapeamento.items():
            slug = info.get("slug")
            if slug:
                # Aplica namespace se necessário
                if namespace and not slug.startswith(f"{namespace}_"):
                    slug = self._aplicar_namespace(slug, namespace)
                pergunta_id_to_slug[str(pergunta_id)] = slug

        # Cria mapeamento de nome_variavel_sugerido -> slug (para resolver dependências)
        nome_sugerido_to_slug = {}
        for p in perguntas:
            if p.nome_variavel_sugerido:
                slug_info = mapeamento.get(str(p.id), {})
                slug = slug_info.get("slug")
                if slug:
                    if namespace and not slug.startswith(f"{namespace}_"):
                        slug = self._aplicar_namespace(slug, namespace)
                    nome_sugerido_to_slug[p.nome_variavel_sugerido] = slug

        # Para cada pergunta com dependência, injeta no schema
        for p in perguntas:
            if not p.depends_on_variable:
                continue

            # Encontra o slug desta pergunta no schema
            slug_pergunta = pergunta_id_to_slug.get(str(p.id))
            if not slug_pergunta or slug_pergunta not in schema:
                logger.warning(f"Pergunta {p.id} não encontrada no schema para injetar dependência")
                continue

            # Resolve o slug da variável de dependência
            depends_on_slug = p.depends_on_variable

            # Se é um nome_variavel_sugerido, converte para slug
            if depends_on_slug in nome_sugerido_to_slug:
                depends_on_slug = nome_sugerido_to_slug[depends_on_slug]
            # Se não tem namespace, aplica
            elif namespace and not depends_on_slug.startswith(f"{namespace}_"):
                depends_on_slug = self._aplicar_namespace(depends_on_slug, namespace)

            # Injeta campos de dependência no schema
            schema[slug_pergunta]["conditional"] = True
            schema[slug_pergunta]["depends_on"] = depends_on_slug
            if p.dependency_operator:
                schema[slug_pergunta]["dependency_operator"] = p.dependency_operator
            if p.dependency_value is not None:
                schema[slug_pergunta]["dependency_value"] = p.dependency_value

            logger.info(f"Dependência injetada no schema: {slug_pergunta} -> {depends_on_slug}")

        return schema

    def _injetar_opcoes_no_schema(
        self,
        schema: Dict,
        mapeamento: Dict,
        perguntas: List[ExtractionQuestion],
        namespace: str
    ) -> Dict:
        """
        Injeta opções das perguntas no schema JSON e no mapeamento.

        Garante que as opções definidas pelo usuário sejam refletidas
        no schema final e no mapeamento, independentemente do que a IA retornou.

        Args:
            schema: Schema JSON gerado
            mapeamento: Mapeamento pergunta_id -> info da variável (modificado in-place)
            perguntas: Lista de perguntas
            namespace: Namespace da categoria

        Returns:
            Schema com opções injetadas
        """
        # Cria mapeamento de pergunta_id -> slug no schema
        pergunta_id_to_slug = {}
        for pergunta_id, info in mapeamento.items():
            slug = info.get("slug")
            if slug:
                if namespace and not slug.startswith(f"{namespace}_"):
                    slug = self._aplicar_namespace(slug, namespace)
                pergunta_id_to_slug[str(pergunta_id)] = slug

        # Para cada pergunta com opções definidas, injeta no schema
        for p in perguntas:
            if not p.opcoes_sugeridas or len(p.opcoes_sugeridas) == 0:
                continue

            # Encontra o slug desta pergunta no schema
            slug_pergunta = pergunta_id_to_slug.get(str(p.id))
            if not slug_pergunta or slug_pergunta not in schema:
                logger.warning(f"Pergunta {p.id} não encontrada no schema para injetar opções")
                continue

            # Verifica se é tipo choice ou list
            tipo_atual = schema[slug_pergunta].get("type", "text")

            # Se o tipo sugerido é choice/list ou o tipo no schema é choice/list
            tipo_sugerido = p.tipo_sugerido or ""
            eh_tipo_opcoes = tipo_atual in ("choice", "list") or tipo_sugerido in ("choice", "list")

            # Se tem opções definidas e não tem opções no schema, ou se é tipo de opções
            if eh_tipo_opcoes or (p.opcoes_sugeridas and "options" not in schema[slug_pergunta]):
                # Força tipo para choice se tem opções mas tipo é text
                if tipo_atual == "text" and p.opcoes_sugeridas:
                    schema[slug_pergunta]["type"] = "choice"
                    tipo_atual = "choice"

                # Injeta opções no schema
                schema[slug_pergunta]["options"] = p.opcoes_sugeridas
                logger.info(f"Opções injetadas no schema: {slug_pergunta} -> {p.opcoes_sugeridas}")

                # Também atualiza o mapeamento para que o frontend receba as opções
                pergunta_id_str = str(p.id)
                if pergunta_id_str in mapeamento:
                    mapeamento[pergunta_id_str]["options"] = p.opcoes_sugeridas
                    mapeamento[pergunta_id_str]["tipo"] = tipo_atual

        return schema

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

    def _validar_slug(self, slug: str, namespace: str = "") -> tuple:
        """
        Valida um slug e retorna (slug_valido, erro).

        Regras:
        1. Máximo 100 caracteres
        2. Apenas letras minúsculas, números e underscore
        3. Não pode começar com número
        4. Deve ter pelo menos 3 caracteres

        Returns:
            (slug_normalizado, None) se válido
            (None, mensagem_erro) se inválido
        """
        import unicodedata

        if not slug:
            return None, "Slug vazio"

        # Remove acentos
        slug_norm = unicodedata.normalize('NFD', slug)
        slug_norm = ''.join(c for c in slug_norm if unicodedata.category(c) != 'Mn')

        # Converte para minúsculas e substitui espaços/hífens por underscore
        slug_norm = slug_norm.lower().replace(' ', '_').replace('-', '_')

        # Remove caracteres não permitidos
        slug_norm = re.sub(r'[^a-z0-9_]', '', slug_norm)

        # Remove underscores duplicados
        slug_norm = re.sub(r'_+', '_', slug_norm)

        # Remove underscores do início e fim
        slug_norm = slug_norm.strip('_')

        # Validações
        if len(slug_norm) < 3:
            return None, f"Slug muito curto: '{slug}' -> '{slug_norm}'"

        if len(slug_norm) > 100:
            # Trunca mantendo o namespace se existir
            if namespace and slug_norm.startswith(f"{namespace}_"):
                max_len = 100 - len(namespace) - 1
                slug_sem_ns = slug_norm[len(namespace)+1:][:max_len]
                slug_norm = f"{namespace}_{slug_sem_ns}"
            else:
                slug_norm = slug_norm[:100]
            logger.warning(f"Slug truncado: '{slug}' -> '{slug_norm}'")

        if slug_norm[0].isdigit():
            slug_norm = f"var_{slug_norm}"

        return slug_norm, None

    async def _criar_variaveis(
        self,
        categoria_id: int,
        mapeamento: Dict,
        perguntas: List[ExtractionQuestion]
    ) -> List[Dict]:
        """
        Cria as variáveis normalizadas no banco com namespace do grupo.

        SALVAGUARDAS:
        1. Valida e normaliza slugs antes de criar
        2. Evita duplicatas verificando slugs já criados nesta operação
        3. Limita tamanho máximo do slug a 100 caracteres
        4. Registra erros de validação sem interromper a operação
        """
        variaveis_criadas = []
        slugs_criados_nesta_operacao = set()  # Evita duplicatas na mesma operação
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
                logger.warning(f"Pergunta {pergunta_id}: slug vazio, ignorando")
                continue

            # SALVAGUARDA: Valida e normaliza o slug
            slug_validado, erro_validacao = self._validar_slug(slug_base, namespace)
            if erro_validacao:
                logger.warning(f"Pergunta {pergunta_id}: {erro_validacao}, ignorando")
                continue

            slug_base = slug_validado

            # Aplica namespace ao slug
            slug = self._aplicar_namespace(slug_base, namespace) if namespace else slug_base

            # SALVAGUARDA: Verifica se já criamos este slug nesta operação
            if slug in slugs_criados_nesta_operacao:
                logger.warning(f"Slug duplicado nesta operação: '{slug}', ignorando pergunta {pergunta_id}")
                continue

            slugs_criados_nesta_operacao.add(slug)

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
                    "atualizado": True,
                    "pergunta_id": int(pergunta_id) if pergunta_id.isdigit() else None
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
                    "criado": True,
                    "pergunta_id": int(pergunta_id) if pergunta_id.isdigit() else None
                })

        # ============================================================
        # CORREÇÃO: Atualiza nome_variavel_sugerido e tipo_sugerido
        # das perguntas para refletir os slugs/tipos gerados pela IA
        # ============================================================
        for v in variaveis_criadas:
            pergunta_id = v.get("pergunta_id")
            if pergunta_id:
                pergunta = self.db.query(ExtractionQuestion).filter(
                    ExtractionQuestion.id == pergunta_id
                ).first()
                if pergunta:
                    # Atualiza nome_variavel_sugerido com o slug base (sem namespace)
                    # para manter compatibilidade com o frontend
                    slug_base = v.get("slug_base")
                    if slug_base and pergunta.nome_variavel_sugerido != slug_base:
                        pergunta.nome_variavel_sugerido = slug_base
                        pergunta.atualizado_em = datetime.utcnow()
                        logger.info(f"Pergunta {pergunta_id}: nome_variavel_sugerido atualizado para '{slug_base}'")

                    # Atualiza tipo_sugerido se estava vazio ou como ia_decide
                    tipo_var = v.get("tipo")
                    if tipo_var and (not pergunta.tipo_sugerido or pergunta.tipo_sugerido == "ia_decide"):
                        pergunta.tipo_sugerido = tipo_var
                        logger.info(f"Pergunta {pergunta_id}: tipo_sugerido atualizado para '{tipo_var}'")

        # ============================================================
        # CORREÇÃO: Atualiza depends_on_variable das perguntas para
        # usar o slug com namespace (sincroniza pergunta ↔ variável)
        # ============================================================

        # Cria mapeamento de slug_base → slug_com_namespace
        slug_mapping = {}
        for v in variaveis_criadas:
            slug_base = v.get("slug_base")
            slug_final = v.get("slug")
            if slug_base and slug_final:
                slug_mapping[slug_base] = slug_final
                # Também mapeia o nome_variavel_sugerido das perguntas
                # (que é usado no select de dependência do frontend)

        # Busca TODAS as perguntas da categoria (incluindo as existentes)
        todas_perguntas = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.categoria_id == categoria_id,
            ExtractionQuestion.ativo == True
        ).all()

        perguntas_atualizadas = 0
        for pergunta in todas_perguntas:
            if pergunta.depends_on_variable:
                dep_original = pergunta.depends_on_variable

                # Tenta encontrar o slug com namespace correspondente
                slug_com_namespace = None

                # 1. Busca direta no mapeamento
                if dep_original in slug_mapping:
                    slug_com_namespace = slug_mapping[dep_original]
                else:
                    # 2. Tenta encontrar variável pelo nome_variavel_sugerido
                    # da pergunta que tem esse slug (busca pela pergunta âncora)
                    pergunta_ancora = self.db.query(ExtractionQuestion).filter(
                        ExtractionQuestion.categoria_id == categoria_id,
                        ExtractionQuestion.nome_variavel_sugerido == dep_original,
                        ExtractionQuestion.ativo == True
                    ).first()

                    if pergunta_ancora:
                        # Busca a variável vinculada à pergunta âncora
                        variavel_ancora = self.db.query(ExtractionVariable).filter(
                            ExtractionVariable.source_question_id == pergunta_ancora.id,
                            ExtractionVariable.ativo == True
                        ).first()

                        if variavel_ancora:
                            slug_com_namespace = variavel_ancora.slug
                    else:
                        # 3. Tenta aplicar namespace diretamente
                        if namespace and not dep_original.startswith(f"{namespace}_"):
                            slug_com_namespace = self._aplicar_namespace(dep_original, namespace)
                            # Verifica se essa variável existe
                            variavel_existe = self.db.query(ExtractionVariable).filter(
                                ExtractionVariable.slug == slug_com_namespace,
                                ExtractionVariable.ativo == True
                            ).first()
                            if not variavel_existe:
                                slug_com_namespace = None

                # Atualiza a pergunta se encontrou o slug correto
                if slug_com_namespace and slug_com_namespace != dep_original:
                    pergunta.depends_on_variable = slug_com_namespace
                    pergunta.atualizado_em = datetime.utcnow()
                    perguntas_atualizadas += 1
                    logger.info(f"Pergunta {pergunta.id}: depends_on atualizado de '{dep_original}' para '{slug_com_namespace}'")

        if perguntas_atualizadas > 0:
            logger.info(f"Total de {perguntas_atualizadas} perguntas tiveram depends_on_variable atualizado para usar namespace")

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
