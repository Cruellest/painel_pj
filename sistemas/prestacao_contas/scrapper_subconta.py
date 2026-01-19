# sistemas/prestacao_contas/scrapper_subconta.py
"""
Scrapper de Extratos de Subconta - TJ-MS
Adaptado para uso assíncrono com FastAPI.

Baseado no projeto E:/Projetos/Ressarcimento/Scrapper Subconta
"""

import asyncio
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv

# Carrega variáveis do .env
load_dotenv()

logger = logging.getLogger(__name__)


# ==========================
# CONFIGURAÇÕES
# ==========================

@dataclass
class ConfigSubconta:
    """Configurações do scrapper de subconta."""

    # URLs base - usadas para acesso direto (local)
    base_url_www: str = "https://www.tjms.jus.br"
    base_url_www5: str = "https://www5.tjms.jus.br"

    # URL do proxy (produção)
    base_url: str = ""
    usar_proxy: bool = False

    delay_min: float = 2.0
    delay_max: float = 5.0
    max_tentativas: int = 3
    timeout_navegacao: int = 60_000  # ms - aumentado para ambientes cloud
    headless: bool = True

    @property
    def login_url(self) -> str:
        if self.usar_proxy:
            return f"{self.base_url}/www5/login/?forwardTo=/contaunica/"
        return f"{self.base_url_www5}/login/?forwardTo=/contaunica/"

    @property
    def listagem_url(self) -> str:
        if self.usar_proxy:
            return f"{self.base_url}/contaunica/subconta_listagem.php"
        return f"{self.base_url_www}/contaunica/subconta_listagem.php"

    @classmethod
    def from_env(cls) -> "ConfigSubconta":
        """Cria configuração a partir de variáveis de ambiente com fallback automático."""
        import httpx

        # Proxies disponíveis (ordem de prioridade)
        proxy_local = os.getenv("TJMS_PROXY_LOCAL_URL", "").strip()  # Seu PC via Cloudflare Tunnel
        proxy_flyio = os.getenv("TJMS_PROXY_URL", "").strip()  # Fly.io + BrightData

        # Configurações comuns
        config_base = dict(
            delay_min=float(os.getenv("SUBCONTA_DELAY_MIN", 2.0)),
            delay_max=float(os.getenv("SUBCONTA_DELAY_MAX", 5.0)),
            max_tentativas=int(os.getenv("SUBCONTA_MAX_TENTATIVAS", 3)),
            headless=os.getenv("SUBCONTA_HEADLESS", "true").lower() == "true",
        )

        # Tenta proxy local primeiro (mais rápido)
        if proxy_local:
            try:
                r = httpx.get(f"{proxy_local.rstrip('/')}/", timeout=5)
                if r.status_code == 200:
                    logger.info(f"Usando proxy LOCAL: {proxy_local}")
                    return cls(base_url=proxy_local.rstrip("/"), usar_proxy=True, **config_base)
            except Exception as e:
                logger.debug(f"Proxy local indisponível: {e}")

        # Fallback para Fly.io
        if proxy_flyio:
            try:
                r = httpx.get(f"{proxy_flyio.rstrip('/')}/", timeout=10)
                if r.status_code == 200:
                    logger.info(f"Usando proxy FLY.IO: {proxy_flyio}")
                    return cls(base_url=proxy_flyio.rstrip("/"), usar_proxy=True, **config_base)
            except Exception as e:
                logger.debug(f"Proxy Fly.io indisponível: {e}")

        # Acesso direto (sem proxy)
        logger.info("Usando acesso DIRETO (sem proxy)")
        return cls(**config_base)


class StatusProcessamento(str, Enum):
    """Status do processamento."""
    OK = "ok"
    SEM_SUBCONTA = "sem_subconta"
    ERRO = "erro"


@dataclass
class ResultadoExtracao:
    """Resultado da extração do extrato."""

    numero_processo: str
    status: StatusProcessamento
    pdf_bytes: Optional[bytes] = None
    texto_extraido: Optional[str] = None
    erro: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ==========================
# EXTRATOR PRINCIPAL
# ==========================

class ExtratorSubconta:
    """
    Extrator de PDFs de extratos de subconta do TJ-MS.
    Versão adaptada para uso assíncrono com FastAPI.
    """

    # Aceita formato com pontuação: 0810365-40.2018.8.12.0002
    PADRAO_CNJ_FORMATADO = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")
    # Aceita formato só números: 08103654020188120002 (20 dígitos)
    PADRAO_CNJ_NUMERICO = re.compile(r"^\d{20}$")

    MSG_SEM_SUBCONTA = "Nenhuma Subconta encontrada ou sem acesso."

    def __init__(self, config: Optional[ConfigSubconta] = None):
        self.config = config or ConfigSubconta.from_env()
        self._browser = None
        self._page = None
        self._playwright = None

    def _validar_numero_processo(self, numero: str) -> bool:
        """Valida formato CNJ do número do processo."""
        return bool(
            self.PADRAO_CNJ_FORMATADO.match(numero) or
            self.PADRAO_CNJ_NUMERICO.match(numero)
        )

    def _formatar_cnj(self, numero: str) -> str:
        """Converte número CNJ para formato com pontuação."""
        if self.PADRAO_CNJ_FORMATADO.match(numero):
            return numero

        # Remove tudo que não é dígito
        numero_limpo = re.sub(r'\D', '', numero)

        if len(numero_limpo) != 20:
            return numero  # Retorna original se não tiver 20 dígitos

        # Formata: NNNNNNN-DD.AAAA.J.TR.OOOO
        return f"{numero_limpo[:7]}-{numero_limpo[7:9]}.{numero_limpo[9:13]}.{numero_limpo[13]}.{numero_limpo[14:16]}.{numero_limpo[16:]}"

    def _obter_credenciais(self) -> Tuple[str, str]:
        """Obtém credenciais do arquivo .env."""
        usuario = os.getenv("TJMS_USUARIO")
        senha = os.getenv("TJMS_SENHA")

        if not usuario or not senha:
            raise ValueError(
                "Credenciais TJMS_USUARIO e TJMS_SENHA não encontradas no .env"
            )

        return usuario, senha

    async def _aguardar_aleatorio(self) -> None:
        """Aguarda tempo aleatório entre requisições."""
        delay = random.uniform(self.config.delay_min, self.config.delay_max)
        await asyncio.sleep(delay)

    def _precisa_fazer_login(self) -> bool:
        """Verifica se precisa fazer login."""
        url_atual = self._page.url.lower()

        if "login" in url_atual:
            return True

        if "subconta_listagem" in url_atual:
            return False

        return self._page.locator('button:has-text("ENTRAR")').count() > 0

    def _fazer_login(self) -> None:
        """Faz login no sistema TJ-MS."""
        usuario, senha = self._obter_credenciais()

        logger.debug("Executando login no TJ-MS...")

        # Aguarda a página de login carregar
        self._page.wait_for_selector('button:has-text("ENTRAR")', timeout=30000)
        self._page.wait_for_timeout(1000)

        # Preenche usuário
        campo_usuario = self._page.locator('input[type="text"]').first
        campo_usuario.click()
        campo_usuario.fill(usuario)

        # Preenche senha
        campo_senha = self._page.locator('input[type="password"]').first
        campo_senha.click()
        campo_senha.fill(senha)

        self._page.wait_for_timeout(500)

        # Clica em ENTRAR
        self._page.click('button:has-text("ENTRAR")')
        self._page.wait_for_load_state("load", timeout=self.config.timeout_navegacao)
        self._page.wait_for_timeout(2000)  # Aguarda redirecionamento

        # Verifica se foi para o Menu Principal
        if "subconta_listagem" not in self._page.url:
            try:
                self._page.wait_for_selector('text=Menu Principal', timeout=30000)
                self._page.get_by_role("cell", name="4. Listagem de Subcontas", exact=True).click()
                self._page.wait_for_load_state("load", timeout=self.config.timeout_navegacao)
                self._page.wait_for_timeout(1000)
            except:
                pass

        logger.debug("Login realizado com sucesso")

    def _preencher_campo_processo(self, numero_processo: str) -> None:
        """Preenche o campo Nº Processo no formulário."""
        sucesso = self._page.evaluate("""
            (numero) => {
                const fieldset = document.querySelector('fieldset');
                if (!fieldset) return false;

                const inputs = fieldset.querySelectorAll('input');
                let textInputIndex = 0;

                for (const input of inputs) {
                    const type = (input.type || 'text').toLowerCase();
                    const isText = type === 'text' || type === '';
                    const isVisible = input.offsetWidth > 0 && input.offsetHeight > 0;

                    if (isText && isVisible) {
                        textInputIndex++;
                        if (textInputIndex === 2) {
                            input.focus();
                            input.value = numero;
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                    }
                }
                return false;
            }
        """, numero_processo)

        if not sucesso:
            raise Exception("Não foi possível preencher o campo Nº Processo")

    def _extrair_texto_pdf(self, pdf_bytes: bytes) -> str:
        """Extrai texto do PDF usando PyMuPDF."""
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            texto = ""
            for page in doc:
                texto += page.get_text()
            doc.close()

            return texto.strip()
        except Exception as e:
            logger.error(f"Erro ao extrair texto do PDF: {e}")
            return ""

    def _processar_unico(self, numero_processo: str) -> ResultadoExtracao:
        """Processa um único processo."""
        try:
            numero_formatado = self._formatar_cnj(numero_processo)
            logger.debug(f"Processando subconta: {numero_formatado}")

            # Navega para listagem (usa 'load' em vez de 'networkidle' para maior tolerância)
            self._page.goto(
                self.config.listagem_url,
                wait_until="load",
                timeout=self.config.timeout_navegacao,
            )
            self._page.wait_for_timeout(1000)  # Aguarda estabilização

            # Verifica se precisa login
            if self._precisa_fazer_login():
                logger.debug("Sessão expirou, fazendo login novamente...")
                self._fazer_login()
                self._page.goto(
                    self.config.listagem_url,
                    wait_until="load",
                    timeout=self.config.timeout_navegacao,
                )
                self._page.wait_for_timeout(1000)

            # Aguarda formulário
            self._page.wait_for_selector('fieldset', timeout=30000)
            self._page.wait_for_timeout(500)

            # Preenche campo processo
            self._preencher_campo_processo(numero_formatado)

            # Submete formulário
            self._page.evaluate("""
                () => {
                    const form = document.querySelector('form');
                    if (form) form.submit();
                }
            """)

            self._page.wait_for_load_state("load", timeout=self.config.timeout_navegacao)
            self._page.wait_for_timeout(2000)  # Aguarda processamento

            # Verifica se não encontrou subconta
            sem_subconta = self._page.locator('text=Nenhuma Subconta encontrada').first.is_visible()
            if sem_subconta:
                return ResultadoExtracao(
                    numero_processo=numero_processo,
                    status=StatusProcessamento.SEM_SUBCONTA,
                    erro=self.MSG_SEM_SUBCONTA,
                )

            # Verifica se há resultados
            tem_resultados = self._page.locator('img[src*="extrato"]').count() > 0
            if not tem_resultados:
                return ResultadoExtracao(
                    numero_processo=numero_processo,
                    status=StatusProcessamento.SEM_SUBCONTA,
                    erro="Nenhuma subconta encontrada",
                )

            # Clica no ícone de extrato
            extrato_clicado = self._page.evaluate("""
                () => {
                    const imgs = document.querySelectorAll('img');
                    for (const img of imgs) {
                        const src = (img.src || '').toLowerCase();
                        if (src.includes('extrato')) {
                            const link = img.closest('a');
                            if (link) {
                                link.click();
                                return true;
                            } else {
                                img.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }
            """)

            if not extrato_clicado:
                self._page.locator('table img, td img, .acoes img').first.click()

            self._page.wait_for_load_state("load", timeout=self.config.timeout_navegacao)
            self._page.wait_for_timeout(2000)

            # Aguarda extrato carregar
            try:
                self._page.wait_for_selector('text=Extrato', timeout=30000)
            except:
                self._page.wait_for_selector('text=INFORMAÇÕES DA SUBCONTA', timeout=30000)

            # Gera PDF
            pdf_bytes = self._page.pdf(format="A4", print_background=True)

            # Extrai texto
            texto = self._extrair_texto_pdf(pdf_bytes)

            logger.debug(f"Extrato baixado com sucesso: {numero_formatado}")

            return ResultadoExtracao(
                numero_processo=numero_processo,
                status=StatusProcessamento.OK,
                pdf_bytes=pdf_bytes,
                texto_extraido=texto,
            )

        except Exception as e:
            logger.error(f"Erro ao processar {numero_processo}: {e}")
            return ResultadoExtracao(
                numero_processo=numero_processo,
                status=StatusProcessamento.ERRO,
                erro=str(e),
            )

    async def extrair_extrato(self, numero_processo: str) -> ResultadoExtracao:
        """
        Extrai o extrato de subconta de um processo.
        Método principal para uso externo.

        Args:
            numero_processo: Número CNJ do processo

        Returns:
            ResultadoExtracao com PDF bytes e texto extraído
        """
        if not self._validar_numero_processo(numero_processo):
            return ResultadoExtracao(
                numero_processo=numero_processo,
                status=StatusProcessamento.ERRO,
                erro=f"Formato de número CNJ inválido: {numero_processo}",
            )

        # Importa playwright apenas quando necessário
        from playwright.sync_api import sync_playwright

        ultima_excecao = None
        resultado = None

        # Executa em thread separada pois playwright sync não é async
        def executar_sync():
            nonlocal resultado, ultima_excecao

            with sync_playwright() as p:
                self._playwright = p
                self._browser = p.chromium.launch(headless=self.config.headless)
                self._page = self._browser.new_page()

                try:
                    # Faz login inicial (usa 'load' para maior tolerância em ambientes cloud)
                    self._page.goto(
                        self.config.listagem_url,
                        wait_until="load",
                        timeout=self.config.timeout_navegacao,
                    )
                    self._page.wait_for_timeout(1000)

                    if self._precisa_fazer_login():
                        self._fazer_login()

                    # Tenta extrair com retry
                    for tentativa in range(1, self.config.max_tentativas + 1):
                        try:
                            resultado = self._processar_unico(numero_processo)
                            if resultado.status != StatusProcessamento.ERRO:
                                break

                            ultima_excecao = resultado.erro
                            if tentativa < self.config.max_tentativas:
                                time.sleep(random.uniform(self.config.delay_min, self.config.delay_max))

                        except Exception as e:
                            ultima_excecao = str(e)
                            if tentativa < self.config.max_tentativas:
                                time.sleep(random.uniform(self.config.delay_min, self.config.delay_max))

                    if resultado is None:
                        resultado = ResultadoExtracao(
                            numero_processo=numero_processo,
                            status=StatusProcessamento.ERRO,
                            erro=f"Falhou após {self.config.max_tentativas} tentativas: {ultima_excecao}",
                        )

                finally:
                    if self._browser:
                        self._browser.close()

        # Executa em thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, executar_sync)

        return resultado


async def _tentar_endpoint_proxy(numero_processo: str) -> Optional[ResultadoExtracao]:
    """
    Tenta extrair o extrato usando o endpoint /extrair-subconta do proxy local.
    Retorna None se o proxy não estiver disponível.
    """
    import httpx
    import base64

    proxy_local = os.getenv("TJMS_PROXY_LOCAL_URL", "").strip()
    if not proxy_local:
        return None

    endpoint = f"{proxy_local.rstrip('/')}/extrair-subconta"

    try:
        logger.info(f"Tentando endpoint do proxy local: {endpoint}")
        async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0)) as client:
            response = await client.post(
                endpoint,
                json={"numero_processo": numero_processo},
            )

            if response.status_code == 200:
                data = response.json()

                # Converte base64 de volta para bytes
                pdf_bytes = None
                if data.get("pdf_base64"):
                    pdf_bytes = base64.b64decode(data["pdf_base64"])

                status = StatusProcessamento(data["status"])

                logger.info(f"Extrato obtido via endpoint proxy local: {status.value}")

                return ResultadoExtracao(
                    numero_processo=data["numero_processo"],
                    status=status,
                    pdf_bytes=pdf_bytes,
                    texto_extraido=data.get("texto_extraido"),
                    erro=data.get("erro"),
                    timestamp=data.get("timestamp", datetime.now().isoformat(timespec="seconds")),
                )
            else:
                logger.warning(f"Endpoint retornou status {response.status_code}")
                return None

    except httpx.ConnectError:
        logger.debug("Proxy local não disponível (conexão recusada)")
        return None
    except httpx.TimeoutException:
        logger.warning("Timeout ao chamar endpoint do proxy local")
        return None
    except Exception as e:
        logger.warning(f"Erro ao chamar endpoint do proxy: {type(e).__name__}: {e}")
        return None


async def extrair_extrato_subconta(numero_processo: str) -> ResultadoExtracao:
    """
    Função de conveniência para extrair extrato de subconta.

    Tenta primeiro o endpoint /extrair-subconta do proxy local (quando disponível),
    depois usa Playwright diretamente como fallback.

    Args:
        numero_processo: Número CNJ do processo

    Returns:
        ResultadoExtracao com PDF bytes e texto extraído
    """
    # Primeira tentativa: endpoint do proxy local (Playwright rodando no PC)
    resultado = await _tentar_endpoint_proxy(numero_processo)
    if resultado is not None:
        return resultado

    # Fallback: Playwright local (funciona em homologação, pode falhar em produção)
    logger.info("Usando Playwright local como fallback")
    extrator = ExtratorSubconta()
    return await extrator.extrair_extrato(numero_processo)
