# sistemas/gerador_pecas/services_slug_rename.py
"""
Servico para renomeacao transacional de slugs de variaveis.

Este servico implementa a propagacao completa de renomeacao de slugs,
garantindo que todas as referencias sejam atualizadas atomicamente:
- ExtractionVariable (fonte de verdade)
- CategoriaResumoJSON.formato_json
- ExtractionQuestion.nome_variavel_sugerido
- PromptModulo.regra_deterministica
- PromptModulo.regra_deterministica_secundaria
- RegraDeterministicaTipoPeca.regra_deterministica
- PromptVariableUsage.variable_slug
- ExtractionVariable.depends_on_variable
- ExtractionQuestion.depends_on_variable
"""

import json
import logging
import re
import unicodedata
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from sqlalchemy.orm import Session

from .models_extraction import ExtractionVariable, ExtractionQuestion, PromptVariableUsage
from .models_resumo_json import CategoriaResumoJSON

logger = logging.getLogger(__name__)


@dataclass
class SlugRenameResult:
    """Resultado da operacao de renomeacao de slug"""
    success: bool
    old_slug: str
    new_slug: str
    error: Optional[str] = None

    # Contadores de propagacao
    categoria_json_atualizada: bool = False
    perguntas_atualizadas: int = 0
    prompts_atualizados: int = 0
    regras_tipo_peca_atualizadas: int = 0
    prompt_usages_atualizados: int = 0
    variaveis_dependentes_atualizadas: int = 0
    perguntas_dependentes_atualizadas: int = 0

    # Detalhes para log
    detalhes: List[str] = field(default_factory=list)


class SlugRenameService:
    """
    Servico para renomear slugs de variaveis de forma transacional.

    A fonte de verdade do slug e a tabela ExtractionVariable.
    Ao renomear, todas as referencias sao atualizadas atomicamente.
    """

    def __init__(self, db: Session):
        self.db = db

    def _normalizar_slug(self, texto: str) -> str:
        """
        Normaliza texto para formato de slug valido.

        Exemplo: "O parecer analisou?" -> "o_parecer_analisou"
        """
        # Remove acentos
        texto = unicodedata.normalize('NFKD', texto)
        texto = texto.encode('ascii', 'ignore').decode('ascii')

        # Converte para minusculas
        texto = texto.lower()

        # Remove caracteres especiais, mantem apenas letras, numeros e underscores
        texto = re.sub(r'[^a-z0-9_]', '_', texto)

        # Remove underscores multiplos
        texto = re.sub(r'_+', '_', texto)

        # Remove underscores no inicio e fim
        texto = texto.strip('_')

        # Limita tamanho
        return texto[:100]

    def _validar_novo_slug(self, novo_slug: str, variavel_id: int) -> Optional[str]:
        """
        Valida se o novo slug e valido e unico.

        Returns:
            None se valido, mensagem de erro se invalido
        """
        # Valida formato basico
        if not novo_slug:
            return "Novo slug nao pode ser vazio"

        # Permite letras maiusculas e minusculas (case-insensitive)
        # Regex aceita: letras (a-z, A-Z), numeros, underscores
        # Deve comecar com letra
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', novo_slug):
            return "Slug deve comecar com letra e conter apenas letras, numeros e underscores"

        if len(novo_slug) < 3:
            return "Slug deve ter pelo menos 3 caracteres"

        if len(novo_slug) > 100:
            return "Slug deve ter no maximo 100 caracteres"

        # Verifica unicidade entre variaveis ativas
        existente = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.slug == novo_slug,
            ExtractionVariable.ativo == True,
            ExtractionVariable.id != variavel_id
        ).first()

        if existente:
            return f"Ja existe uma variavel ativa com o slug '{novo_slug}'"

        return None

    def _atualizar_regra_recursivo(self, regra: Dict[str, Any], old_slug: str, new_slug: str) -> Tuple[Dict[str, Any], int]:
        """
        Atualiza referencias ao slug em uma regra deterministica (AST JSON) recursivamente.

        Returns:
            Tuple[regra_atualizada, quantidade_de_substituicoes]
        """
        if not regra or not isinstance(regra, dict):
            return regra, 0

        count = 0
        regra_copy = regra.copy()

        tipo = regra_copy.get("type")

        if tipo == "condition":
            # Noh condicional - verifica campo variable
            if regra_copy.get("variable") == old_slug:
                regra_copy["variable"] = new_slug
                count += 1

        elif tipo in ("and", "or"):
            # Noh composto - processa filhos
            conditions = regra_copy.get("conditions", [])
            new_conditions = []
            for cond in conditions:
                updated_cond, sub_count = self._atualizar_regra_recursivo(cond, old_slug, new_slug)
                new_conditions.append(updated_cond)
                count += sub_count
            regra_copy["conditions"] = new_conditions

        elif tipo == "not":
            # Noh de negacao - processa filho
            if "condition" in regra_copy:
                updated_cond, sub_count = self._atualizar_regra_recursivo(
                    regra_copy["condition"], old_slug, new_slug
                )
                regra_copy["condition"] = updated_cond
                count += sub_count

        return regra_copy, count

    def _propagar_para_json_categoria(self, variavel: ExtractionVariable, old_slug: str, new_slug: str, result: SlugRenameResult) -> None:
        """Propaga renomeacao para o JSON da categoria"""
        if not variavel.categoria_id:
            return

        categoria = self.db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.id == variavel.categoria_id
        ).first()

        if not categoria or not categoria.formato_json:
            return

        try:
            schema = json.loads(categoria.formato_json)

            if old_slug in schema:
                # Move o valor para a nova chave
                schema[new_slug] = schema.pop(old_slug)
                categoria.formato_json = json.dumps(schema, ensure_ascii=False, indent=2)
                categoria.atualizado_em = datetime.utcnow()
                result.categoria_json_atualizada = True
                result.detalhes.append(f"JSON da categoria '{categoria.nome}' atualizado")
                logger.info(f"[SLUG-RENAME] JSON categoria {categoria.id} atualizado: {old_slug} -> {new_slug}")
        except json.JSONDecodeError as e:
            logger.warning(f"[SLUG-RENAME] Erro ao parsear JSON da categoria {categoria.id}: {e}")

    def _propagar_para_pergunta(self, variavel: ExtractionVariable, old_slug: str, new_slug: str, result: SlugRenameResult) -> None:
        """Propaga renomeacao para a pergunta de origem"""
        if not variavel.source_question_id:
            return

        pergunta = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.id == variavel.source_question_id
        ).first()

        if pergunta and pergunta.nome_variavel_sugerido == old_slug:
            pergunta.nome_variavel_sugerido = new_slug
            pergunta.atualizado_em = datetime.utcnow()
            result.perguntas_atualizadas += 1
            result.detalhes.append(f"Pergunta id={pergunta.id} atualizada")

    def _propagar_para_prompts(self, old_slug: str, new_slug: str, result: SlugRenameResult) -> None:
        """Propaga renomeacao para prompts modulares"""
        from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca

        # Busca todos os prompts que podem ter regras usando este slug
        prompts = self.db.query(PromptModulo).filter(
            PromptModulo.ativo == True
        ).all()

        for prompt in prompts:
            atualizado = False

            # Atualiza regra primaria
            if prompt.regra_deterministica:
                nova_regra, count = self._atualizar_regra_recursivo(
                    prompt.regra_deterministica, old_slug, new_slug
                )
                if count > 0:
                    prompt.regra_deterministica = nova_regra
                    atualizado = True

            # Atualiza regra secundaria
            if prompt.regra_deterministica_secundaria:
                nova_regra, count = self._atualizar_regra_recursivo(
                    prompt.regra_deterministica_secundaria, old_slug, new_slug
                )
                if count > 0:
                    prompt.regra_deterministica_secundaria = nova_regra
                    atualizado = True

            if atualizado:
                prompt.atualizado_em = datetime.utcnow()
                result.prompts_atualizados += 1
                result.detalhes.append(f"Prompt '{prompt.nome}' (id={prompt.id}) atualizado")
                logger.info(f"[SLUG-RENAME] Prompt {prompt.id} atualizado: {old_slug} -> {new_slug}")

        # Atualiza regras por tipo de peca
        regras_tipo_peca = self.db.query(RegraDeterministicaTipoPeca).filter(
            RegraDeterministicaTipoPeca.ativo == True
        ).all()

        for regra in regras_tipo_peca:
            if regra.regra_deterministica:
                nova_regra, count = self._atualizar_regra_recursivo(
                    regra.regra_deterministica, old_slug, new_slug
                )
                if count > 0:
                    regra.regra_deterministica = nova_regra
                    regra.atualizado_em = datetime.utcnow()
                    result.regras_tipo_peca_atualizadas += 1
                    result.detalhes.append(
                        f"Regra tipo_peca '{regra.tipo_peca}' do modulo {regra.modulo_id} atualizada"
                    )
                    logger.info(f"[SLUG-RENAME] Regra tipo_peca {regra.id} atualizada: {old_slug} -> {new_slug}")

    def _propagar_para_prompt_usages(self, old_slug: str, new_slug: str, result: SlugRenameResult) -> None:
        """Propaga renomeacao para PromptVariableUsage"""
        usages = self.db.query(PromptVariableUsage).filter(
            PromptVariableUsage.variable_slug == old_slug
        ).all()

        for usage in usages:
            usage.variable_slug = new_slug
            result.prompt_usages_atualizados += 1

        if usages:
            result.detalhes.append(f"{len(usages)} PromptVariableUsage atualizados")
            logger.info(f"[SLUG-RENAME] {len(usages)} PromptVariableUsage atualizados: {old_slug} -> {new_slug}")

    def _atualizar_dependency_config(self, config: Dict[str, Any], old_slug: str, new_slug: str) -> Tuple[Dict[str, Any], bool]:
        """
        Atualiza referencias ao slug em dependency_config (JSON complexo).

        Returns:
            Tuple[config_atualizado, foi_modificado]
        """
        if not config or not isinstance(config, dict):
            return config, False

        modificado = False
        config_copy = json.loads(json.dumps(config))  # Deep copy

        # Verifica campo 'variable' direto
        if config_copy.get("variable") == old_slug:
            config_copy["variable"] = new_slug
            modificado = True

        # Verifica array de conditions
        if "conditions" in config_copy and isinstance(config_copy["conditions"], list):
            for i, cond in enumerate(config_copy["conditions"]):
                if isinstance(cond, dict):
                    updated_cond, cond_modified = self._atualizar_dependency_config(cond, old_slug, new_slug)
                    if cond_modified:
                        config_copy["conditions"][i] = updated_cond
                        modificado = True

        return config_copy, modificado

    def _propagar_para_dependencias(self, old_slug: str, new_slug: str, result: SlugRenameResult) -> None:
        """Propaga renomeacao para dependencias de outras variaveis e perguntas"""
        # Atualiza variaveis que dependem desta
        variaveis_dependentes = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.depends_on_variable == old_slug
        ).all()

        for var in variaveis_dependentes:
            var.depends_on_variable = new_slug
            var.atualizado_em = datetime.utcnow()
            result.variaveis_dependentes_atualizadas += 1

            # Atualiza dependency_config se existir
            if var.dependency_config:
                updated_config, modificado = self._atualizar_dependency_config(
                    var.dependency_config, old_slug, new_slug
                )
                if modificado:
                    var.dependency_config = updated_config

        if variaveis_dependentes:
            result.detalhes.append(f"{len(variaveis_dependentes)} variaveis dependentes atualizadas")

        # Atualiza perguntas que dependem desta variavel
        perguntas_dependentes = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.depends_on_variable == old_slug
        ).all()

        for perg in perguntas_dependentes:
            perg.depends_on_variable = new_slug
            perg.atualizado_em = datetime.utcnow()
            result.perguntas_dependentes_atualizadas += 1

            # Atualiza dependency_config se existir
            if perg.dependency_config:
                updated_config, modificado = self._atualizar_dependency_config(
                    perg.dependency_config, old_slug, new_slug
                )
                if modificado:
                    perg.dependency_config = updated_config

        if perguntas_dependentes:
            result.detalhes.append(f"{len(perguntas_dependentes)} perguntas dependentes atualizadas")

        # Tambem busca variaveis/perguntas que tem o slug no dependency_config
        # mas nao no depends_on_variable (casos de config complexa)
        self._propagar_para_dependency_configs_complexos(old_slug, new_slug, result)

    def _propagar_para_dependency_configs_complexos(self, old_slug: str, new_slug: str, result: SlugRenameResult) -> None:
        """
        Busca e atualiza dependency_config que contem o slug em formato JSON complexo.

        Casos onde depends_on_variable pode ser diferente mas o slug aparece em conditions.
        """
        # Busca variaveis com dependency_config que pode conter o slug
        # Nota: Busca por LIKE no JSON (funciona para SQLite e PostgreSQL)
        variaveis_com_config = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.dependency_config.isnot(None),
            ExtractionVariable.depends_on_variable != old_slug  # Ja processamos acima
        ).all()

        for var in variaveis_com_config:
            if var.dependency_config:
                config_str = json.dumps(var.dependency_config)
                if old_slug in config_str:
                    updated_config, modificado = self._atualizar_dependency_config(
                        var.dependency_config, old_slug, new_slug
                    )
                    if modificado:
                        var.dependency_config = updated_config
                        var.atualizado_em = datetime.utcnow()
                        logger.info(f"[SLUG-RENAME] dependency_config de variavel {var.id} atualizado")

        # Busca perguntas com dependency_config complexo
        perguntas_com_config = self.db.query(ExtractionQuestion).filter(
            ExtractionQuestion.dependency_config.isnot(None),
            ExtractionQuestion.depends_on_variable != old_slug  # Ja processamos acima
        ).all()

        for perg in perguntas_com_config:
            if perg.dependency_config:
                config_str = json.dumps(perg.dependency_config)
                if old_slug in config_str:
                    updated_config, modificado = self._atualizar_dependency_config(
                        perg.dependency_config, old_slug, new_slug
                    )
                    if modificado:
                        perg.dependency_config = updated_config
                        perg.atualizado_em = datetime.utcnow()
                        logger.info(f"[SLUG-RENAME] dependency_config de pergunta {perg.id} atualizado")

    def renomear(
        self,
        variavel_id: int,
        novo_slug: str,
        normalizar: bool = True,
        skip_pergunta: bool = False
    ) -> SlugRenameResult:
        """
        Renomeia o slug de uma variavel de forma transacional.

        Args:
            variavel_id: ID da variavel a renomear
            novo_slug: Novo slug desejado
            normalizar: Se True, normaliza o novo slug (remove acentos, etc)
            skip_pergunta: Se True, nao atualiza a pergunta de origem (usado quando
                           a renomeacao vem da propria pergunta que ja foi atualizada)

        Returns:
            SlugRenameResult com detalhes da operacao
        """
        # Busca a variavel
        variavel = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.id == variavel_id
        ).first()

        if not variavel:
            return SlugRenameResult(
                success=False,
                old_slug="",
                new_slug=novo_slug,
                error="Variavel nao encontrada"
            )

        old_slug = variavel.slug

        # Normaliza se solicitado
        if normalizar:
            novo_slug = self._normalizar_slug(novo_slug)

        # Se o slug e o mesmo, nada a fazer
        if old_slug == novo_slug:
            return SlugRenameResult(
                success=True,
                old_slug=old_slug,
                new_slug=novo_slug,
                detalhes=["Nenhuma alteracao necessaria - slug ja e o mesmo"]
            )

        # Valida novo slug
        erro_validacao = self._validar_novo_slug(novo_slug, variavel_id)
        if erro_validacao:
            return SlugRenameResult(
                success=False,
                old_slug=old_slug,
                new_slug=novo_slug,
                error=erro_validacao
            )

        result = SlugRenameResult(
            success=True,
            old_slug=old_slug,
            new_slug=novo_slug
        )

        try:
            logger.info(f"[SLUG-RENAME] Iniciando renomeacao: {old_slug} -> {novo_slug}")

            # 1. Atualiza a variavel (fonte de verdade)
            variavel.slug = novo_slug
            variavel.atualizado_em = datetime.utcnow()
            result.detalhes.append(f"Variavel id={variavel.id} atualizada")

            # 2. Propaga para JSON da categoria
            self._propagar_para_json_categoria(variavel, old_slug, novo_slug, result)

            # 3. Propaga para pergunta de origem (se nao foi skip)
            if not skip_pergunta:
                self._propagar_para_pergunta(variavel, old_slug, novo_slug, result)

            # 4. Propaga para prompts e regras
            self._propagar_para_prompts(old_slug, novo_slug, result)

            # 5. Propaga para PromptVariableUsage
            self._propagar_para_prompt_usages(old_slug, novo_slug, result)

            # 6. Propaga para dependencias
            self._propagar_para_dependencias(old_slug, novo_slug, result)

            # Flush para garantir que nao ha erros antes do commit
            self.db.flush()

            logger.info(
                f"[SLUG-RENAME] Concluido: {old_slug} -> {novo_slug} "
                f"(categoria_json={result.categoria_json_atualizada}, "
                f"prompts={result.prompts_atualizados}, "
                f"regras_tipo_peca={result.regras_tipo_peca_atualizadas})"
            )

        except Exception as e:
            logger.error(f"[SLUG-RENAME] Erro durante renomeacao: {e}")
            result.success = False
            result.error = str(e)
            # Nao faz rollback aqui - deixa para o chamador decidir

        return result


class SlugConsistencyChecker:
    """
    Servico para verificar e reparar inconsistencias entre slugs.
    """

    def __init__(self, db: Session):
        self.db = db

    def verificar_categoria(self, categoria_id: int) -> Dict[str, Any]:
        """
        Verifica consistencia entre JSON da categoria e variaveis.

        Returns:
            Dict com:
            - consistente: bool
            - slugs_no_json: set de slugs presentes no JSON
            - slugs_variaveis: set de slugs de variaveis ativas
            - slugs_orfaos_json: slugs no JSON sem variavel correspondente
            - slugs_orfaos_variaveis: variaveis sem entrada no JSON
        """
        categoria = self.db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.id == categoria_id
        ).first()

        if not categoria:
            return {
                "consistente": False,
                "erro": "Categoria nao encontrada"
            }

        # Extrai slugs do JSON
        slugs_no_json = set()
        if categoria.formato_json:
            try:
                schema = json.loads(categoria.formato_json)
                slugs_no_json = set(schema.keys())
            except json.JSONDecodeError:
                return {
                    "consistente": False,
                    "erro": "JSON da categoria invalido"
                }

        # Busca variaveis ativas da categoria
        variaveis = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.categoria_id == categoria_id,
            ExtractionVariable.ativo == True
        ).all()

        slugs_variaveis = {v.slug for v in variaveis}

        # Calcula diferencas
        slugs_orfaos_json = slugs_no_json - slugs_variaveis
        slugs_orfaos_variaveis = slugs_variaveis - slugs_no_json

        return {
            "consistente": len(slugs_orfaos_json) == 0 and len(slugs_orfaos_variaveis) == 0,
            "categoria_id": categoria_id,
            "categoria_nome": categoria.nome,
            "total_slugs_json": len(slugs_no_json),
            "total_variaveis_ativas": len(slugs_variaveis),
            "slugs_no_json": list(slugs_no_json),
            "slugs_variaveis": list(slugs_variaveis),
            "slugs_orfaos_json": list(slugs_orfaos_json),
            "slugs_orfaos_variaveis": list(slugs_orfaos_variaveis),
            "mensagem": (
                "Consistente" if len(slugs_orfaos_json) == 0 and len(slugs_orfaos_variaveis) == 0
                else f"{len(slugs_orfaos_json)} slugs no JSON sem variavel, {len(slugs_orfaos_variaveis)} variaveis sem entrada no JSON"
            )
        }

    def verificar_referencias_prompts(self, slug: str) -> Dict[str, Any]:
        """
        Verifica se um slug esta sendo usado em regras deterministicas.

        Returns:
            Dict com lista de prompts e regras que usam este slug
        """
        from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca

        prompts_usando = []
        regras_tipo_peca_usando = []

        # Verifica PromptModulo
        prompts = self.db.query(PromptModulo).filter(
            PromptModulo.ativo == True
        ).all()

        for prompt in prompts:
            usa_slug = False

            # Verifica regra primaria
            if prompt.regra_deterministica:
                if self._regra_usa_slug(prompt.regra_deterministica, slug):
                    usa_slug = True

            # Verifica regra secundaria
            if prompt.regra_deterministica_secundaria:
                if self._regra_usa_slug(prompt.regra_deterministica_secundaria, slug):
                    usa_slug = True

            if usa_slug:
                prompts_usando.append({
                    "id": prompt.id,
                    "nome": prompt.nome,
                    "titulo": prompt.titulo
                })

        # Verifica RegraDeterministicaTipoPeca
        regras = self.db.query(RegraDeterministicaTipoPeca).filter(
            RegraDeterministicaTipoPeca.ativo == True
        ).all()

        for regra in regras:
            if regra.regra_deterministica and self._regra_usa_slug(regra.regra_deterministica, slug):
                regras_tipo_peca_usando.append({
                    "id": regra.id,
                    "modulo_id": regra.modulo_id,
                    "tipo_peca": regra.tipo_peca
                })

        return {
            "slug": slug,
            "total_prompts": len(prompts_usando),
            "total_regras_tipo_peca": len(regras_tipo_peca_usando),
            "prompts": prompts_usando,
            "regras_tipo_peca": regras_tipo_peca_usando
        }

    def _regra_usa_slug(self, regra: Dict[str, Any], slug: str) -> bool:
        """Verifica recursivamente se uma regra usa determinado slug"""
        if not regra or not isinstance(regra, dict):
            return False

        tipo = regra.get("type")

        if tipo == "condition":
            return regra.get("variable") == slug

        elif tipo in ("and", "or"):
            for cond in regra.get("conditions", []):
                if self._regra_usa_slug(cond, slug):
                    return True

        elif tipo == "not":
            return self._regra_usa_slug(regra.get("condition"), slug)

        return False

    def reparar_categoria(self, categoria_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Repara inconsistencias de uma categoria.

        Acoes:
        1. Remove do JSON slugs que nao tem variavel correspondente
        2. Adiciona ao JSON variaveis que estao faltando

        Returns:
            Dict com detalhes das correcoes
        """
        verificacao = self.verificar_categoria(categoria_id)

        if verificacao.get("erro"):
            return verificacao

        if verificacao["consistente"]:
            return {
                "success": True,
                "mensagem": "Categoria ja esta consistente",
                "correcoes": []
            }

        categoria = self.db.query(CategoriaResumoJSON).filter(
            CategoriaResumoJSON.id == categoria_id
        ).first()

        correcoes = []

        try:
            schema = json.loads(categoria.formato_json) if categoria.formato_json else {}

            # Remove slugs orfaos do JSON
            for slug in verificacao["slugs_orfaos_json"]:
                del schema[slug]
                correcoes.append(f"Removido do JSON: {slug}")

            # Adiciona variaveis faltantes ao JSON
            for slug in verificacao["slugs_orfaos_variaveis"]:
                variavel = self.db.query(ExtractionVariable).filter(
                    ExtractionVariable.slug == slug,
                    ExtractionVariable.ativo == True
                ).first()

                if variavel:
                    schema[slug] = {
                        "type": variavel.tipo or "text",
                        "description": variavel.descricao or variavel.label
                    }
                    correcoes.append(f"Adicionado ao JSON: {slug}")

            # Salva JSON atualizado
            categoria.formato_json = json.dumps(schema, ensure_ascii=False, indent=2)
            categoria.atualizado_em = datetime.utcnow()
            if user_id:
                categoria.atualizado_por = user_id

            self.db.flush()

            logger.info(f"[SLUG-CONSISTENCY] Categoria {categoria_id} reparada: {len(correcoes)} correcoes")

            return {
                "success": True,
                "categoria_id": categoria_id,
                "correcoes_aplicadas": len(correcoes),
                "correcoes": correcoes
            }

        except Exception as e:
            logger.error(f"[SLUG-CONSISTENCY] Erro ao reparar categoria {categoria_id}: {e}")
            return {
                "success": False,
                "erro": str(e)
            }
