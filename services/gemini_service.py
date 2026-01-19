# services/gemini_service.py
"""
Serviço centralizado para chamadas à API do Google Gemini.

Este serviço é usado por todos os sistemas do Portal PGE-MS:
- Gerador de Peças Jurídicas
- Matrículas Confrontantes
- Assistência Judiciária

OTIMIZAÇÕES DE LATÊNCIA (2026-01-16):
- HTTP Client reutilizável (connection pooling)
- Instrumentação de métricas de latência
- Retry com backoff exponencial
- Timeouts granulares (connect vs read)
- Cache hash-based para prompts idênticos
- Logging estruturado

Autor: LAB/PGE-MS
"""

import os
import asyncio
import aiohttp
import httpx
import hashlib
import logging
import time
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)


# ============================================
# INSTRUMENTAÇÃO DE MÉTRICAS
# ============================================

@dataclass
class GeminiMetrics:
    """Métricas de uma chamada ao Gemini para diagnóstico de latência"""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    model: str = ""
    prompt_chars: int = 0
    prompt_tokens_estimated: int = 0
    response_tokens: int = 0

    # Tempos em milissegundos
    time_prepare_ms: float = 0      # Tempo preparando payload
    time_connect_ms: float = 0      # Tempo conectando (TCP + TLS)
    time_ttft_ms: float = 0         # Time to First Token (ou first byte)
    time_generation_ms: float = 0   # Tempo gerando resposta
    time_total_ms: float = 0        # Tempo total

    # Status
    success: bool = True
    cached: bool = False
    retry_count: int = 0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "prompt_chars": self.prompt_chars,
            "prompt_tokens_est": self.prompt_tokens_estimated,
            "response_tokens": self.response_tokens,
            "time_prepare_ms": round(self.time_prepare_ms, 2),
            "time_connect_ms": round(self.time_connect_ms, 2),
            "time_ttft_ms": round(self.time_ttft_ms, 2),
            "time_generation_ms": round(self.time_generation_ms, 2),
            "time_total_ms": round(self.time_total_ms, 2),
            "success": self.success,
            "cached": self.cached,
            "retry_count": self.retry_count,
            "error": self.error
        }

    def log(self):
        """Log estruturado das métricas"""
        if self.success:
            logger.info(
                f"[Gemini] model={self.model} "
                f"prompt={self.prompt_chars}chars "
                f"response={self.response_tokens}tok "
                f"prepare={self.time_prepare_ms:.0f}ms "
                f"ttft={self.time_ttft_ms:.0f}ms "
                f"total={self.time_total_ms:.0f}ms "
                f"cached={self.cached}"
            )
        else:
            logger.warning(
                f"[Gemini] ERRO model={self.model} "
                f"total={self.time_total_ms:.0f}ms "
                f"retries={self.retry_count} "
                f"error={self.error[:100]}"
            )


# ============================================
# CACHE DE RESPOSTAS
# ============================================

class ResponseCache:
    """Cache LRU com TTL para respostas do Gemini"""

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._max_size = max_size
        self._ttl = timedelta(seconds=ttl_seconds)
        self._hits = 0
        self._misses = 0

    def _make_key(self, prompt: str, system_prompt: str, model: str, temperature: float) -> str:
        """Gera chave hash do prompt"""
        content = f"{model}:{temperature}:{system_prompt}:{prompt}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def get(self, prompt: str, system_prompt: str, model: str, temperature: float) -> Optional[Any]:
        """Busca no cache, retorna None se não encontrado ou expirado"""
        key = self._make_key(prompt, system_prompt, model, temperature)

        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.utcnow() - timestamp < self._ttl:
                self._hits += 1
                return value
            else:
                del self._cache[key]

        self._misses += 1
        return None

    def set(self, prompt: str, system_prompt: str, model: str, temperature: float, value: Any):
        """Armazena no cache"""
        # Evict se cheio (remove mais antigo)
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]

        key = self._make_key(prompt, system_prompt, model, temperature)
        self._cache[key] = (value, datetime.utcnow())

    def stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%"
        }


# Cache global (singleton)
_response_cache = ResponseCache(max_size=100, ttl_seconds=300)


@dataclass
class GeminiResponse:
    """Resposta padronizada do Gemini"""
    success: bool
    content: str = ""
    error: Optional[str] = None
    tokens_used: int = 0
    metrics: Optional[GeminiMetrics] = None  # Métricas de latência


# ============================================
# CONFIGURAÇÃO DE TIMEOUTS E RETRY
# ============================================

# Timeouts granulares (em segundos)
TIMEOUT_CONNECT = 10.0      # Tempo máximo para estabelecer conexão
TIMEOUT_READ = 120.0        # Tempo máximo para ler resposta
TIMEOUT_TOTAL = 180.0       # Tempo máximo total (menor que 300s original)

# Retry com backoff exponencial
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0      # Delay inicial em segundos
RETRY_MAX_DELAY = 10.0      # Delay máximo
RETRY_ERRORS = (
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ConnectError,
    aiohttp.ClientConnectorError,
    aiohttp.ServerDisconnectedError,
)

# HTTP Client singleton
_http_client: Optional[httpx.AsyncClient] = None
_http_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    """
    Retorna HTTP client singleton com connection pooling.

    PERFORMANCE: Reutiliza conexões TCP/TLS entre chamadas.
    """
    global _http_client

    if _http_client is None or _http_client.is_closed:
        async with _http_client_lock:
            # Double-check após adquirir lock
            if _http_client is None or _http_client.is_closed:
                _http_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=TIMEOUT_CONNECT,
                        read=TIMEOUT_READ,
                        write=30.0,
                        pool=10.0
                    ),
                    limits=httpx.Limits(
                        max_keepalive_connections=10,
                        max_connections=20,
                        keepalive_expiry=30.0
                    ),
                    http2=True  # HTTP/2 para multiplexação
                )
                logger.info("[Gemini] HTTP client criado com connection pooling e HTTP/2")

    return _http_client


async def close_http_client():
    """Fecha o HTTP client (para shutdown graceful)"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.info("[Gemini] HTTP client fechado")


class GeminiService:
    """
    Serviço centralizado para chamadas à API do Google Gemini.
    
    Uso:
        from services import gemini_service
        
        # Chamada simples
        response = await gemini_service.generate(prompt="Olá!")
        
        # Com imagens
        response = await gemini_service.generate_with_images(
            prompt="Descreva esta imagem",
            images_base64=[...]
        )
    """
    
    # URL base da API Gemini
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    
    # Modelos disponíveis
    MODELS = {
        # Modelos rápidos (baixo custo)
        "flash": "gemini-3-flash-preview",
        "flash-lite": "gemini-3-flash-preview",
        
        # Modelos avançados
        "pro": "gemini-2.5-pro",
        "pro-preview": "gemini-3-pro-preview",
        "flash-preview": "gemini-3-flash-preview",
    }
    
    # Modelo padrão para cada tipo de tarefa
    DEFAULT_MODELS = {
        "resumo": "gemini-3-flash-preview",      # Resumir documentos
        "analise": "gemini-3-flash-preview",           # Analisar conteúdo
        "geracao": "gemini-3-pro-preview",       # Gerar peças/relatórios
        "visao": "gemini-3-flash-preview",             # Análise de imagens
    }
    
    def __init__(self, api_key: str = None):
        """
        Inicializa o serviço.
        
        Args:
            api_key: API key do Gemini (opcional, usa GEMINI_KEY do ambiente)
        """
        self._api_key = api_key or os.getenv("GEMINI_KEY", "")
    
    @property
    def api_key(self) -> str:
        """Retorna a API key configurada"""
        return self._api_key
    
    @api_key.setter
    def api_key(self, value: str):
        """Atualiza a API key"""
        self._api_key = value
    
    def is_configured(self) -> bool:
        """Verifica se o serviço está configurado"""
        return bool(self._api_key)
    
    @staticmethod
    def normalize_model(model: str) -> str:
        """
        Normaliza o nome do modelo.
        
        - Remove prefixo 'google/' se presente
        - Converte aliases para nomes completos
        
        Exemplos:
            - google/gemini-3-pro-preview -> gemini-3-pro-preview
            - flash -> gemini-3-flash-preview
            - pro-preview -> gemini-3-pro-preview
        """
        # Remove prefixo google/
        if model.startswith("google/"):
            model = model[7:]
        
        # Converte aliases
        if model in GeminiService.MODELS:
            return GeminiService.MODELS[model]
        
        return model
    
    def get_model_for_task(self, task: str) -> str:
        """
        Retorna o modelo recomendado para uma tarefa.
        
        Args:
            task: Tipo de tarefa (resumo, analise, geracao, visao)
            
        Returns:
            Nome do modelo
        """
        return self.DEFAULT_MODELS.get(task, self.DEFAULT_MODELS["analise"])
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = None,
        task: str = None,
        max_tokens: int = None,
        temperature: float = 0.3,
        use_cache: bool = True,
        thinking_level: str = None,
        # Contexto para logging
        context: Dict[str, Any] = None
    ) -> GeminiResponse:
        """
        Gera texto usando o Gemini.

        Args:
            prompt: Prompt do usuário
            system_prompt: Instruções do sistema (opcional)
            model: Nome do modelo (opcional, usa padrão se não especificado)
            task: Tipo de tarefa para selecionar modelo automaticamente
            max_tokens: Limite de tokens na resposta (None = sem limite, usa máximo do modelo)
            temperature: Temperatura (0-2)
            use_cache: Se True, usa cache para respostas idênticas (padrão: True)
            thinking_level: Nível de raciocínio do Gemini 3 ("minimal", "low", "medium", "high")
                           None = usa padrão do modelo (high/dynamic)
                           "low" recomendado para classificação JSON (reduz latência ~80%)
            context: Dicionário com contexto para logging (sistema, modulo, user_id, username)

        Returns:
            GeminiResponse com o resultado e métricas de latência
        """
        # Contexto padrão
        ctx = context or {}
        metrics = GeminiMetrics()
        t_start = time.perf_counter()

        if not self._api_key:
            metrics.success = False
            metrics.error = "GEMINI_KEY não configurada"
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            metrics.log()
            return GeminiResponse(success=False, error=metrics.error, metrics=metrics)

        # Determina o modelo
        t_prepare = time.perf_counter()
        if model:
            model = self.normalize_model(model)
        elif task:
            model = self.get_model_for_task(task)
        else:
            model = self.DEFAULT_MODELS["analise"]

        metrics.model = model
        metrics.prompt_chars = len(prompt)
        metrics.prompt_tokens_estimated = len(prompt) // 4  # Estimativa ~4 chars/token

        # Verifica cache
        if use_cache and temperature <= 0.3:  # Só cacheia respostas determinísticas
            cached = _response_cache.get(prompt, system_prompt, model, temperature)
            if cached is not None:
                metrics.cached = True
                metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                metrics.response_tokens = cached.tokens_used
                metrics.log()
                # Log assíncrono para BD (mesmo para cache)
                asyncio.create_task(self._log_to_db(metrics, ctx, temperature=temperature))
                return GeminiResponse(
                    success=True,
                    content=cached.content,
                    tokens_used=cached.tokens_used,
                    metrics=metrics
                )

        # Monta payload
        payload = self._build_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking_level=thinking_level,
            model=model
        )
        metrics.time_prepare_ms = (time.perf_counter() - t_prepare) * 1000

        # URL da API
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"

        # Executa com retry e backoff
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                t_connect = time.perf_counter()

                # Usa HTTP client singleton com connection pooling
                client = await get_http_client()
                response = await client.post(url, json=payload)

                metrics.time_ttft_ms = (time.perf_counter() - t_connect) * 1000
                response.raise_for_status()

                t_parse = time.perf_counter()
                data = response.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                # Se conteúdo vazio e thinking_level restritivo foi usado, tenta sem
                if not content and thinking_level in ("minimal", "low"):
                    logger.warning(
                        f"[Gemini] Resposta vazia com thinking_level={thinking_level}, tentando sem"
                    )
                    # Reconstrói payload SEM thinking_level (usa default)
                    payload_retry = self._build_payload(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        thinking_level=None,  # Usa default do modelo
                        model=model
                    )
                    response_retry = await client.post(url, json=payload_retry)
                    response_retry.raise_for_status()
                    data = response_retry.json()
                    content = self._extract_content(data)
                    tokens = self._extract_tokens(data)
                    logger.info(f"[Gemini] Retry sem thinking_level: {len(content)} chars")

                # Se ainda vazio, retorna erro
                if not content:
                    metrics.success = False
                    metrics.error = "Resposta vazia do Gemini (sem conteúdo gerado)"
                    metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                    metrics.log()
                    asyncio.create_task(self._log_to_db(metrics, ctx, temperature=temperature))
                    return GeminiResponse(success=False, error=metrics.error, metrics=metrics)

                metrics.time_generation_ms = (time.perf_counter() - t_parse) * 1000
                metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                metrics.response_tokens = tokens
                metrics.retry_count = attempt
                metrics.log()

                result = GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens,
                    metrics=metrics
                )

                # Salva no cache
                if use_cache and temperature <= 0.3:
                    _response_cache.set(prompt, system_prompt, model, temperature, result)

                # Log assíncrono para BD (não bloqueia)
                asyncio.create_task(self._log_to_db(metrics, ctx, temperature=temperature))

                return result

            except RETRY_ERRORS as e:
                last_error = e
                metrics.retry_count = attempt + 1

                if attempt < MAX_RETRIES - 1:
                    delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                    logger.warning(
                        f"[Gemini] Retry {attempt + 1}/{MAX_RETRIES} após {delay:.1f}s: {type(e).__name__}"
                    )
                    await asyncio.sleep(delay)

            except httpx.HTTPStatusError as e:
                metrics.success = False
                metrics.error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                metrics.log()
                asyncio.create_task(self._log_to_db(metrics, ctx, temperature=temperature))
                return GeminiResponse(success=False, error=metrics.error, metrics=metrics)

            except Exception as e:
                metrics.success = False
                metrics.error = str(e)
                metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                metrics.log()
                asyncio.create_task(self._log_to_db(metrics, ctx, temperature=temperature))
                return GeminiResponse(success=False, error=f"Erro: {str(e)}", metrics=metrics)

        # Todas as tentativas falharam
        metrics.success = False
        metrics.error = f"Falhou após {MAX_RETRIES} tentativas: {str(last_error)}"
        metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
        metrics.log()
        asyncio.create_task(self._log_to_db(metrics, ctx, temperature=temperature))
        return GeminiResponse(success=False, error=metrics.error, metrics=metrics)
    
    async def generate_with_session(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        system_prompt: str = "",
        model: str = None,
        task: str = None,
        max_tokens: int = None,
        temperature: float = 0.3,
        thinking_level: str = None
    ) -> GeminiResponse:
        """
        Gera texto usando uma sessão aiohttp existente.

        Útil para chamadas em paralelo.

        Args:
            thinking_level: "minimal", "low", "medium", "high" ou None (default)
        """
        if not self._api_key:
            return GeminiResponse(
                success=False,
                error="GEMINI_KEY não configurada"
            )

        # Determina o modelo
        if model:
            model = self.normalize_model(model)
        elif task:
            model = self.get_model_for_task(task)
        else:
            model = self.DEFAULT_MODELS["analise"]

        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"

        # Monta payload
        payload = self._build_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking_level=thinking_level,
            model=model
        )

        try:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )

        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )

    async def generate_with_images(
        self,
        prompt: str,
        images_base64: List[str],
        system_prompt: str = "",
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.3,
        thinking_level: str = None,
        context: Dict[str, Any] = None
    ) -> GeminiResponse:
        """
        Gera texto analisando imagens.

        Args:
            prompt: Prompt do usuário
            images_base64: Lista de imagens em base64
            system_prompt: Instruções do sistema (opcional)
            model: Nome do modelo (opcional)
            max_tokens: Limite de tokens na resposta
            temperature: Temperatura (0-2)
            thinking_level: "minimal", "low", "medium", "high" ou None (default)
            context: Dicionário com contexto para logging (sistema, modulo, user_id, username)

        Returns:
            GeminiResponse com o resultado
        """
        ctx = context or {}
        metrics = GeminiMetrics()
        t_start = time.perf_counter()

        if not self._api_key:
            metrics.success = False
            metrics.error = "GEMINI_KEY não configurada"
            return GeminiResponse(success=False, error=metrics.error, metrics=metrics)

        # Modelo padrão para visão
        if model:
            model = self.normalize_model(model)
        else:
            model = self.DEFAULT_MODELS["visao"]

        metrics.model = model
        metrics.prompt_chars = len(prompt)

        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"

        # Monta payload com imagens
        payload = self._build_payload_with_images(
            prompt=prompt,
            images_base64=images_base64,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking_level=thinking_level,
            model=model
        )

        # Retry com backoff
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                t_connect = time.perf_counter()

                # Usa HTTP client singleton
                client = await get_http_client()
                response = await client.post(url, json=payload)

                metrics.time_ttft_ms = (time.perf_counter() - t_connect) * 1000
                response.raise_for_status()
                data = response.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                # Se conteúdo vazio e thinking_level restritivo foi usado, tenta sem
                if not content and thinking_level in ("minimal", "low"):
                    logger.warning(
                        f"[Gemini] Resposta vazia com thinking_level={thinking_level} (imagens), tentando sem"
                    )
                    payload_retry = self._build_payload_with_images(
                        prompt=prompt,
                        images_base64=images_base64,
                        system_prompt=system_prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        thinking_level=None,  # Usa default do modelo
                        model=model
                    )
                    response_retry = await client.post(url, json=payload_retry)
                    response_retry.raise_for_status()
                    data = response_retry.json()
                    content = self._extract_content(data)
                    tokens = self._extract_tokens(data)
                    logger.info(f"[Gemini] Retry sem thinking_level: {len(content)} chars")

                # Se ainda vazio, retorna erro
                if not content:
                    metrics.success = False
                    metrics.error = "Resposta vazia do Gemini (sem conteúdo gerado)"
                    metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                    asyncio.create_task(self._log_to_db(metrics, ctx, has_images=True, temperature=temperature))
                    return GeminiResponse(success=False, error=metrics.error, metrics=metrics)

                metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                metrics.response_tokens = tokens
                metrics.log()

                # Log assíncrono para BD
                asyncio.create_task(self._log_to_db(metrics, ctx, has_images=True, temperature=temperature))

                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens,
                    metrics=metrics
                )

            except RETRY_ERRORS as e:
                last_error = e
                metrics.retry_count = attempt + 1
                if attempt < MAX_RETRIES - 1:
                    delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                    await asyncio.sleep(delay)

            except httpx.HTTPStatusError as e:
                metrics.success = False
                metrics.error = f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}"
                metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                asyncio.create_task(self._log_to_db(metrics, ctx, has_images=True, temperature=temperature))
                return GeminiResponse(success=False, error=metrics.error, metrics=metrics)

            except Exception as e:
                metrics.success = False
                metrics.error = str(e)
                metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                asyncio.create_task(self._log_to_db(metrics, ctx, has_images=True, temperature=temperature))
                return GeminiResponse(success=False, error=f"Erro: {str(e)}", metrics=metrics)

        # Todas as tentativas falharam
        metrics.success = False
        metrics.error = f"Falhou após {MAX_RETRIES} tentativas: {str(last_error)}"
        metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
        asyncio.create_task(self._log_to_db(metrics, ctx, has_images=True, temperature=temperature))
        return GeminiResponse(success=False, error=metrics.error, metrics=metrics)

    async def generate_with_images_session(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        images_base64: List[str],
        system_prompt: str = "",
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.3
    ) -> GeminiResponse:
        """
        Gera texto analisando imagens usando sessão aiohttp.
        """
        if not self._api_key:
            return GeminiResponse(
                success=False, 
                error="GEMINI_KEY não configurada"
            )
        
        # Modelo padrão para visão
        if model:
            model = self.normalize_model(model)
        else:
            model = self.DEFAULT_MODELS["visao"]
        
        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"
        
        # Monta payload com imagens
        payload = self._build_payload_with_images(
            prompt=prompt,
            images_base64=images_base64,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            model=model
        )

        try:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )

        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )

    def _build_payload(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = None,
        temperature: float = 0.3,
        thinking_level: str = None,
        model: str = None
    ) -> Dict[str, Any]:
        """
        Monta o payload para chamada de texto.

        Args:
            thinking_level: Nível de raciocínio do Gemini 3. Valores válidos:
                - None: Usa padrão do modelo (high/dynamic)
                - "minimal": Quase sem thinking (melhor para chat/alta vazão) - só Flash
                - "low": Mínimo thinking (bom para classificação simples)
                - "medium": Balanceado - só Flash
                - "high": Máximo raciocínio (padrão)
            model: Nome do modelo (usado para validar thinking_level)
        """
        generation_config = {"temperature": temperature}

        # Só adiciona maxOutputTokens se especificado (None = usa máximo do modelo)
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        # Configura nível de thinking para Gemini 3
        # - Gemini 3 Flash: suporta "minimal", "low", "medium", "high"
        # - Gemini 3 Pro: suporta apenas "low", "high"
        # - Gemini 2.x: não suporta thinkingConfig
        if thinking_level and model:
            model_lower = model.lower()
            if "gemini-3" in model_lower:
                if "flash" in model_lower:
                    # Flash aceita todos os níveis
                    valid_levels = ("minimal", "low", "medium", "high")
                else:
                    # Pro aceita apenas low e high
                    valid_levels = ("low", "high")

                if thinking_level in valid_levels:
                    generation_config["thinkingConfig"] = {
                        "thinkingLevel": thinking_level
                    }
                # Se nível inválido para o modelo, simplesmente ignora (usa default)

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": generation_config
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        return payload
    
    def _build_payload_with_images(
        self,
        prompt: str,
        images_base64: List[str],
        system_prompt: str = "",
        max_tokens: int = None,
        temperature: float = 0.3,
        thinking_level: str = None,
        model: str = None
    ) -> Dict[str, Any]:
        """
        Monta o payload para chamada com imagens.

        Args:
            thinking_level: Nível de raciocínio do Gemini 3. Valores válidos:
                - None: Usa padrão do modelo (high/dynamic)
                - "minimal": Quase sem thinking (melhor para chat/alta vazão) - só Flash
                - "low": Mínimo thinking (bom para classificação simples)
                - "medium": Balanceado - só Flash
                - "high": Máximo raciocínio (padrão)
            model: Nome do modelo (usado para validar thinking_level)
        """
        parts = []

        # Adiciona imagens
        for img_base64 in images_base64:
            if img_base64.startswith("data:"):
                # Formato: data:image/png;base64,<dados>
                header, data = img_base64.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
            else:
                mime_type = "image/png"
                data = img_base64

            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": data
                }
            })

        # Adiciona prompt
        parts.append({"text": prompt})

        generation_config = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        # Configura nível de thinking para Gemini 3
        # - Gemini 3 Flash: suporta "minimal", "low", "medium", "high"
        # - Gemini 3 Pro: suporta apenas "low", "high"
        # - Gemini 2.x: não suporta thinkingConfig
        if thinking_level and model:
            model_lower = model.lower()
            if "gemini-3" in model_lower:
                if "flash" in model_lower:
                    # Flash aceita todos os níveis
                    valid_levels = ("minimal", "low", "medium", "high")
                else:
                    # Pro aceita apenas low e high
                    valid_levels = ("low", "high")

                if thinking_level in valid_levels:
                    generation_config["thinkingConfig"] = {
                        "thinkingLevel": thinking_level
                    }
                # Se nível inválido para o modelo, simplesmente ignora (usa default)

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        return payload
    
    async def generate_with_search(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.3,
        search_threshold: float = 0.3
    ) -> GeminiResponse:
        """
        Gera texto com Google Search Grounding habilitado.

        Permite que o modelo busque informações na internet quando necessário.
        Útil para verificar informações factuais como medicamentos, leis, etc.

        Args:
            prompt: Prompt do usuário
            system_prompt: Instruções do sistema (opcional)
            model: Nome do modelo (opcional)
            max_tokens: Limite de tokens na resposta
            temperature: Temperatura (0-2)
            search_threshold: Limiar para ativar busca (0-1, menor = mais buscas)

        Returns:
            GeminiResponse com o resultado
        """
        if not self._api_key:
            return GeminiResponse(
                success=False,
                error="GEMINI_KEY não configurada"
            )

        # Determina o modelo
        if model:
            model = self.normalize_model(model)
        else:
            model = self.DEFAULT_MODELS["analise"]

        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"

        # Monta payload base
        generation_config = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": prompt}]}
            ],
            "generationConfig": generation_config,
            "tools": [
                {
                    "google_search": {}
                }
            ]
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                # Extrai informações de grounding se disponíveis
                grounding_metadata = self._extract_grounding_metadata(data)
                if grounding_metadata:
                    content += f"\n\n---\n**Fontes consultadas:** {grounding_metadata}"

                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )

        except httpx.HTTPStatusError as e:
            return GeminiResponse(
                success=False,
                error=f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )

    async def generate_with_images_and_search(
        self,
        prompt: str,
        images_base64: List[str],
        system_prompt: str = "",
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.3,
        search_threshold: float = 0.3
    ) -> GeminiResponse:
        """
        Gera texto analisando imagens COM Google Search Grounding.

        Combina análise de imagens com busca na internet.
        Ideal para verificar informações em notas fiscais, medicamentos, etc.
        """
        if not self._api_key:
            return GeminiResponse(
                success=False,
                error="GEMINI_KEY não configurada"
            )

        # Modelo padrão para visão
        if model:
            model = self.normalize_model(model)
        else:
            model = self.DEFAULT_MODELS["visao"]

        # Monta URL
        url = f"{self.BASE_URL}/{model}:generateContent?key={self._api_key}"

        # Monta partes com imagens
        parts = []
        for img_base64 in images_base64:
            if img_base64.startswith("data:"):
                header, data = img_base64.split(",", 1)
                mime_type = header.split(":")[1].split(";")[0]
            else:
                mime_type = "image/png"
                data = img_base64

            parts.append({
                "inline_data": {
                    "mime_type": mime_type,
                    "data": data
                }
            })

        parts.append({"text": prompt})

        generation_config = {"temperature": temperature}
        if max_tokens is not None:
            generation_config["maxOutputTokens"] = max_tokens

        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
            "tools": [
                {
                    "google_search": {}
                }
            ]
        }

        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens
                )

        except httpx.HTTPStatusError as e:
            return GeminiResponse(
                success=False,
                error=f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}"
            )
        except Exception as e:
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}"
            )

    def _extract_content(self, data: Dict) -> str:
        """Extrai conteúdo da resposta do Gemini"""
        candidates = data.get("candidates", [])
        if candidates:
            # Verifica se há bloqueio
            finish_reason = candidates[0].get("finishReason", "")
            if finish_reason in ("SAFETY", "RECITATION", "OTHER"):
                logger.warning(f"[Gemini] Resposta bloqueada: finishReason={finish_reason}")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                # Gemini 2.5 com thinking pode ter múltiplas parts
                # A primeira pode ser "thought" e a segunda o texto real
                for part in parts:
                    text = part.get("text", "")
                    if text:
                        return text
        else:
            # Log para diagnóstico de respostas vazias
            prompt_feedback = data.get("promptFeedback", {})
            if prompt_feedback:
                block_reason = prompt_feedback.get("blockReason", "")
                if block_reason:
                    logger.warning(f"[Gemini] Prompt bloqueado: blockReason={block_reason}")
            else:
                logger.warning(f"[Gemini] Resposta sem candidates. Keys: {list(data.keys())}")
        return ""

    def _extract_tokens(self, data: Dict) -> int:
        """Extrai contagem de tokens da resposta"""
        usage = data.get("usageMetadata", {})
        return usage.get("totalTokenCount", 0)

    def _extract_grounding_metadata(self, data: Dict) -> str:
        """Extrai metadados de grounding (fontes consultadas)"""
        candidates = data.get("candidates", [])
        if not candidates:
            return ""

        grounding = candidates[0].get("groundingMetadata", {})
        if not grounding:
            return ""

        # Extrai URLs das fontes
        sources = grounding.get("webSearchQueries", [])
        chunks = grounding.get("groundingChunks", [])

        urls = []
        for chunk in chunks:
            web = chunk.get("web", {})
            if web.get("uri"):
                urls.append(web.get("uri"))

        if urls:
            return ", ".join(urls[:3])  # Máximo 3 URLs
        elif sources:
            return f"Buscas: {', '.join(sources[:3])}"

        return ""

    async def _log_to_db(
        self,
        metrics: GeminiMetrics,
        context: Dict[str, Any],
        has_images: bool = False,
        has_search: bool = False,
        temperature: float = None
    ):
        """
        Registra a chamada no banco de dados de forma assíncrona.

        IMPORTANTE: Se o contexto não for passado explicitamente ou estiver incompleto,
        tenta obter automaticamente do ia_context (middleware HTTP).

        Args:
            metrics: Métricas da chamada
            context: Dicionário com sistema, modulo, user_id, username
            has_images: Se a chamada incluiu imagens
            has_search: Se usou Google Search Grounding
            temperature: Temperatura usada
        """
        try:
            from admin.services_gemini_logs import log_gemini_call_async

            # Se não temos sistema ou está como unknown, tenta obter do ia_context
            sistema = context.get('sistema')
            if not sistema or sistema == 'unknown':
                try:
                    from admin.ia_context import ia_ctx
                    auto_context = ia_ctx.get_context()
                    # Mescla contexto automático com o passado (passado tem prioridade se não for unknown)
                    if auto_context.get('sistema') and auto_context['sistema'] != 'unknown':
                        sistema = auto_context['sistema']
                    if not context.get('modulo') and auto_context.get('modulo'):
                        context['modulo'] = auto_context['modulo']
                    if not context.get('user_id') and auto_context.get('user_id'):
                        context['user_id'] = auto_context['user_id']
                    if not context.get('username') and auto_context.get('username'):
                        context['username'] = auto_context['username']
                    if not context.get('request_id') and auto_context.get('request_id'):
                        context['request_id'] = auto_context['request_id']
                    if not context.get('route') and auto_context.get('route'):
                        context['route'] = auto_context['route']
                except Exception as ctx_err:
                    logger.debug(f"[Gemini] Não foi possível obter ia_context: {ctx_err}")

            await log_gemini_call_async(
                metrics=metrics,
                sistema=sistema or 'unknown',
                modulo=context.get('modulo'),
                user_id=context.get('user_id'),
                username=context.get('username'),
                has_images=has_images,
                has_search=has_search,
                temperature=temperature,
                request_id=context.get('request_id'),
                route=context.get('route')
            )
        except Exception as e:
            # Não falha a chamada principal por erro de logging
            logger.warning(f"[Gemini] Falha ao logar chamada no BD: {e}")


# Instância global do serviço (singleton)
gemini_service = GeminiService()


# ============================================
# Funções de conveniência (compatibilidade)
# ============================================

async def chamar_gemini(
    prompt: str,
    system_prompt: str = "",
    modelo: str = None,
    max_tokens: int = None,
    temperature: float = 0.3
) -> str:
    """
    Função de conveniência para chamadas simples.
    
    Retorna apenas o texto (para compatibilidade).
    """
    response = await gemini_service.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        model=modelo,
        max_tokens=max_tokens,
        temperature=temperature
    )
    
    if not response.success:
        raise ValueError(response.error)
    
    return response.content


async def chamar_gemini_com_imagens(
    prompt: str,
    imagens_base64: List[str],
    system_prompt: str = "",
    modelo: str = None,
    max_tokens: int = None,
    temperature: float = 0.3
) -> str:
    """
    Função de conveniência para chamadas com imagens.

    Retorna apenas o texto (para compatibilidade).
    """
    response = await gemini_service.generate_with_images(
        prompt=prompt,
        images_base64=imagens_base64,
        system_prompt=system_prompt,
        model=modelo,
        max_tokens=max_tokens,
        temperature=temperature
    )

    if not response.success:
        raise ValueError(response.error)

    return response.content


# ============================================
# FUNÇÕES DE DIAGNÓSTICO E MONITORAMENTO
# ============================================

def get_cache_stats() -> Dict[str, Any]:
    """Retorna estatísticas do cache de respostas"""
    return _response_cache.stats()


def clear_cache():
    """Limpa o cache de respostas"""
    global _response_cache
    _response_cache = ResponseCache(max_size=100, ttl_seconds=300)
    logger.info("[Gemini] Cache limpo")


async def get_service_status() -> Dict[str, Any]:
    """
    Retorna status do serviço Gemini para diagnóstico.

    Útil para endpoints de health check e monitoramento.
    """
    global _http_client

    return {
        "configured": gemini_service.is_configured(),
        "http_client_active": _http_client is not None and not _http_client.is_closed,
        "cache": _response_cache.stats(),
        "config": {
            "timeout_connect": TIMEOUT_CONNECT,
            "timeout_read": TIMEOUT_READ,
            "max_retries": MAX_RETRIES,
            "default_model": gemini_service.DEFAULT_MODELS["analise"],
        }
    }


# ============================================
# FUNÇÕES DE CONFIGURAÇÃO DINÂMICA
# ============================================

def get_thinking_level(db, sistema: str) -> str:
    """
    Obtém o thinking_level configurado para um sistema.

    Args:
        db: Sessão do SQLAlchemy
        sistema: Nome do sistema (gerador_pecas, assistencia_judiciaria, etc.)

    Returns:
        Nível de thinking ("minimal", "low", "medium", "high") ou None para default

    Exemplo:
        thinking_level = get_thinking_level(db, "gerador_pecas")
        response = await gemini_service.generate(prompt, thinking_level=thinking_level)
    """
    try:
        from admin.models import ConfiguracaoIA

        config = db.query(ConfiguracaoIA).filter(
            ConfiguracaoIA.sistema == sistema,
            ConfiguracaoIA.chave == "thinking_level"
        ).first()

        if config and config.valor and config.valor.strip():
            valor = config.valor.strip().lower()
            if valor in ("minimal", "low", "medium", "high"):
                return valor

        return None  # Usa default do modelo

    except Exception as e:
        logger.warning(f"[Gemini] Erro ao ler thinking_level para {sistema}: {e}")
        return None


# Exports para outros módulos
__all__ = [
    # Classes
    "GeminiService",
    "GeminiResponse",
    "GeminiMetrics",
    "ResponseCache",
    # Singleton
    "gemini_service",
    # Funções de conveniência
    "chamar_gemini",
    "chamar_gemini_com_imagens",
    # HTTP Client
    "get_http_client",
    "close_http_client",
    # Diagnóstico
    "get_cache_stats",
    "clear_cache",
    "get_service_status",
]