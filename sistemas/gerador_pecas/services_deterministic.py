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


# Modelo padrão (pode ser sobrescrito por config do banco)
GEMINI_MODEL_DEFAULT = "gemini-3-flash-preview"


# ==============================================================================
# REGRA DE OURO DO SISTEMA: RESOLUÇÃO AUTOMÁTICA DO MODO DE ATIVAÇÃO
# ==============================================================================
#
# INVARIANTE: Se existe QUALQUER regra determinística associada a um módulo,
# o módulo DEVE operar em modo 'deterministic', INDEPENDENTE do valor salvo
# no campo modo_ativacao.
#
# Esta garantia é implementada em TRÊS níveis:
# 1. RUNTIME: resolve_activation_mode() é chamada antes de toda avaliação
# 2. PERSISTÊNCIA: ao salvar/atualizar módulos, o modo é forçado corretamente
# 3. CORREÇÃO: corrigir_modos_ativacao_inconsistentes() corrige dados legados
#
# NUNCA confie no campo modo_ativacao do banco - sempre use resolve_activation_mode()
# ==============================================================================


def tem_regras_deterministicas(
    regra_primaria: Optional[Dict] = None,
    regra_secundaria: Optional[Dict] = None,
    fallback_habilitado: bool = False,
    regras_tipo_peca: Optional[List[Dict]] = None
) -> bool:
    """
    Verifica se existe pelo menos UMA regra determinística configurada.

    Esta função verifica TODAS as possíveis fontes de regras:
    - Regra global primária
    - Regra global secundária (fallback)
    - Regras específicas por tipo de peça

    Args:
        regra_primaria: Regra determinística primária (AST JSON)
        regra_secundaria: Regra determinística secundária/fallback
        fallback_habilitado: Se o fallback está habilitado
        regras_tipo_peca: Lista de regras específicas por tipo de peça

    Returns:
        True se existir pelo menos uma regra, False caso contrário
    """
    # Verifica regra primária
    if regra_primaria and isinstance(regra_primaria, dict) and regra_primaria.get("type"):
        return True

    # Verifica regra secundária (apenas se fallback habilitado)
    if fallback_habilitado and regra_secundaria and isinstance(regra_secundaria, dict) and regra_secundaria.get("type"):
        return True

    # Verifica regras por tipo de peça
    if regras_tipo_peca:
        for regra in regras_tipo_peca:
            if regra and isinstance(regra, dict):
                # Pode ser o objeto completo com 'regra_deterministica' ou a regra direta
                regra_det = regra.get("regra_deterministica", regra)
                if regra_det and isinstance(regra_det, dict) and regra_det.get("type"):
                    return True

    return False


def resolve_activation_mode(
    modo_ativacao_salvo: str,
    regra_primaria: Optional[Dict] = None,
    regra_secundaria: Optional[Dict] = None,
    fallback_habilitado: bool = False,
    regras_tipo_peca: Optional[List[Dict]] = None,
    log_correcao: bool = True
) -> str:
    """
    FONTE ÚNICA DE VERDADE para o modo de ativação de um módulo.

    REGRA DE OURO: Se existe qualquer regra determinística, o modo DEVE ser 'deterministic'.

    Esta função IGNORA o valor salvo no banco quando há regras configuradas,
    garantindo que o sistema SEMPRE opere corretamente independente de:
    - Edições manuais no banco
    - Seeds ou imports incorretos
    - Bugs em versões anteriores
    - Configurações inconsistentes

    Args:
        modo_ativacao_salvo: Valor do campo modo_ativacao no banco
        regra_primaria: Regra determinística primária (AST JSON)
        regra_secundaria: Regra determinística secundária/fallback
        fallback_habilitado: Se o fallback está habilitado
        regras_tipo_peca: Lista de regras específicas por tipo de peça
        log_correcao: Se deve logar quando corrigir o modo

    Returns:
        Modo de ativação CORRETO: 'deterministic' se há regras, senão o valor salvo
    """
    # Verifica se existem regras
    existe_regra = tem_regras_deterministicas(
        regra_primaria=regra_primaria,
        regra_secundaria=regra_secundaria,
        fallback_habilitado=fallback_habilitado,
        regras_tipo_peca=regras_tipo_peca
    )

    # REGRA DE OURO: se há regra, modo DEVE ser 'deterministic'
    if existe_regra:
        if modo_ativacao_salvo != "deterministic" and log_correcao:
            logger.warning(
                f"[REGRA-DE-OURO] Modo de ativação corrigido: '{modo_ativacao_salvo}' -> 'deterministic' "
                f"(regras determinísticas detectadas)"
            )
        return "deterministic"

    # Sem regras: respeita o valor salvo (default para 'llm')
    return modo_ativacao_salvo or "llm"


def resolve_activation_mode_from_db(
    db: Session,
    modulo_id: int,
    modo_ativacao_salvo: Optional[str] = None,
    regra_primaria: Optional[Dict] = None,
    regra_secundaria: Optional[Dict] = None,
    fallback_habilitado: bool = False
) -> str:
    """
    Resolve o modo de ativação buscando também regras por tipo de peça no banco.

    Esta versão consulta o banco para verificar regras específicas por tipo de peça,
    garantindo que módulos com regras apenas em tipos específicos também sejam
    detectados como determinísticos.

    Args:
        db: Sessão do banco de dados
        modulo_id: ID do módulo
        modo_ativacao_salvo: Valor salvo (opcional, busca do banco se não fornecido)
        regra_primaria: Regra primária (opcional, busca do banco se não fornecido)
        regra_secundaria: Regra secundária (opcional)
        fallback_habilitado: Se fallback está habilitado

    Returns:
        Modo de ativação CORRETO
    """
    try:
        from admin.models_prompts import RegraDeterministicaTipoPeca

        # Busca regras específicas por tipo de peça ativas
        regras_tipo_peca = db.query(RegraDeterministicaTipoPeca).filter(
            RegraDeterministicaTipoPeca.modulo_id == modulo_id,
            RegraDeterministicaTipoPeca.ativo == True
        ).all()

        # Converte para lista de dicts
        regras_tipo_peca_dicts = [
            {"regra_deterministica": r.regra_deterministica, "tipo_peca": r.tipo_peca}
            for r in regras_tipo_peca
            if r.regra_deterministica
        ]

        return resolve_activation_mode(
            modo_ativacao_salvo=modo_ativacao_salvo or "llm",
            regra_primaria=regra_primaria,
            regra_secundaria=regra_secundaria,
            fallback_habilitado=fallback_habilitado,
            regras_tipo_peca=regras_tipo_peca_dicts if regras_tipo_peca_dicts else None
        )

    except Exception as e:
        logger.error(f"Erro ao resolver modo de ativação do módulo {modulo_id}: {e}")
        # Em caso de erro, usa resolução básica
        return resolve_activation_mode(
            modo_ativacao_salvo=modo_ativacao_salvo or "llm",
            regra_primaria=regra_primaria,
            regra_secundaria=regra_secundaria,
            fallback_habilitado=fallback_habilitado
        )


def corrigir_modos_ativacao_inconsistentes(db: Session, commit: bool = True) -> Dict[str, Any]:
    """
    Corrige TODOS os módulos com modo de ativação inconsistente.

    Esta função deve ser chamada:
    - No startup da aplicação
    - Após migrações
    - Manualmente via endpoint de administração

    Garante que dados legados ou corrompidos sejam corrigidos automaticamente.

    Args:
        db: Sessão do banco de dados
        commit: Se deve fazer commit das alterações

    Returns:
        Dict com estatísticas da correção
    """
    try:
        from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca

        corrigidos = []
        verificados = 0

        # Busca todos os módulos
        modulos = db.query(PromptModulo).all()

        for modulo in modulos:
            verificados += 1

            # Busca regras por tipo de peça
            regras_tipo_peca = db.query(RegraDeterministicaTipoPeca).filter(
                RegraDeterministicaTipoPeca.modulo_id == modulo.id,
                RegraDeterministicaTipoPeca.ativo == True
            ).all()

            regras_tipo_peca_dicts = [
                {"regra_deterministica": r.regra_deterministica}
                for r in regras_tipo_peca
                if r.regra_deterministica
            ]

            # Resolve o modo correto
            modo_correto = resolve_activation_mode(
                modo_ativacao_salvo=modulo.modo_ativacao,
                regra_primaria=modulo.regra_deterministica,
                regra_secundaria=modulo.regra_deterministica_secundaria,
                fallback_habilitado=modulo.fallback_habilitado or False,
                regras_tipo_peca=regras_tipo_peca_dicts if regras_tipo_peca_dicts else None,
                log_correcao=False  # Vamos logar abaixo de forma consolidada
            )

            # Se há inconsistência, corrige
            if modulo.modo_ativacao != modo_correto:
                corrigidos.append({
                    "id": modulo.id,
                    "nome": modulo.nome,
                    "modo_anterior": modulo.modo_ativacao,
                    "modo_novo": modo_correto,
                    "tem_regra_primaria": bool(modulo.regra_deterministica),
                    "tem_regra_secundaria": bool(modulo.regra_deterministica_secundaria and modulo.fallback_habilitado),
                    "tem_regras_tipo_peca": len(regras_tipo_peca_dicts) > 0
                })

                modulo.modo_ativacao = modo_correto

        if commit and corrigidos:
            db.commit()

        # Log consolidado
        if corrigidos:
            logger.warning(
                f"[REGRA-DE-OURO] Corrigidos {len(corrigidos)} módulos com modo de ativação inconsistente: "
                f"{[c['nome'] for c in corrigidos]}"
            )
        else:
            logger.info(f"[REGRA-DE-OURO] Verificados {verificados} módulos - nenhuma inconsistência encontrada")

        return {
            "verificados": verificados,
            "corrigidos": len(corrigidos),
            "detalhes": corrigidos
        }

    except Exception as e:
        logger.error(f"Erro ao corrigir modos de ativação: {e}")
        return {
            "verificados": 0,
            "corrigidos": 0,
            "erro": str(e)
        }


def _get_config_sistemas_acessorios(db: Session, chave: str, default: Any = None) -> Any:
    """
    Busca configuração do sistema 'sistemas_acessorios' no banco.

    Args:
        db: Sessão do banco
        chave: Nome da configuração (ex: 'gerador_regras_modelo')
        default: Valor padrão se não encontrado

    Returns:
        Valor da configuração ou default
    """
    try:
        from admin.models import ConfiguracaoIA
        config = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == "sistemas_acessorios",
            ConfiguracaoIA.chave == chave
        ).first()

        if config and config.valor:
            return config.valor
        return default
    except Exception as e:
        logger.warning(f"Erro ao buscar config '{chave}': {e}")
        return default


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

            # Log detalhado das variáveis disponíveis para diagnóstico
            slugs_disponiveis = [v['slug'] for v in variaveis_disponiveis]
            vars_sistema = [v for v in variaveis_disponiveis if v.get('fonte') == 'processo_sistema']
            slugs_sistema = [v['slug'] for v in vars_sistema]

            logger.info(
                f"[REGRA-DETERMINISTICO] Variáveis disponíveis: {len(variaveis_disponiveis)} total"
            )
            logger.info(
                f"[REGRA-DETERMINISTICO] Variáveis de SISTEMA incluídas: {len(vars_sistema)} - "
                f"Slugs: {slugs_sistema}"
            )

            # 2. Monta prompt para a IA
            prompt = self._montar_prompt_geracao(
                condicao_texto,
                variaveis_disponiveis,
                contexto
            )

            # 3. Chama o Gemini
            logger.info(f"Gerando regra determinística: '{condicao_texto[:100]}...'")

            # Busca configurações do banco (sistema "sistemas_acessorios")
            # Se não houver config, usa valores padrão conservadores
            modelo = _get_config_sistemas_acessorios(
                self.db, "gerador_regras_modelo", GEMINI_MODEL_DEFAULT
            )
            thinking_level = _get_config_sistemas_acessorios(
                self.db, "gerador_regras_thinking_level", "low"  # Padrão: LOW para ser direto
            )
            temperatura_str = _get_config_sistemas_acessorios(
                self.db, "gerador_regras_temperatura", "0.1"
            )
            try:
                temperatura = float(temperatura_str)
            except (ValueError, TypeError):
                temperatura = 0.1

            logger.info(
                f"[REGRA-DETERMINISTICO] Config: modelo={modelo}, "
                f"thinking_level={thinking_level}, temperatura={temperatura}"
            )

            response = await gemini_service.generate(
                prompt=prompt,
                system_prompt=self._get_system_prompt(),
                model=modelo,
                temperature=temperatura,
                thinking_level=thinking_level if thinking_level else None,
                context={
                    "sistema": "extracao",
                    "modulo": "regras_deterministicas",
                    "operacao": "gerar_regra"
                }
            )

            if not response.success:
                logger.error(f"Erro na chamada Gemini: {response.error}")
                return {"success": False, "erro": f"Erro na IA: {response.error}"}

            # Log da resposta bruta para diagnóstico
            logger.info(f"[REGRA-DETERMINISTICO] Resposta IA (primeiros 500 chars): {response.content[:500]}")

            # 4. Parseia a resposta JSON
            resultado = self._extrair_json_resposta(response.content)

            if not resultado:
                logger.error(f"Resposta IA não é JSON válido: {response.content[:500]}")
                return {"success": False, "erro": "A IA não retornou um JSON válido"}

            # 4.1 Verifica se IA indicou variáveis insuficientes
            if resultado.get("erro") == "variaveis_insuficientes":
                logger.warning(
                    f"[REGRA-DETERMINISTICO] IA indicou variáveis insuficientes. "
                    f"Condição: '{condicao_texto}'. "
                    f"Total variáveis disponíveis: {len(slugs_disponiveis)}. "
                    f"Variáveis de SISTEMA disponíveis: {slugs_sistema}. "
                    f"Mensagem IA: {resultado.get('mensagem')}. "
                    f"Variáveis necessárias sugeridas: {resultado.get('variaveis_necessarias')}"
                )
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
                logger.warning(
                    f"[REGRA-DETERMINISTICO] Regra inválida. "
                    f"Erros: {validacao['errors']}. "
                    f"Variáveis faltantes: {validacao.get('variaveis_faltantes')}"
                )
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
    "variable": "valor_causa_numerico",
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

6. "Valor da causa igual ou superior a 210 salários mínimos" (usa variável booleana pré-calculada)
{
    "type": "condition",
    "variable": "valor_causa_superior_210sm",
    "operator": "equals",
    "value": true
}

7. "Valor da causa inferior a 60 salários mínimos" (usa variável booleana pré-calculada)
{
    "type": "condition",
    "variable": "valor_causa_inferior_60sm",
    "operator": "equals",
    "value": true
}

8. "A União está no polo passivo" (usa variável do grupo Sistema)
{
    "type": "condition",
    "variable": "uniao_polo_passivo",
    "operator": "equals",
    "value": true
}

9. "Município no polo passivo e valor da causa superior a 210 SM"
{
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "municipio_polo_passivo", "operator": "equals", "value": true},
        {"type": "condition", "variable": "valor_causa_superior_210sm", "operator": "equals", "value": true}
    ]
}

10. "Parecer do NAT analisou medicamento não incorporado E valor >= 210 SM E União não está no polo passivo E ajuizado após 19/09/2024"
{
    "type": "and",
    "conditions": [
        {"type": "condition", "variable": "pareceres_medicamento_nao_incorporado_sus", "operator": "equals", "value": true},
        {"type": "condition", "variable": "valor_causa_superior_210sm", "operator": "equals", "value": true},
        {"type": "condition", "variable": "uniao_polo_passivo", "operator": "equals", "value": false},
        {"type": "condition", "variable": "processo_ajuizado_apos_2024_09_19", "operator": "equals", "value": true}
    ]
}

IMPORTANTE - VARIÁVEIS DO GRUPO "SISTEMA" (PRÉ-CALCULADAS):
Estas variáveis são calculadas automaticamente a partir do processo e SEMPRE existem:
- processo_ajuizado_apos_2024_09_19: TRUE se ajuizado APÓS 19/09/2024
- valor_causa_numerico: Valor da causa como número (float)
- valor_causa_inferior_60sm: TRUE se valor < 60 salários mínimos (R$ 97.260)
- valor_causa_superior_210sm: TRUE se valor > 210 salários mínimos (R$ 340.410)
- uniao_polo_passivo: TRUE se União/órgão federal está no polo passivo
- municipio_polo_passivo: TRUE se algum município está no polo passivo
- estado_polo_passivo: TRUE se o Estado está no polo passivo
- autor_com_assistencia_judiciaria: TRUE se autor tem assistência judiciária
- autor_com_defensoria: TRUE se autor é representado por Defensoria

IMPORTANTE - VARIÁVEIS DE PARECERES (NAT):
- pareceres_medicamento_nao_incorporado_sus: TRUE se parecer do NAT analisou medicamento NÃO incorporado ao SUS
- pareceres_medicamento_incorporado_sus: TRUE se parecer do NAT analisou medicamento incorporado ao SUS
- pareceres_analisou_medicamento: TRUE se parecer analisou qualquer medicamento

PREFIRA usar essas variáveis booleanas pré-calculadas quando a condição envolver:
- Valores em salários mínimos → use valor_causa_inferior_60sm ou valor_causa_superior_210sm
- Competência/litisconsórcio → use uniao_polo_passivo, municipio_polo_passivo, estado_polo_passivo
- Datas de ajuizamento → use processo_ajuizado_apos_2024_09_19
- Parecer NAT com medicamento → use pareceres_medicamento_nao_incorporado_sus ou pareceres_medicamento_incorporado_sus

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
6. Variáveis devem estar em snake_case
7. IMPORTANTE: Para variáveis booleanas, use SEMPRE os valores literais true ou false (minúsculos, sem aspas)
   - CORRETO: "value": true
   - CORRETO: "value": false
   - ERRADO: "value": 1
   - ERRADO: "value": 0
   - ERRADO: "value": "true"
   - ERRADO: "value": "false" """

    def _buscar_variaveis_disponiveis(self) -> List[Dict]:
        """
        Busca todas as variáveis disponíveis no sistema.

        Inclui:
        - ExtractionVariable: variáveis extraídas de PDFs (tabela do banco)
        - ProcessVariableDefinition: variáveis derivadas do XML do processo (grupo "Sistema")
        """
        variaveis = []

        # 1. Variáveis de extração (PDFs) do banco de dados
        extraction_vars = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.ativo == True
        ).all()

        for v in extraction_vars:
            variaveis.append({
                "slug": v.slug,
                "label": v.label,
                "tipo": v.tipo,
                "descricao": v.descricao,
                "opcoes": v.opcoes,
                "fonte": "extracao"  # Para identificar origem
            })

        logger.info(f"[REGRA-DETERMINISTICO] Variáveis de extração (banco): {len(extraction_vars)}")

        # 2. Variáveis de processo (XML) - derivadas/calculadas (grupo "Sistema")
        # IMPORTANTE: Estas variáveis incluem valor_causa_superior_210sm, uniao_polo_passivo, etc.
        vars_processo_count = 0
        try:
            from .services_process_variables import ProcessVariableResolver

            definitions = ProcessVariableResolver.get_all_definitions()
            vars_processo_count = len(definitions)

            for definition in definitions:
                variaveis.append({
                    "slug": definition.slug,
                    "label": definition.label,
                    "tipo": definition.tipo,
                    "descricao": definition.descricao,
                    "opcoes": None,
                    "fonte": "processo_sistema"  # Variável do grupo Sistema (calculada do XML)
                })

            # Log explícito das variáveis de Sistema carregadas
            slugs_sistema = [d.slug for d in definitions]
            logger.info(
                f"[REGRA-DETERMINISTICO] Variáveis de Sistema (processo): {vars_processo_count} - "
                f"Slugs: {slugs_sistema}"
            )

        except Exception as e:
            logger.error(
                f"[REGRA-DETERMINISTICO] ERRO CRÍTICO ao carregar variáveis de processo (Sistema): {e}. "
                f"Variáveis como valor_causa_superior_210sm NÃO estarão disponíveis!"
            )
            import traceback
            logger.error(traceback.format_exc())

        logger.info(
            f"[REGRA-DETERMINISTICO] TOTAL de variáveis disponíveis: {len(variaveis)} "
            f"(extração: {len(extraction_vars)}, sistema: {vars_processo_count})"
        )

        return variaveis

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

        Regras especiais:
        1. Se variável não existe ou é None → considera como False (para booleanos)
        2. Se variável é uma lista → usa lógica OR (pelo menos um True = True)
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

            # REGRA 1: Se variável não existe ou é None, considera como False para booleanos
            # Isso permite que condições como "variavel = false" sejam TRUE quando a variável não existe
            if valor_esperado in (True, False, "true", "false"):
                valor_atual = False
                logger.debug(
                    f"[REGRA-DETERMINISTICO] Variável '{variavel}' não existe/null, "
                    f"considerando como False para comparação booleana"
                )

        # REGRA 2: Se valor_atual é uma lista, aplica lógica OR
        # Se pelo menos um valor TRUE na lista → variável = TRUE
        # Depois compara normalmente com valor_esperado
        if isinstance(valor_atual, list):
            # Para booleanos: consolida a lista usando lógica OR
            # [false, false, true] → true (pelo menos 1 true)
            # [false, false, false] → false (nenhum true)
            if valor_esperado in (True, False, "true", "false"):
                valor_atual = any(self._normalizar_booleano(v) for v in valor_atual)
            else:
                # Para outros tipos: verifica se algum valor na lista satisfaz
                for v in valor_atual:
                    if self._aplicar_operador(operador, v, valor_esperado):
                        return True
                return False

            logger.debug(
                f"[REGRA-DETERMINISTICO] Variável '{variavel}' é lista, "
                f"aplicando lógica OR: valor consolidado = {valor_atual}"
            )

        # Avalia operador
        return self._aplicar_operador(operador, valor_atual, valor_esperado)

    def _normalizar_booleano(self, valor: Any) -> bool:
        """Normaliza um valor para booleano."""
        if valor is None:
            return False
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, str):
            return valor.lower() in ("true", "1", "yes", "sim")
        return bool(valor)

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

        # Normaliza 1/0 para booleanos (compatibilidade com regras antigas)
        # Isso garante que value:1 seja tratado como value:true
        if isinstance(b, int) and b in (0, 1):
            b = bool(b)
        if isinstance(a, int) and a in (0, 1) and isinstance(b, bool):
            a = bool(a)

        # Normaliza booleanos
        if isinstance(b, bool):
            if isinstance(a, str):
                return a.lower() in ("true", "sim", "yes", "1") if b else a.lower() in ("false", "não", "nao", "no", "0")
            if isinstance(a, bool):
                return a == b

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
    fallback_habilitado: bool = False,
    tipo_peca: Optional[str] = None
) -> Dict[str, Any]:
    """
    Avalia se um prompt deve ser ativado com suporte a regras por tipo de peça.

    IMPORTANTE: Esta função usa resolve_activation_mode_from_db() para determinar
    o modo de ativação REAL, IGNORANDO o parâmetro modo_ativacao quando há regras
    determinísticas configuradas. Isso garante a REGRA DE OURO do sistema.

    LÓGICA DE ATIVAÇÃO (v3 - regra global como FALLBACK):

    REGRA PRINCIPAL:
    - Se existe ALGUMA regra específica ATIVA para o tipo de peça:
      → Avalia APENAS as regras específicas (ignora regra global primária)
    - Se NÃO existe regra específica ativa para o tipo de peça:
      → Usa a regra global primária como FALLBACK

    Isso significa que regras específicas SOBREPÕEM a regra global primária.

    Args:
        prompt_id: ID do prompt
        modo_ativacao: 'llm' ou 'deterministic' (PODE SER IGNORADO se há regras)
        regra_deterministica: AST JSON da regra PRIMÁRIA GLOBAL (se modo deterministic)
        dados_extracao: Dados extraídos do processo
        db: Sessão do banco
        regra_secundaria: AST JSON da regra SECUNDÁRIA GLOBAL/fallback (opcional)
        fallback_habilitado: Se deve avaliar regra secundária quando primária não existe
        tipo_peca: Tipo de peça para buscar regras específicas (opcional, ex: 'contestacao')

    Returns:
        Dict com ativar, modo, detalhes, regra_usada, regras_avaliadas
    """
    # ==========================================================================
    # REGRA DE OURO: Resolve o modo de ativação REAL considerando todas as regras
    # O parâmetro modo_ativacao pode estar incorreto - não confiamos nele!
    # ==========================================================================
    modo_ativacao_real = resolve_activation_mode_from_db(
        db=db,
        modulo_id=prompt_id,
        modo_ativacao_salvo=modo_ativacao,
        regra_primaria=regra_deterministica,
        regra_secundaria=regra_secundaria,
        fallback_habilitado=fallback_habilitado
    )

    # Log se houve correção
    if modo_ativacao_real != modo_ativacao:
        logger.warning(
            f"[REGRA-DE-OURO] Prompt {prompt_id}: modo_ativacao corrigido de "
            f"'{modo_ativacao}' para '{modo_ativacao_real}' em runtime"
        )

    if modo_ativacao_real != "deterministic":
        # Modo LLM - retorna None para indicar que precisa chamar LLM
        return {
            "ativar": None,
            "modo": "llm",
            "regra_usada": None,
            "detalhes": "Requer avaliação por LLM"
        }

    avaliador = DeterministicRuleEvaluator()
    regras_avaliadas = []

    # ========================================
    # 1. VERIFICA SE EXISTEM REGRAS ESPECÍFICAS ATIVAS
    # ========================================
    tem_regra_especifica_ativa = False
    if tipo_peca:
        tem_regra_especifica_ativa = _existe_regra_especifica_ativa(db, prompt_id, tipo_peca)
        logger.info(
            f"[DETERMINISTIC] Prompt {prompt_id}: "
            f"tipo_peca={tipo_peca}, tem_regra_especifica_ativa={tem_regra_especifica_ativa}"
        )

    # ========================================
    # 2. SE TEM REGRA ESPECÍFICA → AVALIA APENAS ESPECÍFICA
    # ========================================
    if tem_regra_especifica_ativa:
        regra_especifica = _carregar_regra_tipo_peca(db, prompt_id, tipo_peca)

        if regra_especifica and regra_especifica.regra_deterministica:
            # Log detalhado da regra específica
            logger.info(
                f"[DETERMINISTIC] Prompt {prompt_id}: "
                f"Regra específica carregada: {regra_especifica.regra_deterministica}"
            )
            
            variaveis_especifica_existem, vars_especifica = verificar_variaveis_existem(
                regra_especifica.regra_deterministica, dados_extracao
            )

            # Log dos valores atuais das variáveis
            valores_vars = {v: dados_extracao.get(v, "<<NÃO ENCONTRADA>>") for v in vars_especifica}
            logger.info(
                f"[DETERMINISTIC] Prompt {prompt_id}: "
                f"ESPECÍFICA {tipo_peca} - vars existem={variaveis_especifica_existem}, "
                f"vars={vars_especifica}, valores={valores_vars}"
            )

            if variaveis_especifica_existem:
                resultado_tipo_peca = avaliador.avaliar(
                    regra_especifica.regra_deterministica, dados_extracao
                )
                regras_avaliadas.append({
                    "tipo": f"especifica_{tipo_peca}",
                    "resultado": resultado_tipo_peca,
                    "variaveis": vars_especifica
                })

                logger.info(
                    f"[DETERMINISTIC] Prompt {prompt_id}: ESPECÍFICA {tipo_peca} = {resultado_tipo_peca}"
                )

                if resultado_tipo_peca is True:
                    _registrar_log_ativacao(
                        db=db,
                        prompt_id=prompt_id,
                        modo="deterministic_tipo_peca",
                        resultado=True,
                        variaveis_usadas=vars_especifica,
                        detalhe=tipo_peca
                    )
                    return {
                        "ativar": True,
                        "modo": "deterministic",
                        "regra_usada": f"especifica_{tipo_peca}",
                        "detalhes": f"Ativado por regra ESPECÍFICA de {tipo_peca} (vars: {vars_especifica})",
                        "regras_avaliadas": regras_avaliadas
                    }

                # Regra específica retornou False - NÃO ativa (não usa global como fallback)
                if resultado_tipo_peca is False:
                    _registrar_log_ativacao(
                        db=db,
                        prompt_id=prompt_id,
                        modo="deterministic_tipo_peca",
                        resultado=False,
                        variaveis_usadas=vars_especifica,
                        detalhe=f"{tipo_peca}_false"
                    )
                    return {
                        "ativar": False,
                        "modo": "deterministic",
                        "regra_usada": f"especifica_{tipo_peca}",
                        "detalhes": f"Regra específica de {tipo_peca} retornou False (global ignorada)",
                        "regras_avaliadas": regras_avaliadas
                    }

            # Variáveis não existem - resultado indeterminado
            return {
                "ativar": None,
                "modo": "deterministic",
                "regra_usada": f"especifica_{tipo_peca}",
                "detalhes": f"Variáveis da regra específica de {tipo_peca} não encontradas",
                "regras_avaliadas": regras_avaliadas
            }

    # ========================================
    # 3. SEM REGRA ESPECÍFICA → USA GLOBAL COMO FALLBACK
    # ========================================
    resultado_global = None

    if regra_deterministica:
        variaveis_primaria_existem, vars_primaria = verificar_variaveis_existem(
            regra_deterministica, dados_extracao
        )

        logger.info(
            f"[DETERMINISTIC] Prompt {prompt_id}: "
            f"GLOBAL primária (fallback) - vars existem={variaveis_primaria_existem}, vars={vars_primaria}"
        )

        if variaveis_primaria_existem:
            resultado_global = avaliador.avaliar(regra_deterministica, dados_extracao)
            regras_avaliadas.append({
                "tipo": "global_primaria",
                "resultado": resultado_global,
                "variaveis": vars_primaria
            })

            logger.info(
                f"[DETERMINISTIC] Prompt {prompt_id}: GLOBAL primária = {resultado_global}"
            )

            if resultado_global is True:
                _registrar_log_ativacao(
                    db=db,
                    prompt_id=prompt_id,
                    modo="deterministic_global",
                    resultado=True,
                    variaveis_usadas=vars_primaria,
                    detalhe="primary"
                )
                return {
                    "ativar": True,
                    "modo": "deterministic",
                    "regra_usada": "global_primaria",
                    "detalhes": f"Ativado por regra GLOBAL primária (fallback, sem regra específica para {tipo_peca or 'N/A'})",
                    "regras_avaliadas": regras_avaliadas
                }

            if resultado_global is False:
                _registrar_log_ativacao(
                    db=db,
                    prompt_id=prompt_id,
                    modo="deterministic_global",
                    resultado=False,
                    variaveis_usadas=vars_primaria,
                    detalhe="primary_false"
                )
                return {
                    "ativar": False,
                    "modo": "deterministic",
                    "regra_usada": "global_primaria",
                    "detalhes": f"Regra GLOBAL primária retornou False (fallback)",
                    "regras_avaliadas": regras_avaliadas
                }

        elif fallback_habilitado and regra_secundaria:
            # Tenta regra global secundária
            variaveis_secundaria_existem, vars_secundaria = verificar_variaveis_existem(
                regra_secundaria, dados_extracao
            )

            if variaveis_secundaria_existem:
                resultado_global = avaliador.avaliar(regra_secundaria, dados_extracao)
                regras_avaliadas.append({
                    "tipo": "global_secundaria",
                    "resultado": resultado_global,
                    "variaveis": vars_secundaria
                })

                logger.info(
                    f"[DETERMINISTIC] Prompt {prompt_id}: GLOBAL secundária = {resultado_global}"
                )

                if resultado_global is True:
                    _registrar_log_ativacao(
                        db=db,
                        prompt_id=prompt_id,
                        modo="deterministic_global",
                        resultado=True,
                        variaveis_usadas=vars_secundaria,
                        detalhe="secondary"
                    )
                    return {
                        "ativar": True,
                        "modo": "deterministic",
                        "regra_usada": "global_secundaria",
                        "detalhes": f"Ativado por regra GLOBAL secundária (vars: {vars_secundaria})",
                        "regras_avaliadas": regras_avaliadas
                    }

                if resultado_global is False:
                    _registrar_log_ativacao(
                        db=db,
                        prompt_id=prompt_id,
                        modo="deterministic_global",
                        resultado=False,
                        variaveis_usadas=vars_secundaria,
                        detalhe="secondary_false"
                    )
                    return {
                        "ativar": False,
                        "modo": "deterministic",
                        "regra_usada": "global_secundaria",
                        "detalhes": f"Regra GLOBAL secundária retornou False",
                        "regras_avaliadas": regras_avaliadas
                    }

    # Nenhuma regra aplicável ou avaliável
    return {
        "ativar": None,
        "modo": "deterministic",
        "regra_usada": "nenhuma",
        "detalhes": f"Nenhuma regra aplicável (tipo_peca={tipo_peca})",
        "regras_avaliadas": regras_avaliadas
    }


def _carregar_regra_tipo_peca(
    db: Session,
    modulo_id: int,
    tipo_peca: str
) -> Optional['RegraDeterministicaTipoPeca']:
    """
    Carrega a regra determinística específica para um tipo de peça.

    Args:
        db: Sessão do banco
        modulo_id: ID do módulo
        tipo_peca: Tipo de peça (ex: 'contestacao', 'apelacao')

    Returns:
        RegraDeterministicaTipoPeca ou None se não existir
    """
    from admin.models_prompts import RegraDeterministicaTipoPeca

    return db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.modulo_id == modulo_id,
        RegraDeterministicaTipoPeca.tipo_peca == tipo_peca,
        RegraDeterministicaTipoPeca.ativo == True
    ).first()


def _existe_regra_especifica_ativa(
    db: Session,
    modulo_id: int,
    tipo_peca: str
) -> bool:
    """
    Verifica se existe ALGUMA regra específica ATIVA para o tipo de peça.

    Usado para determinar se a regra global principal deve ser usada como fallback.

    Args:
        db: Sessão do banco
        modulo_id: ID do módulo
        tipo_peca: Tipo de peça (ex: 'contestacao', 'apelacao')

    Returns:
        True se existe pelo menos uma regra específica ativa, False caso contrário
    """
    from admin.models_prompts import RegraDeterministicaTipoPeca

    count = db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.modulo_id == modulo_id,
        RegraDeterministicaTipoPeca.tipo_peca == tipo_peca,
        RegraDeterministicaTipoPeca.ativo == True
    ).count()

    return count > 0


def carregar_regras_tipo_peca_modulo(
    db: Session,
    modulo_id: int
) -> List['RegraDeterministicaTipoPeca']:
    """
    Carrega todas as regras específicas por tipo de peça de um módulo.

    Args:
        db: Sessão do banco
        modulo_id: ID do módulo

    Returns:
        Lista de RegraDeterministicaTipoPeca
    """
    from admin.models_prompts import RegraDeterministicaTipoPeca

    return db.query(RegraDeterministicaTipoPeca).filter(
        RegraDeterministicaTipoPeca.modulo_id == modulo_id
    ).order_by(RegraDeterministicaTipoPeca.tipo_peca).all()


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
    variaveis_usadas: List[str],
    detalhe: Optional[str] = None
):
    """
    Registra log de ativação de prompt.

    IMPORTANTE: O logging é resiliente - falhas não abortam o fluxo principal.

    Args:
        db: Sessão do banco
        prompt_id: ID do prompt
        modo: Modo padronizado (llm, deterministic, deterministic_global, deterministic_tipo_peca, mixed)
        resultado: True se ativado, False se não ativado
        variaveis_usadas: Lista de slugs das variáveis usadas na avaliação
        detalhe: Detalhe adicional (ex: tipo de peça, regra específica)
    """
    try:
        from .models_extraction import PromptActivationLog

        log = PromptActivationLog(
            prompt_id=prompt_id,
            modo_ativacao=modo,
            modo_ativacao_detalhe=detalhe,
            resultado=resultado,
            variaveis_usadas=variaveis_usadas
        )
        db.add(log)
        db.commit()
    except Exception as e:
        # Logging não deve abortar o fluxo principal
        logger.warning(f"[LOG-ATIVACAO] Falha ao registrar log de ativação: {e}")
        try:
            db.rollback()
        except Exception:
            pass


# =============================================================================
# VALIDAÇÃO DE INTEGRIDADE DE VARIÁVEIS EM REGRAS
# =============================================================================

class RuleIntegrityValidator:
    """
    Validador de integridade entre regras determinísticas e variáveis disponíveis.

    Verifica se todas as variáveis usadas em regras:
    - Existem em algum JSON de extração (ExtractionVariable)
    - OU são variáveis de sistema (ProcessVariableDefinition)

    Uso:
        validator = RuleIntegrityValidator(db)
        resultado = validator.validar_modulo(modulo_id)
        # resultado = {
        #     "valido": False,
        #     "variaveis_invalidas": [
        #         {"variavel": "xyz", "regra": "global_primaria", "tipo_peca": None},
        #         ...
        #     ],
        #     "resumo": {...}
        # }
    """

    def __init__(self, db: Session):
        self.db = db
        self._variaveis_disponiveis: Optional[Set[str]] = None
        self._variaveis_sistema: Optional[Set[str]] = None
        self._variaveis_extracao: Optional[Set[str]] = None

    def _carregar_variaveis_disponiveis(self) -> None:
        """Carrega todas as variáveis disponíveis no sistema."""
        if self._variaveis_disponiveis is not None:
            return

        self._variaveis_extracao = set()
        self._variaveis_sistema = set()

        # 1. Variáveis de extração (PDFs) do banco de dados
        from .models_extraction import ExtractionVariable
        extraction_vars = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.ativo == True
        ).all()

        for v in extraction_vars:
            self._variaveis_extracao.add(v.slug)

        # 2. Variáveis de processo (XML) - variáveis de sistema
        try:
            from .services_process_variables import ProcessVariableResolver
            definitions = ProcessVariableResolver.get_all_definitions()
            for definition in definitions:
                self._variaveis_sistema.add(definition.slug)
        except Exception as e:
            logger.error(f"[VALIDADOR-INTEGRIDADE] Erro ao carregar variáveis de sistema: {e}")

        self._variaveis_disponiveis = self._variaveis_extracao | self._variaveis_sistema

        logger.info(
            f"[VALIDADOR-INTEGRIDADE] Variáveis carregadas: "
            f"extração={len(self._variaveis_extracao)}, "
            f"sistema={len(self._variaveis_sistema)}, "
            f"total={len(self._variaveis_disponiveis)}"
        )

    def _extrair_variaveis_regra(self, regra: Optional[Dict]) -> Set[str]:
        """Extrai todas as variáveis usadas em uma regra (recursivo)."""
        if not regra:
            return set()
        return _extrair_variaveis_regra(regra)

    def validar_regra(
        self,
        regra: Optional[Dict],
        nome_regra: str,
        tipo_peca: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Valida uma única regra e retorna lista de variáveis inválidas.

        Args:
            regra: AST JSON da regra
            nome_regra: Nome identificador da regra (ex: "global_primaria")
            tipo_peca: Tipo de peça se for regra específica

        Returns:
            Lista de dicts com {variavel, regra, tipo_peca, is_sistema}
        """
        self._carregar_variaveis_disponiveis()

        if not regra:
            return []

        variaveis_usadas = self._extrair_variaveis_regra(regra)
        variaveis_invalidas = []

        for var in variaveis_usadas:
            if var not in self._variaveis_disponiveis:
                variaveis_invalidas.append({
                    "variavel": var,
                    "regra": nome_regra,
                    "tipo_peca": tipo_peca,
                    "sugestao_tipo": self._inferir_tipo_variavel(var)
                })

        return variaveis_invalidas

    def _inferir_tipo_variavel(self, slug: str) -> str:
        """Infere o tipo de uma variável baseado no nome."""
        slug_lower = slug.lower()

        if any(p in slug_lower for p in ["valor", "custo", "preco", "montante", "total"]):
            return "currency"
        elif any(p in slug_lower for p in ["data", "date", "dia", "nascimento", "vencimento"]):
            return "date"
        elif any(p in slug_lower for p in ["idoso", "ativo", "possui", "tem_", "eh_", "sim_nao", "aprovado", "habilitado"]):
            return "boolean"
        elif any(p in slug_lower for p in ["quantidade", "numero", "qtd", "age", "prazo", "dias"]):
            return "number"
        return "text"

    def validar_modulo(self, modulo_id: int) -> Dict[str, Any]:
        """
        Valida todas as regras de um módulo de prompt.

        Args:
            modulo_id: ID do módulo a validar

        Returns:
            Dict com:
            - valido: bool
            - variaveis_invalidas: lista de variáveis que não existem
            - resumo: estatísticas
        """
        from admin.models_prompts import PromptModulo, RegraDeterministicaTipoPeca

        self._carregar_variaveis_disponiveis()

        # Busca módulo
        modulo = self.db.query(PromptModulo).filter(PromptModulo.id == modulo_id).first()
        if not modulo:
            return {
                "valido": False,
                "erro": "Módulo não encontrado",
                "variaveis_invalidas": [],
                "resumo": {}
            }

        todas_invalidas = []

        # 1. Valida regra global primária
        invalidas_primaria = self.validar_regra(
            modulo.regra_deterministica,
            "global_primaria"
        )
        todas_invalidas.extend(invalidas_primaria)

        # 2. Valida regra global secundária (fallback)
        invalidas_secundaria = self.validar_regra(
            modulo.regra_deterministica_secundaria,
            "global_secundaria"
        )
        todas_invalidas.extend(invalidas_secundaria)

        # 3. Valida regras por tipo de peça
        regras_tipo_peca = self.db.query(RegraDeterministicaTipoPeca).filter(
            RegraDeterministicaTipoPeca.modulo_id == modulo_id
        ).all()

        for regra_tp in regras_tipo_peca:
            invalidas_tp = self.validar_regra(
                regra_tp.regra_deterministica,
                f"tipo_peca_{regra_tp.tipo_peca}",
                regra_tp.tipo_peca
            )
            todas_invalidas.extend(invalidas_tp)

        # Monta resumo
        variaveis_unicas = list(set(v["variavel"] for v in todas_invalidas))
        regras_afetadas = list(set(v["regra"] for v in todas_invalidas))

        return {
            "valido": len(todas_invalidas) == 0,
            "modulo_id": modulo_id,
            "modulo_nome": modulo.nome,
            "variaveis_invalidas": todas_invalidas,
            "resumo": {
                "total_variaveis_invalidas": len(variaveis_unicas),
                "variaveis_unicas": variaveis_unicas,
                "total_regras_afetadas": len(regras_afetadas),
                "regras_afetadas": regras_afetadas,
                "total_variaveis_disponiveis": len(self._variaveis_disponiveis),
                "total_variaveis_extracao": len(self._variaveis_extracao),
                "total_variaveis_sistema": len(self._variaveis_sistema)
            }
        }

    def validar_todos_modulos(self) -> Dict[str, Any]:
        """
        Valida todos os módulos com regras determinísticas.

        Returns:
            Dict com resumo geral e lista de módulos com problemas
        """
        from admin.models_prompts import PromptModulo

        self._carregar_variaveis_disponiveis()

        # Busca módulos com modo determinístico
        modulos = self.db.query(PromptModulo).filter(
            PromptModulo.modo_ativacao == 'deterministic',
            PromptModulo.ativo == True
        ).all()

        modulos_invalidos = []
        total_problemas = 0

        for modulo in modulos:
            resultado = self.validar_modulo(modulo.id)
            if not resultado["valido"]:
                modulos_invalidos.append({
                    "modulo_id": modulo.id,
                    "modulo_nome": modulo.nome,
                    "modulo_titulo": modulo.titulo,
                    "variaveis_invalidas": resultado["variaveis_invalidas"],
                    "resumo": resultado["resumo"]
                })
                total_problemas += len(resultado["variaveis_invalidas"])

        return {
            "valido": len(modulos_invalidos) == 0,
            "total_modulos_verificados": len(modulos),
            "total_modulos_invalidos": len(modulos_invalidos),
            "total_problemas": total_problemas,
            "modulos_invalidos": modulos_invalidos,
            "variaveis_disponiveis": {
                "total": len(self._variaveis_disponiveis),
                "extracao": len(self._variaveis_extracao),
                "sistema": len(self._variaveis_sistema),
                "lista_sistema": sorted(list(self._variaveis_sistema))
            }
        }

    def obter_variaveis_disponiveis(self) -> Dict[str, Any]:
        """
        Retorna todas as variáveis disponíveis organizadas por fonte.

        Útil para debug e para o frontend mostrar variáveis válidas.
        """
        self._carregar_variaveis_disponiveis()

        # Detalhes das variáveis de extração
        from .models_extraction import ExtractionVariable
        extraction_vars = self.db.query(ExtractionVariable).filter(
            ExtractionVariable.ativo == True
        ).order_by(ExtractionVariable.slug).all()

        vars_extracao_detalhes = [
            {
                "slug": v.slug,
                "label": v.label,
                "tipo": v.tipo,
                "categoria_id": v.categoria_id,
                "is_conditional": v.is_conditional
            }
            for v in extraction_vars
        ]

        # Detalhes das variáveis de sistema
        vars_sistema_detalhes = []
        try:
            from .services_process_variables import ProcessVariableResolver
            for definition in ProcessVariableResolver.get_all_definitions():
                vars_sistema_detalhes.append({
                    "slug": definition.slug,
                    "label": definition.label,
                    "tipo": definition.tipo,
                    "descricao": definition.descricao,
                    "is_system": True
                })
        except Exception:
            pass

        return {
            "total": len(self._variaveis_disponiveis),
            "extracao": {
                "total": len(vars_extracao_detalhes),
                "variaveis": vars_extracao_detalhes
            },
            "sistema": {
                "total": len(vars_sistema_detalhes),
                "variaveis": vars_sistema_detalhes
            }
        }


def validar_integridade_regras_modulo(db: Session, modulo_id: int) -> Dict[str, Any]:
    """
    Função de conveniência para validar integridade de regras de um módulo.

    Args:
        db: Sessão do banco
        modulo_id: ID do módulo

    Returns:
        Resultado da validação
    """
    validator = RuleIntegrityValidator(db)
    return validator.validar_modulo(modulo_id)


def validar_integridade_todas_regras(db: Session) -> Dict[str, Any]:
    """
    Função de conveniência para validar todas as regras do sistema.

    Args:
        db: Sessão do banco

    Returns:
        Resultado da validação geral
    """
    validator = RuleIntegrityValidator(db)
    return validator.validar_todos_modulos()
