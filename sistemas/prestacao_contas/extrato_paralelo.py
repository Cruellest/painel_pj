# sistemas/prestacao_contas/extrato_paralelo.py
"""
Módulo de Extração Paralela de Extrato de Subconta

Executa em paralelo:
- Task A: Scrapper do extrato (primário)
- Task B: Fallback de busca do extrato nos documentos
- Task C: Demais etapas da prestação de contas que não dependem do extrato

Regra de escolha:
- Se A retornar extrato válido dentro do timeout -> usar A
- Se A falhar/timeout/inválido -> usar B (se válido)
- Se A e B falharem -> seguir com extrato_subconta = null e extrato_source = "none"

Autor: LAB/PGE-MS
"""

import asyncio
import logging
import time
import base64
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

import aiohttp

from sistemas.prestacao_contas.scrapper_subconta import (
    extrair_extrato_subconta,
    StatusProcessamento,
    ResultadoExtracao,
)
# Cliente TJMS unificado (funcoes de compatibilidade)
from services.tjms import (
    baixar_documentos_async,
    extrair_texto_pdf,
)

logger = logging.getLogger(__name__)


# =====================================================
# CONFIGURAÇÕES
# =====================================================

@dataclass
class ConfigExtratoParalelo:
    """Configurações de timeouts e thresholds para extração paralela."""

    # Timeouts em segundos
    scrapper_timeout: float = 60.0   # 1 minuto para o scrapper
    fallback_timeout: float = 60.0   # 1 minuto para o fallback

    # Validação de extrato
    min_caracteres_extrato: int = 200  # Mínimo de caracteres para considerar válido
    min_caracteres_util: int = 500     # Mínimo para considerar texto útil (vs imagem)

    # Marcadores esperados no extrato de subconta
    marcadores_extrato: List[str] = field(default_factory=lambda: [
        "SUBCONTA",
        "EXTRATO",
        "SALDO",
        "BLOQUEIO",
        "MOVIMENTAÇÃO",
        "CONTA ÚNICA",
        "VALOR BLOQUEADO",
        "INFORMAÇÕES DA SUBCONTA",
        "LIBERAÇÃO",
        "ALVARÁ",
    ])

    @classmethod
    def from_db(cls, db, sistema: str = "prestacao_contas") -> "ConfigExtratoParalelo":
        """Carrega configurações do banco de dados."""
        try:
            from admin.models import ConfiguracaoIA

            def get_config(chave: str, default: str) -> str:
                config = db.query(ConfiguracaoIA).filter(
                    ConfiguracaoIA.sistema == sistema,
                    ConfiguracaoIA.chave == chave
                ).first()
                return config.valor if config else default

            return cls(
                scrapper_timeout=float(get_config("scrapper_timeout", "120.0")),
                fallback_timeout=float(get_config("fallback_timeout", "60.0")),
                min_caracteres_extrato=int(get_config("min_caracteres_extrato", "200")),
                min_caracteres_util=int(get_config("min_caracteres_util", "500")),
            )
        except Exception:
            return cls()


class ExtratoSource(str, Enum):
    """Fonte do extrato obtido."""
    SCRAPPER = "scrapper"
    FALLBACK_DOCUMENTOS = "fallback_documentos"
    NONE = "none"


class ExtratoFailReason(str, Enum):
    """Motivo da falha na obtenção do extrato."""
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    INVALID = "invalid"
    ERROR = "error"
    SEM_SUBCONTA = "sem_subconta"


# =====================================================
# VALIDAÇÃO DE EXTRATO
# =====================================================

def is_valid_extrato(texto: str, config: Optional[ConfigExtratoParalelo] = None) -> bool:
    """
    Valida se o texto extraído é um extrato válido.

    Heurísticas:
    1. Não vazio
    2. Tamanho mínimo
    3. Contém marcadores esperados

    Args:
        texto: Texto extraído do PDF
        config: Configurações de validação

    Returns:
        True se o extrato é válido
    """
    if config is None:
        config = ConfigExtratoParalelo()

    # Verifica se não é vazio
    if not texto or not texto.strip():
        return False

    # Verifica tamanho mínimo
    texto_limpo = texto.strip()
    if len(texto_limpo) < config.min_caracteres_extrato:
        return False

    # Verifica se contém ao menos um marcador esperado
    texto_upper = texto_limpo.upper()
    marcadores_encontrados = sum(
        1 for marcador in config.marcadores_extrato
        if marcador in texto_upper
    )

    # Considera válido se encontrou pelo menos 1 marcador
    return marcadores_encontrados >= 1


# =====================================================
# RESULTADO DA EXTRAÇÃO PARALELA
# =====================================================

@dataclass
class MetricasExtracao:
    """Métricas de observabilidade da extração paralela."""

    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    # Tempos em segundos
    t_scrapper: Optional[float] = None
    t_fallback: Optional[float] = None
    t_total: float = 0.0

    # Resultado
    extrato_source: ExtratoSource = ExtratoSource.NONE

    # Motivos de falha (se aplicável)
    scrapper_fail_reason: Optional[ExtratoFailReason] = None
    fallback_fail_reason: Optional[ExtratoFailReason] = None

    # Detalhes adicionais
    scrapper_erro: Optional[str] = None
    fallback_erro: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converte métricas para dicionário."""
        return {
            "correlation_id": self.correlation_id,
            "t_scrapper": round(self.t_scrapper, 3) if self.t_scrapper else None,
            "t_fallback": round(self.t_fallback, 3) if self.t_fallback else None,
            "t_total": round(self.t_total, 3),
            "extrato_source": self.extrato_source.value,
            "scrapper_fail_reason": self.scrapper_fail_reason.value if self.scrapper_fail_reason else None,
            "fallback_fail_reason": self.fallback_fail_reason.value if self.fallback_fail_reason else None,
            "scrapper_erro": self.scrapper_erro,
            "fallback_erro": self.fallback_erro,
        }

    def log(self):
        """Loga métricas formatadas."""
        logger.info(f"[{self.correlation_id}] === MÉTRICAS DE EXTRAÇÃO ===")
        logger.info(f"[{self.correlation_id}] t_scrapper: {self.t_scrapper:.3f}s" if self.t_scrapper else f"[{self.correlation_id}] t_scrapper: N/A")
        logger.info(f"[{self.correlation_id}] t_fallback: {self.t_fallback:.3f}s" if self.t_fallback else f"[{self.correlation_id}] t_fallback: N/A")
        logger.info(f"[{self.correlation_id}] t_total: {self.t_total:.3f}s")
        logger.info(f"[{self.correlation_id}] extrato_source: {self.extrato_source.value}")
        if self.scrapper_fail_reason:
            logger.info(f"[{self.correlation_id}] scrapper_fail: {self.scrapper_fail_reason.value} - {self.scrapper_erro}")
        if self.fallback_fail_reason:
            logger.info(f"[{self.correlation_id}] fallback_fail: {self.fallback_fail_reason.value} - {self.fallback_erro}")


@dataclass
class ResultadoExtratoParalelo:
    """Resultado da extração paralela de extrato."""

    # Dados do extrato
    texto: Optional[str] = None
    pdf_bytes: Optional[bytes] = None
    pdf_base64: Optional[str] = None

    # Imagens (para fallback com PDF de imagem)
    imagens_fallback: List[Dict[str, Any]] = field(default_factory=list)

    # Metadados
    source: ExtratoSource = ExtratoSource.NONE
    valido: bool = False

    # Observação para relatório final (quando extrato não encontrado)
    observacao: Optional[str] = None

    # Métricas
    metricas: MetricasExtracao = field(default_factory=MetricasExtracao)


# =====================================================
# EXTRATOR PARALELO
# =====================================================

class ExtratorParalelo:
    """
    Orquestrador de extração paralela de extrato de subconta.

    Executa Task A (scrapper) e Task B (fallback) em paralelo,
    escolhendo o melhor resultado conforme regras definidas.
    """

    def __init__(
        self,
        config: Optional[ConfigExtratoParalelo] = None,
        correlation_id: Optional[str] = None,
    ):
        self.config = config or ConfigExtratoParalelo()
        self.correlation_id = correlation_id or str(uuid.uuid4())[:8]
        self.metricas = MetricasExtracao(correlation_id=self.correlation_id)

    async def _task_a_scrapper(
        self,
        numero_cnj: str,
    ) -> Tuple[Optional[str], Optional[bytes], Optional[ExtratoFailReason], Optional[str]]:
        """
        Task A: Scrapper do extrato da subconta (primário).

        Returns:
            Tuple de (texto, pdf_bytes, fail_reason, erro_msg)
        """
        inicio = time.time()
        texto = None
        pdf_bytes = None
        fail_reason = None
        erro_msg = None

        try:
            logger.info(f"[{self.correlation_id}] Task A (scrapper): iniciando...")

            # Executa scrapper com timeout
            resultado = await asyncio.wait_for(
                extrair_extrato_subconta(numero_cnj),
                timeout=self.config.scrapper_timeout
            )

            if resultado.status == StatusProcessamento.OK:
                texto = resultado.texto_extraido
                pdf_bytes = resultado.pdf_bytes

                if not is_valid_extrato(texto, self.config):
                    fail_reason = ExtratoFailReason.INVALID
                    erro_msg = f"Texto insuficiente ({len(texto or '')} chars)"
                    texto = None
                    pdf_bytes = None

            elif resultado.status == StatusProcessamento.SEM_SUBCONTA:
                fail_reason = ExtratoFailReason.SEM_SUBCONTA
                erro_msg = "Processo não possui subconta registrada"
            else:
                fail_reason = ExtratoFailReason.ERROR
                erro_msg = resultado.erro

        except asyncio.TimeoutError:
            fail_reason = ExtratoFailReason.TIMEOUT
            erro_msg = f"Timeout após {self.config.scrapper_timeout}s"
            logger.warning(f"[{self.correlation_id}] Task A (scrapper): timeout")

        except Exception as e:
            fail_reason = ExtratoFailReason.ERROR
            erro_msg = str(e)
            logger.error(f"[{self.correlation_id}] Task A (scrapper): erro - {e}")

        finally:
            self.metricas.t_scrapper = time.time() - inicio
            if fail_reason:
                self.metricas.scrapper_fail_reason = fail_reason
                self.metricas.scrapper_erro = erro_msg
                logger.info(f"[{self.correlation_id}] Task A (scrapper): falhou - {fail_reason.value}")
            else:
                logger.info(f"[{self.correlation_id}] Task A (scrapper): sucesso em {self.metricas.t_scrapper:.2f}s")

        return texto, pdf_bytes, fail_reason, erro_msg

    async def _task_b_fallback(
        self,
        numero_cnj: str,
        documentos: List[Any],
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Tuple[Optional[str], Optional[bytes], List[Dict], Optional[ExtratoFailReason], Optional[str]]:
        """
        Task B: Fallback de busca do extrato nos documentos.

        Busca documentos com código 71 (Extrato da Conta Única).

        Returns:
            Tuple de (texto, pdf_bytes, imagens_fallback, fail_reason, erro_msg)
        """
        inicio = time.time()
        texto = None
        pdf_bytes = None
        imagens_fallback = []
        fail_reason = None
        erro_msg = None

        try:
            logger.info(f"[{self.correlation_id}] Task B (fallback): iniciando...")

            # Busca documentos com código 71 (Extrato da Conta Única)
            CODIGO_EXTRATO_CONTA = "71"
            extratos_conta_unica = [
                d for d in documentos
                if str(d.tipo_codigo) == CODIGO_EXTRATO_CONTA
            ]

            if not extratos_conta_unica:
                fail_reason = ExtratoFailReason.NOT_FOUND
                erro_msg = "Nenhum documento código 71 encontrado"
                return texto, pdf_bytes, imagens_fallback, fail_reason, erro_msg

            logger.info(f"[{self.correlation_id}] Task B (fallback): encontrados {len(extratos_conta_unica)} documentos código 71")

            # Cria sessão se não foi passada
            close_session = False
            if session is None:
                session = aiohttp.ClientSession()
                close_session = True

            try:
                textos_extratos = []

                for i, extrato in enumerate(extratos_conta_unica):
                    try:
                        # Baixa documento com timeout
                        xml_docs = await asyncio.wait_for(
                            baixar_documentos_async(session, numero_cnj, [extrato.id]),
                            timeout=self.config.fallback_timeout / len(extratos_conta_unica)
                        )

                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(xml_docs)
                        conteudo_bytes = None

                        for elem in root.iter():
                            if 'conteudo' in elem.tag.lower() and elem.text:
                                conteudo_bytes = base64.b64decode(elem.text)
                                break

                        if conteudo_bytes:
                            texto_extrato = extrair_texto_pdf(conteudo_bytes)
                            data_extrato = extrato.data_juntada.strftime('%d/%m/%Y') if extrato.data_juntada else 'Data desconhecida'

                            # Se texto extraído é muito curto, converte para imagem
                            if len(texto_extrato) < self.config.min_caracteres_util:
                                from sistemas.prestacao_contas.services import converter_pdf_para_imagens
                                imagens = converter_pdf_para_imagens(conteudo_bytes)
                                if imagens:
                                    imagens_fallback.append({
                                        "id": extrato.id,
                                        "tipo": f"Extrato da Conta Única - {data_extrato}",
                                        "imagens": imagens
                                    })
                            else:
                                textos_extratos.append(f"### Extrato da Conta Única {i+1} (ID: {extrato.id}, Data: {data_extrato})\n{texto_extrato}")

                            # Guarda o primeiro PDF para visualização
                            if pdf_bytes is None:
                                pdf_bytes = conteudo_bytes

                    except asyncio.TimeoutError:
                        logger.warning(f"[{self.correlation_id}] Task B: timeout ao baixar documento {extrato.id}")
                        continue
                    except Exception as e:
                        logger.warning(f"[{self.correlation_id}] Task B: erro ao processar documento {extrato.id}: {e}")
                        continue

                # Monta texto final
                if textos_extratos:
                    texto = "## EXTRATOS DA CONTA ÚNICA (FALLBACK DO XML)\n\n" + "\n\n---\n\n".join(textos_extratos)
                    if not is_valid_extrato(texto, self.config):
                        # Texto insuficiente, mas temos imagens
                        if imagens_fallback:
                            texto = f"## EXTRATOS DA CONTA ÚNICA (IMAGENS)\n\n[{len(imagens_fallback)} extrato(s) convertido(s) para imagem]"
                        else:
                            fail_reason = ExtratoFailReason.INVALID
                            erro_msg = f"Texto insuficiente ({len(texto or '')} chars)"
                            texto = None
                elif imagens_fallback:
                    texto = f"## EXTRATOS DA CONTA ÚNICA (IMAGENS)\n\n[{len(imagens_fallback)} extrato(s) convertido(s) para imagem]"
                else:
                    fail_reason = ExtratoFailReason.NOT_FOUND
                    erro_msg = "Nenhum conteúdo extraído dos documentos código 71"

            finally:
                if close_session:
                    await session.close()

        except asyncio.TimeoutError:
            fail_reason = ExtratoFailReason.TIMEOUT
            erro_msg = f"Timeout após {self.config.fallback_timeout}s"

        except Exception as e:
            fail_reason = ExtratoFailReason.ERROR
            erro_msg = str(e)
            logger.error(f"[{self.correlation_id}] Task B (fallback): erro - {e}")

        finally:
            self.metricas.t_fallback = time.time() - inicio
            if fail_reason:
                self.metricas.fallback_fail_reason = fail_reason
                self.metricas.fallback_erro = erro_msg
                logger.info(f"[{self.correlation_id}] Task B (fallback): falhou - {fail_reason.value}")
            else:
                logger.info(f"[{self.correlation_id}] Task B (fallback): sucesso em {self.metricas.t_fallback:.2f}s")

        return texto, pdf_bytes, imagens_fallback, fail_reason, erro_msg

    async def extrair_paralelo(
        self,
        numero_cnj: str,
        documentos: List[Any],
        session: Optional[aiohttp.ClientSession] = None,
    ) -> ResultadoExtratoParalelo:
        """
        Executa extração paralela de extrato.

        Task A (scrapper) e Task B (fallback) são executadas em paralelo.

        Regra de escolha:
        1. Se A válido -> usa A
        2. Se A inválido e B válido -> usa B
        3. Se A e B inválidos -> retorna sem extrato (não bloqueia pipeline)

        Args:
            numero_cnj: Número CNJ do processo
            documentos: Lista de documentos do processo (para fallback)
            session: Sessão HTTP reutilizável

        Returns:
            ResultadoExtratoParalelo com extrato e métricas
        """
        inicio_total = time.time()

        logger.info(f"[{self.correlation_id}] Iniciando extração paralela para {numero_cnj}")

        # Executa Task A e Task B em paralelo
        task_a = asyncio.create_task(
            self._task_a_scrapper(numero_cnj)
        )
        task_b = asyncio.create_task(
            self._task_b_fallback(numero_cnj, documentos, session)
        )

        # Aguarda ambas terminarem
        (texto_a, pdf_a, fail_a, erro_a), (texto_b, pdf_b, imagens_b, fail_b, erro_b) = await asyncio.gather(
            task_a, task_b
        )

        # Calcula tempo total
        self.metricas.t_total = time.time() - inicio_total

        # Aplica regra de escolha
        resultado = ResultadoExtratoParalelo(metricas=self.metricas)

        if texto_a and is_valid_extrato(texto_a, self.config):
            # Task A (scrapper) venceu
            resultado.texto = texto_a
            resultado.pdf_bytes = pdf_a
            resultado.pdf_base64 = base64.b64encode(pdf_a).decode('utf-8') if pdf_a else None
            resultado.source = ExtratoSource.SCRAPPER
            resultado.valido = True
            self.metricas.extrato_source = ExtratoSource.SCRAPPER
            logger.info(f"[{self.correlation_id}] Usando extrato do SCRAPPER ({len(texto_a)} chars)")

        elif texto_b or imagens_b:
            # Task B (fallback) venceu
            resultado.texto = texto_b
            resultado.pdf_bytes = pdf_b
            resultado.pdf_base64 = base64.b64encode(pdf_b).decode('utf-8') if pdf_b else None
            resultado.imagens_fallback = imagens_b
            resultado.source = ExtratoSource.FALLBACK_DOCUMENTOS
            resultado.valido = True
            self.metricas.extrato_source = ExtratoSource.FALLBACK_DOCUMENTOS
            logger.info(f"[{self.correlation_id}] Usando extrato do FALLBACK ({len(texto_b or '')} chars, {len(imagens_b)} imagens)")

        else:
            # Nenhum extrato válido
            resultado.source = ExtratoSource.NONE
            resultado.valido = False
            self.metricas.extrato_source = ExtratoSource.NONE

            # Monta observação para relatório final
            motivos = []
            if fail_a:
                motivos.append(f"Scrapper: {fail_a.value}" + (f" ({erro_a})" if erro_a else ""))
            if fail_b:
                motivos.append(f"Fallback: {fail_b.value}" + (f" ({erro_b})" if erro_b else ""))

            resultado.observacao = (
                "EXTRATO DA SUBCONTA NÃO LOCALIZADO\n"
                f"Motivos: {'; '.join(motivos)}\n"
                "A análise continuará sem o extrato da subconta. "
                "Os valores bloqueados e movimentações não puderam ser verificados automaticamente."
            )

            logger.warning(f"[{self.correlation_id}] Nenhum extrato válido encontrado: {motivos}")

        # Loga métricas
        self.metricas.log()

        return resultado


# =====================================================
# FUNÇÃO DE CONVENIÊNCIA
# =====================================================

async def extrair_extrato_paralelo(
    numero_cnj: str,
    documentos: List[Any],
    config: Optional[ConfigExtratoParalelo] = None,
    session: Optional[aiohttp.ClientSession] = None,
    correlation_id: Optional[str] = None,
) -> ResultadoExtratoParalelo:
    """
    Função de conveniência para extrair extrato em paralelo.

    Args:
        numero_cnj: Número CNJ do processo
        documentos: Lista de documentos do processo
        config: Configurações opcionais
        session: Sessão HTTP reutilizável
        correlation_id: ID de correlação para logs

    Returns:
        ResultadoExtratoParalelo com extrato e métricas
    """
    extrator = ExtratorParalelo(config=config, correlation_id=correlation_id)
    return await extrator.extrair_paralelo(numero_cnj, documentos, session)
