# sistemas/prestacao_contas/identificador_peticoes.py
"""
Identificador de Petição de Prestação de Contas

Utiliza LLM para classificar petições e documentos.
O prompt é configurável via painel admin (/admin/prompts-config).

Autor: LAB/PGE-MS
"""

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
from sqlalchemy.orm import Session

from services.ia_params_resolver import get_ia_params, IAParams

logger = logging.getLogger(__name__)


class TipoDocumento(str, Enum):
    """Tipos de documentos identificáveis"""
    PETICAO_PRESTACAO = "PETICAO_PRESTACAO"
    PETICAO_RELEVANTE = "PETICAO_RELEVANTE"
    NOTA_FISCAL = "NOTA_FISCAL"
    COMPROVANTE = "COMPROVANTE"
    IRRELEVANTE = "IRRELEVANTE"


# Prompt padrão (usado se não houver configuração no admin)
PROMPT_IDENTIFICACAO_PADRAO = """Analise o documento abaixo e classifique-o em relação a um processo de PRESTAÇÃO DE CONTAS de medicamentos judiciais.

REGRA PRINCIPAL: Na dúvida, classifique como PETICAO_RELEVANTE. Só use IRRELEVANTE para documentos claramente não relacionados ao mérito do processo.

TIPOS DE DOCUMENTOS:

1. PETICAO_PRESTACAO - Petição que apresenta PRESTAÇÃO DE CONTAS:
   - Petição do AUTOR ou TERCEIRO INTERESSADO (farmácia, home care, prestador de serviço)
   - Menciona expressamente "prestação de contas"
   - Informa compra do medicamento ou serviço determinado judicialmente
   - Apresenta ou menciona notas fiscais/recibos de compra
   - Demonstra como o dinheiro bloqueado foi utilizado
   - Solicita arquivamento ou devolução de saldo

   IMPORTANTE: Petições do ESTADO, PGE, Fazenda Pública ou advogados públicos NUNCA são PETICAO_PRESTACAO.
   Petições de FARMÁCIAS, HOME CARE ou prestadores de serviço que prestam contas SÃO PETICAO_PRESTACAO.

2. PETICAO_RELEVANTE - USE ESTA CLASSIFICAÇÃO GENEROSAMENTE para qualquer documento que contenha:
   - Petição inicial do processo (pedido original do medicamento)
   - Manifestações do Estado/PGE sobre a prestação de contas
   - Decisões judiciais sobre bloqueio/liberação de valores
   - Pedidos de complementação ou esclarecimentos
   - Petições mencionando valores, medicamentos ou dinheiro
   - Despachos sobre o andamento do processo
   - Manifestações sobre cumprimento de obrigação
   - Qualquer documento que mencione: medicamento, bloqueio, subconta, valor, prestação, comprovante
   - Petições do Estado/PGE pedindo providências ou informações

3. NOTA_FISCAL - Documento fiscal/comercial:
   - Notas fiscais de compra de medicamento
   - Cupons fiscais
   - Recibos de compra
   - Orçamentos de farmácia

4. COMPROVANTE - Comprovantes financeiros:
   - Comprovantes de transferência/PIX
   - Comprovantes de pagamento
   - Extratos bancários
   - Recibos de depósito

5. IRRELEVANTE - SOMENTE documentos claramente não relacionados ao mérito:
   - Procurações (substabelecimentos, mandatos)
   - Certidões de publicação/intimação
   - Comprovantes de distribuição
   - Documentos pessoais (RG, CPF)
   - Petições APENAS sobre custas processuais
   - Petições APENAS sobre honorários advocatícios
   - ARs e avisos de recebimento

TEXTO DO DOCUMENTO:
{texto}

Responda APENAS com o JSON abaixo (sem explicações adicionais):
{{
  "tipo": "PETICAO_PRESTACAO" | "PETICAO_RELEVANTE" | "NOTA_FISCAL" | "COMPROVANTE" | "IRRELEVANTE",
  "confianca": 0.0 a 1.0,
  "resumo": "breve descrição do conteúdo (max 100 caracteres)",
  "menciona_anexos": true | false,
  "descricao_anexos": "descrição dos anexos mencionados ou null"
}}"""


@dataclass
class ResultadoIdentificacao:
    """Resultado da identificação de petição/documento"""
    tipo_documento: TipoDocumento
    metodo: str  # 'llm', 'llm_erro', 'vazio'
    confianca: float  # 0.0 a 1.0
    resumo: str = ""
    menciona_anexos: bool = False
    descricao_anexos: Optional[str] = None
    explicacao: Optional[str] = None

    # Compatibilidade retroativa
    @property
    def e_prestacao_contas(self) -> bool:
        return self.tipo_documento == TipoDocumento.PETICAO_PRESTACAO

    @property
    def e_relevante(self) -> bool:
        return self.tipo_documento in [
            TipoDocumento.PETICAO_PRESTACAO,
            TipoDocumento.PETICAO_RELEVANTE,
            TipoDocumento.NOTA_FISCAL,
            TipoDocumento.COMPROVANTE
        ]

    @property
    def deve_enviar_como_imagem(self) -> bool:
        return self.tipo_documento in [
            TipoDocumento.NOTA_FISCAL,
            TipoDocumento.COMPROVANTE
        ]


def _buscar_prompt_admin(db: Session = None) -> Optional[str]:
    """
    Busca o prompt de identificação configurado no admin.
    Retorna None se não encontrar.
    """
    if not db:
        return None

    try:
        from admin.models import PromptConfig

        prompt_config = db.query(PromptConfig).filter(
            PromptConfig.sistema == "prestacao_contas",
            PromptConfig.nome == "prompt_identificar_prestacao",
            PromptConfig.is_active == True
        ).first()

        if prompt_config and prompt_config.conteudo:
            return prompt_config.conteudo

    except Exception as e:
        logger.warning(f"Erro ao buscar prompt do admin: {e}")

    return None


class IdentificadorPeticoes:
    """
    Identificador de petições de prestação de contas usando LLM.
    O prompt é buscado do painel admin ou usa o padrão.
    """

    def __init__(
        self,
        modelo_llm: str = None,
        temperatura_llm: float = None,
        db: Session = None,
        usar_llm: bool = True,  # Mantido para compatibilidade, mas sempre usa LLM
    ):
        """
        Args:
            modelo_llm: Modelo de IA (override manual, opcional - usa resolver)
            temperatura_llm: Temperatura da IA (override manual, opcional - usa resolver)
            db: Sessão do banco para buscar prompt do admin
            usar_llm: Ignorado (mantido para compatibilidade)
        """
        self.db = db

        # Usa resolver de parâmetros por agente
        if db:
            self._params = get_ia_params(db, "prestacao_contas", "identificacao")
        else:
            # Fallback para valores padrão se não houver db
            self._params = IAParams(
                modelo="gemini-2.0-flash-lite",
                temperatura=0.1,
                max_tokens=None,
                sistema="prestacao_contas",
                agente="identificacao"
            )

        self.modelo_llm = modelo_llm or self._params.modelo
        self.temperatura_llm = temperatura_llm if temperatura_llm is not None else self._params.temperatura

        # Busca prompt do admin ou usa padrão
        self.prompt_template = _buscar_prompt_admin(db) or PROMPT_IDENTIFICACAO_PADRAO

    def identificar(self, texto: str) -> ResultadoIdentificacao:
        """
        Identifica se o texto é uma petição de prestação de contas.
        Método síncrono que delega para o método async.

        Args:
            texto: Texto da petição

        Returns:
            ResultadoIdentificacao
        """
        import asyncio

        if not texto or len(texto.strip()) < 50:
            return ResultadoIdentificacao(
                tipo_documento=TipoDocumento.IRRELEVANTE,
                metodo="vazio",
                confianca=1.0,
                explicacao="Texto muito curto ou vazio"
            )

        # Executa identificação com LLM
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Se já estamos em um loop async, retorna um resultado que será
                # resolvido pelo chamador async
                return self._identificar_sync_fallback(texto)
            else:
                return loop.run_until_complete(self._identificar_com_llm(texto))
        except RuntimeError:
            # Não há loop de eventos, cria um novo
            return asyncio.run(self._identificar_com_llm(texto))

    def _identificar_sync_fallback(self, texto: str) -> ResultadoIdentificacao:
        """Fallback síncrono que sempre retorna incerto para forçar uso async"""
        return ResultadoIdentificacao(
            tipo_documento=TipoDocumento.IRRELEVANTE,
            metodo="sync_fallback",
            confianca=0.0,
            explicacao="Use o método async identificar_async para identificação com LLM"
        )

    async def identificar_async(self, texto: str) -> ResultadoIdentificacao:
        """
        Identifica o tipo do documento (versão async).

        Args:
            texto: Texto do documento

        Returns:
            ResultadoIdentificacao com tipo, confiança e info sobre anexos
        """
        if not texto or len(texto.strip()) < 50:
            return ResultadoIdentificacao(
                tipo_documento=TipoDocumento.IRRELEVANTE,
                metodo="vazio",
                confianca=1.0,
                explicacao="Texto muito curto ou vazio"
            )

        return await self._identificar_com_llm(texto)

    async def _identificar_com_llm(self, texto: str) -> ResultadoIdentificacao:
        """
        Usa LLM para classificar o documento.
        Retorna tipo, confiança, resumo e se menciona anexos.
        """
        try:
            from services.gemini_service import GeminiService

            # Limita texto para não estourar contexto
            texto_truncado = texto[:6000]

            # Monta o prompt usando o template (do admin ou padrão)
            prompt = self.prompt_template.format(texto=texto_truncado)

            # Contexto para logging
            log_context = {
                "sistema": "prestacao_contas",
                "modulo": "identificador_peticoes",
            }

            service = GeminiService()
            resposta_obj = await service.generate(
                prompt=prompt,
                model=self.modelo_llm,
                temperature=self.temperatura_llm,
                context=log_context,
            )

            # Extrai conteúdo do GeminiResponse
            if not resposta_obj.success:
                raise Exception(resposta_obj.error or "Erro na chamada da IA")

            resposta = resposta_obj.content
            if resposta:
                resposta = resposta.strip()
            else:
                raise Exception("Resposta vazia da IA")

            logger.debug(f"Resposta LLM (primeiros 200 chars): {resposta[:200]}")

            # Tenta extrair JSON da resposta
            dados = self._extrair_json(resposta)

            if dados:
                tipo_str = dados.get("tipo", "IRRELEVANTE").upper()

                # Valida tipo
                try:
                    tipo = TipoDocumento(tipo_str)
                except ValueError:
                    tipo = TipoDocumento.IRRELEVANTE

                return ResultadoIdentificacao(
                    tipo_documento=tipo,
                    metodo="llm",
                    confianca=float(dados.get("confianca", 0.8)),
                    resumo=dados.get("resumo", ""),
                    menciona_anexos=bool(dados.get("menciona_anexos", False)),
                    descricao_anexos=dados.get("descricao_anexos"),
                    explicacao=f"Classificado como {tipo.value}"
                )
            else:
                # Fallback para prompt antigo (SIM/NAO/INCERTO)
                resposta_upper = resposta.upper().strip()

                if resposta_upper.startswith("SIM"):
                    logger.info("Fallback: LLM retornou SIM (prompt antigo)")
                    return ResultadoIdentificacao(
                        tipo_documento=TipoDocumento.PETICAO_PRESTACAO,
                        metodo="llm_fallback",
                        confianca=0.85,
                        resumo="Identificado como prestação de contas (formato antigo)",
                        explicacao="LLM retornou SIM - identificado como prestação"
                    )
                elif resposta_upper.startswith("NAO") or resposta_upper.startswith("NÃO"):
                    logger.info("Fallback: LLM retornou NAO (prompt antigo)")
                    return ResultadoIdentificacao(
                        tipo_documento=TipoDocumento.IRRELEVANTE,
                        metodo="llm_fallback",
                        confianca=0.85,
                        resumo="Não é prestação de contas (formato antigo)",
                        explicacao="LLM retornou NAO - documento irrelevante"
                    )
                else:
                    logger.warning(f"Não foi possível parsear resposta: {resposta[:100]}")
                    return ResultadoIdentificacao(
                        tipo_documento=TipoDocumento.IRRELEVANTE,
                        metodo="llm_parse_erro",
                        confianca=0.3,
                        explicacao="Não foi possível parsear resposta da IA"
                    )

        except Exception as e:
            logger.error(f"Erro ao usar LLM para identificação: {e}")
            return ResultadoIdentificacao(
                tipo_documento=TipoDocumento.IRRELEVANTE,
                metodo="llm_erro",
                confianca=0.0,
                explicacao=f"Erro ao usar LLM: {str(e)}"
            )

    def _extrair_json(self, texto: str) -> Optional[dict]:
        """Extrai JSON da resposta da IA"""
        # Remove blocos de código markdown
        texto_limpo = re.sub(r'```json\s*', '', texto)
        texto_limpo = re.sub(r'```\s*', '', texto_limpo)
        texto_limpo = texto_limpo.strip()

        # Tenta parsear diretamente
        try:
            return json.loads(texto_limpo)
        except json.JSONDecodeError:
            pass

        # Tenta encontrar JSON completo entre chaves (com suporte a múltiplas linhas)
        # Encontra a primeira { e a última }
        inicio = texto.find('{')
        fim = texto.rfind('}')

        if inicio != -1 and fim != -1 and fim > inicio:
            json_str = texto[inicio:fim+1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.debug(f"Erro ao parsear JSON extraído: {e}")

        # Última tentativa: regex mais permissivo
        match = re.search(r'\{[\s\S]*?\}', texto)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        return None

    def identificar_sync(self, texto: str) -> ResultadoIdentificacao:
        """
        Versão síncrona (para compatibilidade).
        Retorna inconclusivo se não conseguir executar async.
        """
        return self.identificar(texto)


async def identificar_documento(
    texto: str,
    modelo: str = "gemini-2.0-flash-lite",
    temperatura: float = 0.1,
    db: Session = None,
) -> ResultadoIdentificacao:
    """
    Classifica um documento em relação a um processo de prestação de contas.

    Args:
        texto: Texto do documento
        modelo: Modelo de IA a usar
        temperatura: Temperatura da IA
        db: Sessão do banco para buscar prompt do admin

    Returns:
        ResultadoIdentificacao com tipo, confiança, resumo e info sobre anexos
    """
    identificador = IdentificadorPeticoes(
        modelo_llm=modelo,
        temperatura_llm=temperatura,
        db=db
    )
    return await identificador.identificar_async(texto)


# Alias para compatibilidade retroativa
async def identificar_peticao_prestacao(
    texto: str,
    modelo: str = "gemini-2.0-flash-lite",
    temperatura: float = 0.1,
    db: Session = None,
    usar_llm: bool = True,
) -> ResultadoIdentificacao:
    """Alias para identificar_documento (compatibilidade retroativa)"""
    return await identificar_documento(texto, modelo, temperatura, db)


def identificar_peticao_prestacao_sync(texto: str) -> ResultadoIdentificacao:
    """
    Versão síncrona para identificar petição.
    Retorna resultado inconclusivo - use a versão async.
    """
    identificador = IdentificadorPeticoes()
    return identificador.identificar_sync(texto)
