# services/tjms_client.py
"""
Cliente centralizado para comunicação com TJ-MS.

Este módulo centraliza TODAS as configurações e funções de comunicação com o TJ-MS:
- SOAP API (e-SAJ MNI) - consulta de processos, download de documentos
- Subconta - extração de extratos via Playwright

IMPORTANTE - Arquitetura de Proxy:
- O TJ-MS bloqueia requisições de IPs de cloud providers (Railway, Fly.io, etc)
- Por isso usamos proxies para todas as requisições

Proxies disponíveis:
1. PROXY LOCAL (TJMS_PROXY_LOCAL_URL): Seu PC via ngrok - mais rápido para subconta
2. PROXY FLY.IO (TJMS_PROXY_URL): Fly.io - fallback, melhor para SOAP

Uso recomendado:
- SOAP: Fly.io (latência menor, mais estável)
- Subconta: Proxy Local (Playwright roda no PC, sem bloqueio WAF)
"""

import os
import logging
import base64
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


# ==========================
# CONFIGURAÇÃO CENTRALIZADA
# ==========================

@dataclass
class TJMSConfig:
    """Configuração centralizada para comunicação com TJ-MS."""

    # URLs dos proxies
    proxy_local_url: str = ""      # Seu PC via ngrok
    proxy_flyio_url: str = ""      # Fly.io

    # Credenciais SOAP (MNI)
    soap_user: str = ""
    soap_pass: str = ""

    # Credenciais Web (Subconta)
    web_user: str = ""
    web_pass: str = ""

    # Timeouts
    soap_timeout: float = 60.0
    subconta_timeout: float = 180.0

    @classmethod
    def from_env(cls) -> "TJMSConfig":
        """Carrega configuração das variáveis de ambiente."""
        return cls(
            proxy_local_url=os.getenv("TJMS_PROXY_LOCAL_URL", "").strip().rstrip("/"),
            proxy_flyio_url=os.getenv("TJMS_PROXY_URL", "").strip().rstrip("/"),
            soap_user=os.getenv("MNI_USER", "") or os.getenv("TJ_USER", "") or os.getenv("TJ_WS_USER", "") or os.getenv("WS_USER", ""),
            soap_pass=os.getenv("MNI_PASS", "") or os.getenv("TJ_PASS", "") or os.getenv("TJ_WS_PASS", "") or os.getenv("WS_PASS", ""),
            web_user=os.getenv("TJMS_USUARIO", ""),
            web_pass=os.getenv("TJMS_SENHA", ""),
            soap_timeout=float(os.getenv("TJMS_SOAP_TIMEOUT", "60")),
            subconta_timeout=float(os.getenv("TJMS_SUBCONTA_TIMEOUT", "180")),
        )

    @property
    def soap_url(self) -> str:
        """URL do endpoint SOAP (usa Fly.io por padrão - mais rápido)."""
        if self.proxy_flyio_url:
            return f"{self.proxy_flyio_url}/soap"
        if self.proxy_local_url:
            return f"{self.proxy_local_url}/soap"
        # Fallback direto (provavelmente será bloqueado em produção)
        return "https://esaj.tjms.jus.br/mniws/servico-intercomunicacao-2.2.2/intercomunicacao"

    @property
    def subconta_endpoint(self) -> Optional[str]:
        """URL do endpoint /extrair-subconta (usa proxy local - Playwright)."""
        if self.proxy_local_url:
            return f"{self.proxy_local_url}/extrair-subconta"
        return None


# Instância global (singleton)
_config: Optional[TJMSConfig] = None


def get_config() -> TJMSConfig:
    """Obtém configuração global (singleton)."""
    global _config
    if _config is None:
        _config = TJMSConfig.from_env()
    return _config


def reload_config() -> TJMSConfig:
    """Recarrega configuração das variáveis de ambiente."""
    global _config
    _config = TJMSConfig.from_env()
    return _config


# ==========================
# CLIENTE SOAP
# ==========================

def _build_soap_envelope(operation: str, body_content: str) -> str:
    """Constrói envelope SOAP."""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/"
                  xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
    <soapenv:Header/>
    <soapenv:Body>
        {body_content}
    </soapenv:Body>
</soapenv:Envelope>'''


async def soap_consultar_processo(
    numero_processo: str,
    movimentos: bool = True,
    incluir_documentos: bool = True,
    config: Optional[TJMSConfig] = None,
) -> str:
    """
    Consulta processo via SOAP (MNI).

    Args:
        numero_processo: Número CNJ do processo (com ou sem formatação)
        movimentos: Incluir movimentos processuais
        incluir_documentos: Incluir lista de documentos
        config: Configuração (usa global se não fornecida)

    Returns:
        XML de resposta do TJ-MS

    Raises:
        httpx.HTTPError: Erro de comunicação
    """
    cfg = config or get_config()

    # Limpa número do processo (remove formatação)
    numero_limpo = "".join(c for c in numero_processo if c.isdigit())

    body = f'''<ser:consultarProcesso>
            <tip:idConsultante>{cfg.soap_user}</tip:idConsultante>
            <tip:senhaConsultante>{cfg.soap_pass}</tip:senhaConsultante>
            <tip:numeroProcesso>{numero_limpo}</tip:numeroProcesso>
            <tip:movimentos>{"true" if movimentos else "false"}</tip:movimentos>
            <tip:incluirDocumentos>{"true" if incluir_documentos else "false"}</tip:incluirDocumentos>
        </ser:consultarProcesso>'''

    envelope = _build_soap_envelope("consultarProcesso", body)

    async with httpx.AsyncClient(timeout=cfg.soap_timeout) as client:
        response = await client.post(
            cfg.soap_url,
            content=envelope,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "",
            },
        )
        response.raise_for_status()
        return response.text


async def soap_baixar_documentos(
    numero_processo: str,
    ids_documentos: list[str],
    config: Optional[TJMSConfig] = None,
) -> str:
    """
    Baixa conteúdo de documentos específicos via SOAP.

    Args:
        numero_processo: Número CNJ do processo
        ids_documentos: Lista de IDs dos documentos a baixar
        config: Configuração (usa global se não fornecida)

    Returns:
        XML de resposta com documentos em base64
    """
    cfg = config or get_config()

    numero_limpo = "".join(c for c in numero_processo if c.isdigit())

    docs_xml = "".join(f"<tip:documento>{doc_id}</tip:documento>" for doc_id in ids_documentos)

    body = f'''<ser:consultarProcesso>
            <tip:idConsultante>{cfg.soap_user}</tip:idConsultante>
            <tip:senhaConsultante>{cfg.soap_pass}</tip:senhaConsultante>
            <tip:numeroProcesso>{numero_limpo}</tip:numeroProcesso>
            {docs_xml}
        </ser:consultarProcesso>'''

    envelope = _build_soap_envelope("consultarProcesso", body)

    # Timeout maior para download de documentos
    timeout = httpx.Timeout(180.0, connect=30.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            cfg.soap_url,
            content=envelope,
            headers={
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "",
            },
        )
        response.raise_for_status()
        return response.text


# ==========================
# CLIENTE SUBCONTA
# ==========================

@dataclass
class ResultadoSubconta:
    """Resultado da extração de extrato de subconta."""
    numero_processo: str
    status: str  # "ok", "sem_subconta", "erro"
    pdf_bytes: Optional[bytes] = None
    texto_extraido: Optional[str] = None
    erro: Optional[str] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat(timespec="seconds")


async def extrair_subconta(
    numero_processo: str,
    config: Optional[TJMSConfig] = None,
) -> ResultadoSubconta:
    """
    Extrai extrato de subconta de um processo.

    Usa o endpoint /extrair-subconta do proxy local, que executa
    Playwright diretamente no PC (sem problemas com WAF).

    Args:
        numero_processo: Número CNJ do processo
        config: Configuração (usa global se não fornecida)

    Returns:
        ResultadoSubconta com PDF e texto extraído
    """
    cfg = config or get_config()

    endpoint = cfg.subconta_endpoint
    if not endpoint:
        return ResultadoSubconta(
            numero_processo=numero_processo,
            status="erro",
            erro="Proxy local não configurado (TJMS_PROXY_LOCAL_URL)",
        )

    try:
        logger.info(f"Extraindo subconta via proxy local: {numero_processo}")

        timeout = httpx.Timeout(cfg.subconta_timeout, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint,
                json={"numero_processo": numero_processo},
                headers={"ngrok-skip-browser-warning": "true"},
            )

            if response.status_code == 200:
                data = response.json()

                pdf_bytes = None
                if data.get("pdf_base64"):
                    pdf_bytes = base64.b64decode(data["pdf_base64"])

                return ResultadoSubconta(
                    numero_processo=data["numero_processo"],
                    status=data["status"],
                    pdf_bytes=pdf_bytes,
                    texto_extraido=data.get("texto_extraido"),
                    erro=data.get("erro"),
                    timestamp=data.get("timestamp", ""),
                )
            else:
                return ResultadoSubconta(
                    numero_processo=numero_processo,
                    status="erro",
                    erro=f"HTTP {response.status_code}: {response.text[:200]}",
                )

    except httpx.ConnectError:
        logger.warning("Proxy local não disponível")
        return ResultadoSubconta(
            numero_processo=numero_processo,
            status="erro",
            erro="Proxy local não disponível (conexão recusada)",
        )

    except httpx.TimeoutException:
        logger.warning("Timeout ao extrair subconta")
        return ResultadoSubconta(
            numero_processo=numero_processo,
            status="erro",
            erro="Timeout ao extrair subconta",
        )

    except Exception as e:
        logger.error(f"Erro ao extrair subconta: {e}")
        return ResultadoSubconta(
            numero_processo=numero_processo,
            status="erro",
            erro=f"{type(e).__name__}: {str(e)}",
        )


# ==========================
# UTILITÁRIOS
# ==========================

async def verificar_conexao_proxy(proxy_url: str) -> Tuple[bool, float, str]:
    """
    Verifica se um proxy está acessível.

    Returns:
        Tuple (sucesso, tempo_ms, mensagem)
    """
    import time

    try:
        start = time.time()
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                proxy_url,
                headers={"ngrok-skip-browser-warning": "true"},
            )
            tempo_ms = (time.time() - start) * 1000

            if response.status_code == 200:
                return True, tempo_ms, "OK"
            else:
                return False, tempo_ms, f"HTTP {response.status_code}"

    except Exception as e:
        return False, 0, f"{type(e).__name__}: {str(e)}"


async def diagnostico_tjms() -> dict:
    """
    Executa diagnóstico completo de conectividade com TJ-MS.

    Returns:
        Dict com status de cada componente
    """
    cfg = get_config()
    resultado = {
        "config": {
            "proxy_local": cfg.proxy_local_url or "(não configurado)",
            "proxy_flyio": cfg.proxy_flyio_url or "(não configurado)",
            "soap_url": cfg.soap_url,
            "subconta_endpoint": cfg.subconta_endpoint or "(não configurado)",
        },
        "testes": {},
    }

    # Testa proxy local
    if cfg.proxy_local_url:
        ok, tempo, msg = await verificar_conexao_proxy(cfg.proxy_local_url)
        resultado["testes"]["proxy_local"] = {
            "ok": ok,
            "tempo_ms": round(tempo, 1),
            "mensagem": msg,
        }

    # Testa proxy Fly.io
    if cfg.proxy_flyio_url:
        ok, tempo, msg = await verificar_conexao_proxy(cfg.proxy_flyio_url)
        resultado["testes"]["proxy_flyio"] = {
            "ok": ok,
            "tempo_ms": round(tempo, 1),
            "mensagem": msg,
        }

    return resultado
