# services/tjms/client.py
"""
Cliente unificado para comunicacao com TJ-MS.

Este e o ponto de entrada principal para todas as operacoes TJMS.

Inclui:
- Retry com backoff exponencial para operações SOAP
- Timeouts configuráveis
- Tratamento de erros específicos do TJ-MS
"""

import asyncio
import base64
import logging
from typing import Optional, List, Dict, Any

import httpx

from .config import TJMSConfig, get_config
from .models import (
    ProcessoTJMS,
    DocumentoTJMS,
    DocumentoMetadata,
    ConsultaOptions,
    DownloadOptions,
    TipoConsulta,
    ResultadoSubconta,
)
from .parsers import XMLParserTJMS, extrair_conteudo_documento
from utils.retry import retry_async, RETRY_CONFIG_TJMS, RetryConfig
from utils.circuit_breaker import (
    get_tjms_circuit_breaker,
    CircuitOpenError,
    CircuitBreaker,
)

logger = logging.getLogger(__name__)

# Circuit Breaker para TJ-MS (singleton)
_tjms_circuit_breaker: CircuitBreaker = None


def _limpar_numero_processo(numero: str) -> str:
    """
    Remove formatação do número do processo para enviar ao TJ-MS.

    O TJ-MS espera exatamente 20 dígitos sem pontos, traços ou barras.
    Ex: '0808281-22.2025.8.12.0002' -> '08082812220258120002'
    """
    if not numero:
        return ""
    if '/' in numero:
        numero = numero.split('/')[0]
    return ''.join(c for c in numero if c.isdigit())


def get_circuit_breaker() -> CircuitBreaker:
    """Obtém o Circuit Breaker do TJ-MS (singleton)."""
    global _tjms_circuit_breaker
    if _tjms_circuit_breaker is None:
        _tjms_circuit_breaker = get_tjms_circuit_breaker()
    return _tjms_circuit_breaker


# Exceções específicas que devem disparar retry no TJ-MS
TJMS_RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ConnectTimeout,
    ConnectionError,
    asyncio.TimeoutError,
)


class TJMSError(Exception):
    """Erro generico de comunicacao com TJ-MS."""
    pass


class TJMSTimeoutError(TJMSError):
    """Timeout na comunicacao com TJ-MS."""
    pass


class TJMSAuthError(TJMSError):
    """Erro de autenticacao com TJ-MS."""
    pass


class TJMSRetryableError(TJMSError):
    """
    Erro temporário que pode ser resolvido com retry.

    Usado para erros de rede, timeouts e HTTP 5xx.
    """
    pass


class TJMSCircuitOpenError(TJMSError):
    """
    Erro lançado quando o circuit breaker está aberto.

    Indica que o TJ-MS está temporariamente indisponível
    e requisições estão sendo rejeitadas para evitar sobrecarga.
    """

    def __init__(self, retry_after: float = None):
        self.retry_after = retry_after
        message = "TJ-MS temporariamente indisponível (circuit breaker aberto)"
        if retry_after:
            message += f" - retry em {retry_after:.0f}s"
        super().__init__(message)


class TJMSClient:
    """
    Cliente unificado para comunicacao com TJ-MS.

    Centraliza todas as operacoes SOAP e download de documentos,
    permitindo customizacao por sistema via options.

    Exemplo de uso:

        # Uso simples (defaults)
        async with TJMSClient() as client:
            processo = await client.consultar_processo("0800001-00.2024.8.12.0001")

        # Uso com opcoes customizadas
        client = TJMSClient()
        opts = ConsultaOptions(tipo=TipoConsulta.MOVIMENTOS_ONLY, timeout=90)
        processo = await client.consultar_processo(cnj, opts)

        # Download de documentos
        download_opts = DownloadOptions(batch_size=3, extrair_texto=True)
        docs = await client.baixar_documentos(cnj, ids, download_opts)
    """

    def __init__(self, config: Optional[TJMSConfig] = None):
        """
        Inicializa o cliente.

        Args:
            config: Configuracao personalizada (opcional, usa global se nao fornecida)
        """
        self.config = config or get_config()
        self._client: Optional[httpx.AsyncClient] = None
        self._owns_client = False

    async def __aenter__(self):
        """Contexto async - cria cliente HTTP."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.soap_timeout, connect=30.0)
            )
            self._owns_client = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Contexto async - fecha cliente HTTP."""
        if self._owns_client and self._client:
            await self._client.aclose()
            self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Obtem cliente HTTP, criando se necessario."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.soap_timeout, connect=30.0)
            )
            self._owns_client = True
        return self._client

    # ========== CONSULTA DE PROCESSO ==========

    async def consultar_processo(
        self,
        numero_cnj: str,
        options: Optional[ConsultaOptions] = None
    ) -> ProcessoTJMS:
        """
        Consulta processo no TJ-MS.

        Args:
            numero_cnj: Numero CNJ (com ou sem formatacao)
            options: Opcoes de consulta (opcional)

        Returns:
            ProcessoTJMS com dados estruturados

        Raises:
            TJMSError: Em caso de erro de comunicacao
            TJMSTimeoutError: Em caso de timeout
            TJMSCircuitOpenError: Em caso de circuit breaker aberto
        """
        opts = options or ConsultaOptions()

        # Limpa numero
        numero_limpo = "".join(c for c in numero_cnj if c.isdigit())
        if len(numero_limpo) != 20:
            raise TJMSError(f"Numero CNJ invalido: {numero_cnj}")

        # Verifica circuit breaker
        cb = get_circuit_breaker()
        if not cb.allow_request():
            retry_after = cb.time_until_retry()
            logger.warning(
                f"Circuit breaker aberto para TJ-MS, rejeitando consulta do processo {numero_limpo}"
            )
            raise TJMSCircuitOpenError(retry_after)

        logger.info(f"Consultando processo {numero_limpo} (tipo={opts.tipo.value})")

        try:
            # Executa consulta SOAP
            xml_response = await self._soap_consultar_processo(
                numero_limpo,
                movimentos=opts.incluir_movimentos,
                incluir_documentos=opts.incluir_documentos,
                timeout=opts.timeout or self.config.soap_timeout
            )

            # Parseia XML
            parser = XMLParserTJMS(xml_response)
            processo = parser.parse()

            # Registra sucesso no circuit breaker
            cb.record_success()

            logger.info(
                f"Processo {numero_limpo} consultado: "
                f"{len(processo.movimentos)} movimentos, "
                f"{len(processo.documentos)} documentos"
            )

            return processo

        except (TJMSTimeoutError, TJMSRetryableError) as e:
            # Registra falha no circuit breaker
            cb.record_failure(e)
            raise

        except TJMSAuthError:
            # Erro de auth não conta como falha do serviço
            raise

        except Exception as e:
            # Outros erros também registram falha
            cb.record_failure(e)
            raise

    async def _soap_consultar_processo(
        self,
        numero_processo: str,
        movimentos: bool = True,
        incluir_documentos: bool = True,
        timeout: float = 60.0
    ) -> str:
        """
        Executa consulta SOAP com retry automático.

        Implementa retry com backoff exponencial para erros transientes
        (timeout, conexão, HTTP 5xx).
        """
        envelope = self._build_soap_envelope_consulta(
            numero_processo,
            movimentos=movimentos,
            incluir_documentos=incluir_documentos
        )

        # Configuração de retry específica para TJ-MS
        retry_config = RetryConfig(
            max_retries=3,
            base_delay=2.0,
            max_delay=30.0,
            jitter=True,
            jitter_factor=0.3,
            retryable_exceptions=TJMS_RETRYABLE_EXCEPTIONS + (TJMSRetryableError,),
        )

        @retry_async(config=retry_config, log_retries=True)
        async def _execute_soap_request():
            client = await self._get_client()
            try:
                response = await client.post(
                    self.config.soap_url,
                    content=envelope,
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": "",
                    },
                    timeout=timeout,
                )

                # HTTP 5xx são retryable
                if response.status_code in (500, 502, 503, 504):
                    logger.warning(
                        f"TJ-MS retornou HTTP {response.status_code} para processo {numero_processo}"
                    )
                    raise TJMSRetryableError(f"HTTP {response.status_code}")

                response.raise_for_status()
                return response.text

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise TJMSAuthError("Credenciais SOAP invalidas")
                if e.response.status_code == 429:
                    # Rate limit - retry
                    raise TJMSRetryableError("Rate limit (429)")
                logger.error(f"Erro HTTP ao consultar processo: {e}")
                raise TJMSError(f"Erro HTTP: {e.response.status_code}")

        try:
            return await _execute_soap_request()

        except TJMS_RETRYABLE_EXCEPTIONS as e:
            logger.error(f"Timeout ao consultar processo {numero_processo} após retries: {e}")
            raise TJMSTimeoutError(f"Timeout ao consultar TJ-MS após retries: {e}")

        except TJMSRetryableError as e:
            logger.error(f"Erro retryable ao consultar processo {numero_processo} após retries: {e}")
            raise TJMSError(f"Erro ao consultar TJ-MS após retries: {e}")

        except (TJMSAuthError, TJMSError):
            raise

        except Exception as e:
            logger.error(f"Erro ao consultar processo {numero_processo}: {e}")
            raise TJMSError(f"Erro ao consultar TJ-MS: {e}")

    def _build_soap_envelope_consulta(
        self,
        numero_processo: str,
        movimentos: bool = True,
        incluir_documentos: bool = True
    ) -> str:
        """Constroi envelope SOAP para consulta de processo."""
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
                  xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
    <soapenv:Header/>
    <soapenv:Body>
        <ser:consultarProcesso>
            <tip:idConsultante>{self.config.soap_user}</tip:idConsultante>
            <tip:senhaConsultante>{self.config.soap_pass}</tip:senhaConsultante>
            <tip:numeroProcesso>{numero_processo}</tip:numeroProcesso>
            <tip:movimentos>{"true" if movimentos else "false"}</tip:movimentos>
            <tip:incluirDocumentos>{"true" if incluir_documentos else "false"}</tip:incluirDocumentos>
        </ser:consultarProcesso>
    </soapenv:Body>
</soapenv:Envelope>'''

    # ========== DOWNLOAD DE DOCUMENTOS ==========

    async def baixar_documento(
        self,
        numero_cnj: str,
        doc_id: str,
        options: Optional[DownloadOptions] = None
    ) -> DocumentoTJMS:
        """
        Baixa um documento especifico.

        Args:
            numero_cnj: Numero CNJ do processo
            doc_id: ID do documento
            options: Opcoes de download

        Returns:
            DocumentoTJMS com conteudo
        """
        docs = await self.baixar_documentos(numero_cnj, [doc_id], options)
        return docs.get(doc_id, DocumentoTJMS(
            id=doc_id,
            numero_processo=numero_cnj,
            erro="Documento nao encontrado na resposta"
        ))

    async def baixar_documentos(
        self,
        numero_cnj: str,
        ids_documentos: List[str],
        options: Optional[DownloadOptions] = None
    ) -> Dict[str, DocumentoTJMS]:
        """
        Baixa multiplos documentos em paralelo.

        Args:
            numero_cnj: Numero CNJ do processo
            ids_documentos: Lista de IDs de documentos
            options: Opcoes de download

        Returns:
            Dict[doc_id -> DocumentoTJMS]

        Raises:
            TJMSCircuitOpenError: Em caso de circuit breaker aberto
        """
        opts = options or DownloadOptions()
        numero_limpo = "".join(c for c in numero_cnj if c.isdigit())

        # Verifica circuit breaker
        cb = get_circuit_breaker()
        if not cb.allow_request():
            retry_after = cb.time_until_retry()
            logger.warning(
                f"Circuit breaker aberto para TJ-MS, rejeitando download de documentos"
            )
            raise TJMSCircuitOpenError(retry_after)

        logger.info(
            f"Baixando {len(ids_documentos)} documentos do processo {numero_limpo} "
            f"(batch_size={opts.batch_size})"
        )

        resultado: Dict[str, DocumentoTJMS] = {}
        has_failure = False

        # Processa em batches
        for i in range(0, len(ids_documentos), opts.batch_size):
            batch = ids_documentos[i:i + opts.batch_size]
            batch_num = i // opts.batch_size + 1
            total_batches = (len(ids_documentos) + opts.batch_size - 1) // opts.batch_size

            logger.debug(f"Processando batch {batch_num}/{total_batches}: {len(batch)} docs")

            try:
                batch_result = await self._baixar_batch(numero_limpo, batch, opts)
                resultado.update(batch_result)
            except Exception as e:
                logger.error(f"Erro no batch {batch_num}: {e}")
                has_failure = True
                # Marca documentos do batch como erro
                for doc_id in batch:
                    if doc_id not in resultado:
                        resultado[doc_id] = DocumentoTJMS(
                            id=doc_id,
                            numero_processo=numero_cnj,
                            erro=str(e)
                        )

        sucesso = sum(1 for d in resultado.values() if d.sucesso)
        logger.info(f"Download concluido: {sucesso}/{len(ids_documentos)} documentos")

        # Registra no circuit breaker
        if has_failure:
            cb.record_failure()
        else:
            cb.record_success()

        return resultado

    async def _baixar_batch(
        self,
        numero_processo: str,
        ids: List[str],
        opts: DownloadOptions
    ) -> Dict[str, DocumentoTJMS]:
        """
        Baixa um batch de documentos com retry automático.

        Implementa retry com backoff exponencial para erros transientes.
        """
        resultado: Dict[str, DocumentoTJMS] = {}

        # Monta envelope SOAP com lista de documentos
        envelope = self._build_soap_envelope_documentos(numero_processo, ids)
        timeout = opts.timeout or self.config.download_timeout

        # Configuração de retry para downloads (mais tolerante)
        retry_config = RetryConfig(
            max_retries=3,
            base_delay=3.0,  # Maior delay para downloads
            max_delay=45.0,
            jitter=True,
            jitter_factor=0.3,
            retryable_exceptions=TJMS_RETRYABLE_EXCEPTIONS + (TJMSRetryableError,),
        )

        @retry_async(config=retry_config, log_retries=True)
        async def _execute_download():
            client = await self._get_client()
            response = await client.post(
                self.config.soap_url,
                content=envelope,
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": "",
                },
                timeout=timeout,
            )

            # HTTP 5xx são retryable
            if response.status_code in (500, 502, 503, 504):
                logger.warning(f"TJ-MS retornou HTTP {response.status_code} ao baixar documentos")
                raise TJMSRetryableError(f"HTTP {response.status_code}")

            if response.status_code == 429:
                raise TJMSRetryableError("Rate limit (429)")

            response.raise_for_status()
            return response.text

        try:
            xml_response = await _execute_download()

            # Extrai conteudo de cada documento
            for doc_id in ids:
                conteudo = extrair_conteudo_documento(xml_response, doc_id)
                if conteudo:
                    resultado[doc_id] = DocumentoTJMS(
                        id=doc_id,
                        numero_processo=numero_processo,
                        conteudo_bytes=conteudo,
                    )
                else:
                    resultado[doc_id] = DocumentoTJMS(
                        id=doc_id,
                        numero_processo=numero_processo,
                        erro="Conteudo nao encontrado na resposta"
                    )

        except TJMS_RETRYABLE_EXCEPTIONS as e:
            logger.error(f"Timeout ao baixar documentos após retries: {e}")
            for doc_id in ids:
                resultado[doc_id] = DocumentoTJMS(
                    id=doc_id,
                    numero_processo=numero_processo,
                    erro=f"Timeout após retries: {e}"
                )

        except TJMSRetryableError as e:
            logger.error(f"Erro retryable ao baixar documentos após retries: {e}")
            for doc_id in ids:
                resultado[doc_id] = DocumentoTJMS(
                    id=doc_id,
                    numero_processo=numero_processo,
                    erro=f"Erro após retries: {e}"
                )

        except Exception as e:
            logger.error(f"Erro ao baixar batch: {e}")
            for doc_id in ids:
                resultado[doc_id] = DocumentoTJMS(
                    id=doc_id,
                    numero_processo=numero_processo,
                    erro=str(e)
                )

        return resultado

    def _build_soap_envelope_documentos(
        self,
        numero_processo: str,
        ids_documentos: List[str]
    ) -> str:
        """Constroi envelope SOAP para download de documentos."""
        # Limpa número do processo (TJ-MS espera 20 dígitos sem formatação)
        numero_limpo = _limpar_numero_processo(numero_processo)

        docs_xml = "".join(
            f"<tip:documento>{doc_id}</tip:documento>"
            for doc_id in ids_documentos
        )

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
                  xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
    <soapenv:Header/>
    <soapenv:Body>
        <ser:consultarProcesso>
            <tip:idConsultante>{self.config.soap_user}</tip:idConsultante>
            <tip:senhaConsultante>{self.config.soap_pass}</tip:senhaConsultante>
            <tip:numeroProcesso>{numero_limpo}</tip:numeroProcesso>
            {docs_xml}
        </ser:consultarProcesso>
    </soapenv:Body>
</soapenv:Envelope>'''

    # ========== LISTAGEM DE DOCUMENTOS ==========

    async def listar_documentos(
        self,
        numero_cnj: str,
        tipos_permitidos: Optional[List[int]] = None,
        tipos_excluidos: Optional[List[int]] = None
    ) -> List[DocumentoMetadata]:
        """
        Lista documentos disponiveis sem baixar conteudo.

        Args:
            numero_cnj: Numero CNJ do processo
            tipos_permitidos: Whitelist de tipos (opcional)
            tipos_excluidos: Blacklist de tipos (opcional)

        Returns:
            Lista de DocumentoMetadata
        """
        processo = await self.consultar_processo(
            numero_cnj,
            ConsultaOptions(tipo=TipoConsulta.COMPLETA)
        )

        documentos = processo.documentos

        if tipos_permitidos is not None:
            documentos = [d for d in documentos if d.tipo_codigo in tipos_permitidos]
        elif tipos_excluidos is not None:
            documentos = [d for d in documentos if d.tipo_codigo not in tipos_excluidos]

        return documentos

    # ========== SUBCONTA ==========

    async def extrair_subconta(
        self,
        numero_cnj: str
    ) -> ResultadoSubconta:
        """
        Extrai extrato de subconta via proxy local (Playwright).

        Args:
            numero_cnj: Numero CNJ do processo

        Returns:
            ResultadoSubconta com PDF e texto
        """
        numero_limpo = "".join(c for c in numero_cnj if c.isdigit())

        endpoint = self.config.subconta_endpoint
        if not endpoint:
            return ResultadoSubconta(
                numero_processo=numero_limpo,
                status="erro",
                erro="Proxy local nao configurado (TJMS_PROXY_LOCAL_URL)",
            )

        logger.info(f"Extraindo subconta do processo {numero_limpo}")

        client = await self._get_client()

        try:
            response = await client.post(
                endpoint,
                json={"numero_processo": numero_limpo},
                headers={"ngrok-skip-browser-warning": "true"},
                timeout=self.config.subconta_timeout,
            )

            if response.status_code == 200:
                data = response.json()

                pdf_bytes = None
                if data.get("pdf_base64"):
                    pdf_bytes = base64.b64decode(data["pdf_base64"])

                return ResultadoSubconta(
                    numero_processo=data.get("numero_processo", numero_limpo),
                    status=data.get("status", "erro"),
                    pdf_bytes=pdf_bytes,
                    texto_extraido=data.get("texto_extraido"),
                    erro=data.get("erro"),
                    timestamp=data.get("timestamp", ""),
                )
            else:
                return ResultadoSubconta(
                    numero_processo=numero_limpo,
                    status="erro",
                    erro=f"HTTP {response.status_code}: {response.text[:200]}",
                )

        except httpx.ConnectError:
            logger.warning("Proxy local nao disponivel para subconta")
            return ResultadoSubconta(
                numero_processo=numero_limpo,
                status="erro",
                erro="Proxy local nao disponivel (conexao recusada)",
            )

        except httpx.TimeoutException:
            logger.warning("Timeout ao extrair subconta")
            return ResultadoSubconta(
                numero_processo=numero_limpo,
                status="erro",
                erro="Timeout ao extrair subconta",
            )

        except Exception as e:
            logger.error(f"Erro ao extrair subconta: {e}")
            return ResultadoSubconta(
                numero_processo=numero_limpo,
                status="erro",
                erro=f"{type(e).__name__}: {str(e)}",
            )

    # ========== DIAGNOSTICO ==========

    async def diagnostico(self) -> Dict[str, Any]:
        """
        Executa diagnostico completo de conectividade.

        Returns:
            Dict com status de cada componente
        """
        resultado = {
            "config": {
                "proxy_local": self.config.proxy_local_url or "(nao configurado)",
                "proxy_flyio": self.config.proxy_flyio_url or "(nao configurado)",
                "soap_url": self.config.soap_url,
                "subconta_endpoint": self.config.subconta_endpoint or "(nao configurado)",
                "soap_user_configurado": bool(self.config.soap_user),
            },
            "testes": {},
        }

        client = await self._get_client()

        # Testa proxy Fly.io
        if self.config.proxy_flyio_url:
            try:
                import time
                start = time.time()
                response = await client.get(
                    self.config.proxy_flyio_url,
                    timeout=10.0
                )
                tempo_ms = (time.time() - start) * 1000
                resultado["testes"]["proxy_flyio"] = {
                    "ok": response.status_code == 200,
                    "tempo_ms": round(tempo_ms, 1),
                    "status_code": response.status_code,
                }
            except Exception as e:
                resultado["testes"]["proxy_flyio"] = {
                    "ok": False,
                    "erro": str(e),
                }

        # Testa proxy local
        if self.config.proxy_local_url:
            try:
                import time
                start = time.time()
                response = await client.get(
                    self.config.proxy_local_url,
                    headers={"ngrok-skip-browser-warning": "true"},
                    timeout=10.0
                )
                tempo_ms = (time.time() - start) * 1000
                resultado["testes"]["proxy_local"] = {
                    "ok": response.status_code == 200,
                    "tempo_ms": round(tempo_ms, 1),
                    "status_code": response.status_code,
                }
            except Exception as e:
                resultado["testes"]["proxy_local"] = {
                    "ok": False,
                    "erro": str(e),
                }

        # Adiciona status do circuit breaker
        cb = get_circuit_breaker()
        resultado["circuit_breaker"] = cb.get_stats()

        return resultado


# ========== SINGLETON ==========

_client: Optional[TJMSClient] = None


def get_client() -> TJMSClient:
    """
    Retorna instancia singleton do cliente.

    Para uso simples sem contexto async:
        client = get_client()
        processo = await client.consultar_processo(cnj)
    """
    global _client
    if _client is None:
        _client = TJMSClient()
    return _client


def reset_client() -> None:
    """Reseta o cliente singleton (util para testes)."""
    global _client
    _client = None
