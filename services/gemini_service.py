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
from typing import List, Optional, Dict, Any, Tuple, AsyncGenerator
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

# Import condicional para evitar ciclo (IAParams é usado como type hint)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from services.ia_params_resolver import IAParams

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

    # Auditoria de parâmetros por agente (novo)
    sistema: str = ""               # Sistema que fez a chamada
    agente: str = ""                # Agente específico
    temperatura: float = 0.0        # Temperatura usada
    max_tokens: Optional[int] = None  # Max tokens usado
    thinking_level: Optional[str] = None  # Thinking level usado

    # Fontes dos parâmetros (para auditoria)
    modelo_source: str = ""         # "agent", "system", "global", "default"
    temperatura_source: str = ""
    max_tokens_source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {
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
        # Adiciona campos de auditoria se preenchidos
        if self.sistema:
            result["sistema"] = self.sistema
        if self.agente:
            result["agente"] = self.agente
        if self.modelo_source:
            result["sources"] = {
                "modelo": self.modelo_source,
                "temperatura": self.temperatura_source,
                "max_tokens": self.max_tokens_source,
            }
        return result

    def log(self):
        """Log estruturado das métricas"""
        # Monta sufixo de auditoria se disponível
        audit_suffix = ""
        if self.sistema and self.agente:
            sources_short = ""
            if self.modelo_source:
                sources_short = f" sources={{modelo:{self.modelo_source[:3]}, temp:{self.temperatura_source[:3]}, tokens:{self.max_tokens_source[:3]}}}"
            audit_suffix = f" sistema={self.sistema} agente={self.agente}{sources_short}"

        if self.success:
            logger.info(
                f"[Gemini] model={self.model} "
                f"prompt={self.prompt_chars}chars "
                f"response={self.response_tokens}tok "
                f"prepare={self.time_prepare_ms:.0f}ms "
                f"ttft={self.time_ttft_ms:.0f}ms "
                f"total={self.time_total_ms:.0f}ms "
                f"cached={self.cached}{audit_suffix}"
            )
        else:
            logger.warning(
                f"[Gemini] ERRO model={self.model} "
                f"total={self.time_total_ms:.0f}ms "
                f"retries={self.retry_count} "
                f"error={self.error[:100]}{audit_suffix}"
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
# NOTA: Aumentados para suportar prompts grandes em processos complexos
TIMEOUT_CONNECT = 15.0      # Tempo máximo para estabelecer conexão
TIMEOUT_READ = 180.0        # Tempo máximo para ler resposta (aumentado de 120s para 180s)
TIMEOUT_TOTAL = 240.0       # Tempo máximo total (aumentado para suportar prompts grandes)

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

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = None,
        task: str = None,
        max_tokens: int = None,
        temperature: float = 0.3,
        thinking_level: str = None,
        context: Dict[str, Any] = None
    ) -> AsyncGenerator[str, None]:
        """
        Gera texto usando streaming real do Gemini (streamGenerateContent).

        PERFORMANCE: Reduz TTFT (Time To First Token) de 15-60s para 1-3s
        permitindo que o frontend mostre tokens assim que chegam.

        Args:
            prompt: Prompt do usuário
            system_prompt: Instruções do sistema (opcional)
            model: Nome do modelo (opcional)
            task: Tipo de tarefa para selecionar modelo automaticamente
            max_tokens: Limite de tokens na resposta
            temperature: Temperatura (0-2)
            thinking_level: Nível de raciocínio ("minimal", "low", "medium", "high")
            context: Dicionário com contexto para logging

        Yields:
            Chunks de texto conforme são gerados pelo modelo

        Exemplo:
            async for chunk in gemini_service.generate_stream(prompt="Olá!"):
                yield f"data: {json.dumps({'chunk': chunk})}\\n\\n"
        """
        ctx = context or {}
        metrics = GeminiMetrics()
        t_start = time.perf_counter()
        first_chunk_received = False

        if not self._api_key:
            metrics.success = False
            metrics.error = "GEMINI_KEY não configurada"
            logger.error("[Gemini Stream] API key não configurada")
            return

        # Determina o modelo
        if model:
            model = self.normalize_model(model)
        elif task:
            model = self.get_model_for_task(task)
        else:
            model = self.DEFAULT_MODELS["analise"]

        metrics.model = model
        metrics.prompt_chars = len(prompt)
        metrics.prompt_tokens_estimated = len(prompt) // 4

        # Monta payload
        payload = self._build_payload(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking_level=thinking_level,
            model=model
        )

        # URL da API com streaming
        url = f"{self.BASE_URL}/{model}:streamGenerateContent?alt=sse&key={self._api_key}"

        total_content = ""
        total_tokens = 0

        try:
            t_connect = time.perf_counter()

            # Usa httpx para streaming
            client = await get_http_client()

            async with client.stream("POST", url, json=payload, timeout=TIMEOUT_TOTAL) as response:
                metrics.time_connect_ms = (time.perf_counter() - t_connect) * 1000

                if response.status_code != 200:
                    error_text = await response.aread()
                    metrics.success = False
                    metrics.error = f"HTTP {response.status_code}: {error_text.decode()[:200]}"
                    metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                    metrics.log()
                    logger.error(f"[Gemini Stream] Erro: {metrics.error}")
                    return

                # Processa eventos SSE
                buffer = ""
                async for raw_chunk in response.aiter_bytes():
                    buffer += raw_chunk.decode("utf-8")

                    # Processa linhas completas
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()

                        if not line:
                            continue

                        # Formato SSE: "data: {...json...}"
                        if line.startswith("data: "):
                            json_str = line[6:]  # Remove "data: "

                            try:
                                data = __import__("json").loads(json_str)

                                # Extrai texto do chunk
                                candidates = data.get("candidates", [])
                                if candidates:
                                    content_obj = candidates[0].get("content", {})
                                    parts = content_obj.get("parts", [])
                                    for part in parts:
                                        text = part.get("text", "")
                                        if text:
                                            # TTFT - primeiro chunk
                                            if not first_chunk_received:
                                                first_chunk_received = True
                                                metrics.time_ttft_ms = (time.perf_counter() - t_start) * 1000
                                                logger.info(
                                                    f"[Gemini Stream] TTFT: {metrics.time_ttft_ms:.0f}ms "
                                                    f"model={model}"
                                                )

                                            total_content += text
                                            yield text

                                # Extrai tokens se disponível
                                usage = data.get("usageMetadata", {})
                                if usage:
                                    total_tokens = usage.get("totalTokenCount", total_tokens)

                            except __import__("json").JSONDecodeError:
                                # Linha não é JSON válido, ignora
                                continue

            # Finaliza métricas
            metrics.success = True
            metrics.response_tokens = total_tokens or len(total_content) // 4
            metrics.time_generation_ms = (time.perf_counter() - t_start) * 1000 - metrics.time_ttft_ms
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            metrics.log()

            # Log assíncrono
            asyncio.create_task(self._log_to_db(metrics, ctx, temperature=temperature))

        except Exception as e:
            metrics.success = False
            metrics.error = str(e)
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            metrics.log()
            logger.error(f"[Gemini Stream] Erro: {e}")
            asyncio.create_task(self._log_to_db(metrics, ctx, temperature=temperature))

    async def generate_with_sla(
        self,
        prompt: str,
        system_prompt: str = "",
        model_primary: str = "gemini-3-flash-preview",
        model_fallback: str = "gemini-2.0-flash-lite",
        sla_timeout_seconds: float = 5.0,
        max_tokens: int = None,
        temperature: float = 0.3,
        thinking_level: str = None,
        context: Dict[str, Any] = None
    ) -> GeminiResponse:
        """
        Gera texto com fallback automático baseado em SLA.

        Se o modelo primário não responder dentro do timeout SLA,
        automaticamente faz fallback para um modelo mais rápido.

        Args:
            prompt: Prompt do usuário
            system_prompt: Instruções do sistema
            model_primary: Modelo preferido (mais capaz, pode ser lento)
            model_fallback: Modelo de fallback (mais rápido, menos capaz)
            sla_timeout_seconds: Timeout em segundos para TTFT do modelo primário
            max_tokens: Limite de tokens na resposta
            temperature: Temperatura (0-2)
            thinking_level: Nível de raciocínio
            context: Contexto para logging

        Returns:
            GeminiResponse com indicação de qual modelo foi usado

        Exemplo:
            # Tenta gemini-3-flash-preview, fallback para lite se > 5s
            response = await gemini_service.generate_with_sla(
                prompt=prompt,
                sla_timeout_seconds=5.0
            )
        """
        ctx = context or {}
        metrics = GeminiMetrics()
        t_start = time.perf_counter()

        if not self._api_key:
            return GeminiResponse(
                success=False,
                error="GEMINI_KEY não configurada"
            )

        model_primary = self.normalize_model(model_primary)
        model_fallback = self.normalize_model(model_fallback)

        metrics.model = model_primary
        metrics.prompt_chars = len(prompt)

        # Tenta modelo primário com timeout
        try:
            # Cria task para o modelo primário
            primary_task = asyncio.create_task(
                self.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=model_primary,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    thinking_level=thinking_level,
                    use_cache=True,
                    context=ctx
                )
            )

            # Aguarda com timeout
            response = await asyncio.wait_for(primary_task, timeout=sla_timeout_seconds)

            # Modelo primário respondeu dentro do SLA
            if response.success:
                logger.info(
                    f"[Gemini SLA] Primário OK: {model_primary} "
                    f"em {response.metrics.time_total_ms:.0f}ms (SLA: {sla_timeout_seconds}s)"
                )
                return response
            else:
                # Erro no primário, tenta fallback
                logger.warning(
                    f"[Gemini SLA] Primário falhou ({response.error}), tentando fallback"
                )

        except asyncio.TimeoutError:
            # Timeout no primário - cancela e usa fallback
            primary_task.cancel()
            try:
                await primary_task
            except asyncio.CancelledError:
                pass

            logger.warning(
                f"[Gemini SLA] Timeout no primário ({model_primary}) "
                f"após {sla_timeout_seconds}s, usando fallback: {model_fallback}"
            )

        except Exception as e:
            logger.warning(
                f"[Gemini SLA] Erro no primário ({e}), tentando fallback"
            )

        # Fallback para modelo mais rápido
        try:
            response = await self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model_fallback,
                max_tokens=max_tokens,
                temperature=temperature,
                thinking_level=None,  # Fallback não usa thinking avançado
                use_cache=True,
                context=ctx
            )

            if response.success:
                logger.info(
                    f"[Gemini SLA] Fallback OK: {model_fallback} "
                    f"em {response.metrics.time_total_ms:.0f}ms"
                )
                # Marca nas métricas que usou fallback
                if response.metrics:
                    response.metrics.error = f"fallback_from:{model_primary}"

            return response

        except Exception as e:
            metrics.success = False
            metrics.error = f"Fallback também falhou: {str(e)}"
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            metrics.log()
            return GeminiResponse(
                success=False,
                error=metrics.error,
                metrics=metrics
            )

    async def generate_with_params(
        self,
        prompt: str,
        ia_params: "IAParams",
        system_prompt: str = "",
        use_cache: bool = True
    ) -> GeminiResponse:
        """
        Gera texto usando parâmetros resolvidos do IAParams.

        Esta é a forma preferida de chamar o Gemini quando se utiliza
        o sistema de resolução de parâmetros por agente.

        Args:
            prompt: Prompt do usuário
            ia_params: Parâmetros resolvidos (de get_ia_params())
            system_prompt: Instruções do sistema (opcional)
            use_cache: Se True, usa cache para respostas idênticas (padrão: True)

        Returns:
            GeminiResponse com o resultado e métricas de latência incluindo
            informações de auditoria (sistema, agente, fontes dos parâmetros)

        Exemplo:
            from services.ia_params_resolver import get_ia_params

            params = get_ia_params(db, "gerador_pecas", "geracao")
            response = await gemini_service.generate_with_params(
                prompt=prompt,
                ia_params=params,
                system_prompt=system_prompt
            )
        """
        # Monta contexto de auditoria
        context = {
            "sistema": ia_params.sistema,
            "modulo": ia_params.agente,
        }

        # Chama generate() com os parâmetros resolvidos
        response = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            model=ia_params.modelo,
            max_tokens=ia_params.max_tokens,
            temperature=ia_params.temperatura,
            thinking_level=ia_params.thinking_level,
            use_cache=use_cache,
            context=context
        )

        # Enriquece métricas com informações de auditoria
        if response.metrics:
            response.metrics.sistema = ia_params.sistema
            response.metrics.agente = ia_params.agente
            response.metrics.temperatura = ia_params.temperatura
            response.metrics.max_tokens = ia_params.max_tokens
            response.metrics.thinking_level = ia_params.thinking_level
            response.metrics.modelo_source = ia_params.modelo_source
            response.metrics.temperatura_source = ia_params.temperatura_source
            response.metrics.max_tokens_source = ia_params.max_tokens_source

            # Log estruturado com auditoria (já chamado em generate(), mas refaz com auditoria)
            logger.info(
                f"[IA] sistema={ia_params.sistema} agente={ia_params.agente} "
                f"modelo={ia_params.modelo} temp={ia_params.temperatura} "
                f"max_tokens={ia_params.max_tokens or 'auto'} "
                f"sources={{modelo:{ia_params.modelo_source}, temp:{ia_params.temperatura_source}, "
                f"tokens:{ia_params.max_tokens_source}}} "
                f"latency={response.metrics.time_total_ms:.0f}ms "
                f"tokens={response.metrics.response_tokens}"
            )

        return response

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
        temperature: float = 0.3,
        thinking_level: str = None
    ) -> GeminiResponse:
        """
        Gera texto analisando imagens usando sessão aiohttp.

        Args:
            thinking_level: "minimal", "low", "medium", "high" ou None (default)
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
        search_threshold: float = 0.3,
        context: Dict[str, Any] = None
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
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            return GeminiResponse(
                success=False,
                error="GEMINI_KEY não configurada",
                metrics=metrics
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

        # Métricas
        metrics.model = model
        metrics.prompt_chars = len(prompt)
        metrics.prompt_tokens_estimated = len(prompt) // 4

        t_request_start = time.perf_counter()
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                t_connect_start = time.perf_counter()
                response = await client.post(url, json=payload)
                metrics.time_connect_ms = (time.perf_counter() - t_connect_start) * 1000
                
                response.raise_for_status()
                data = response.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                # Extrai informações de grounding se disponíveis
                grounding_metadata = self._extract_grounding_metadata(data)
                if grounding_metadata:
                    content += f"\n\n---\n**Fontes consultadas:** {grounding_metadata}"

                metrics.success = True
                metrics.response_tokens = tokens
                metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                metrics.log()
                
                # Loga no banco de dados
                asyncio.create_task(self._log_to_db(metrics, ctx, has_search=True, temperature=temperature))

                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens,
                    metrics=metrics
                )

        except httpx.HTTPStatusError as e:
            metrics.success = False
            metrics.error = f"HTTP {e.response.status_code}"
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            metrics.log()
            asyncio.create_task(self._log_to_db(metrics, ctx, has_search=True, temperature=temperature))
            return GeminiResponse(
                success=False,
                error=f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}",
                metrics=metrics
            )
        except Exception as e:
            metrics.success = False
            metrics.error = str(e)[:100]
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            metrics.log()
            asyncio.create_task(self._log_to_db(metrics, ctx, has_search=True, temperature=temperature))
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}",
                metrics=metrics
            )

    async def generate_with_images_and_search(
        self,
        prompt: str,
        images_base64: List[str],
        system_prompt: str = "",
        model: str = None,
        max_tokens: int = None,
        temperature: float = 0.3,
        search_threshold: float = 0.3,
        context: Dict[str, Any] = None
    ) -> GeminiResponse:
        """
        Gera texto analisando imagens COM Google Search Grounding.

        Combina análise de imagens com busca na internet.
        Ideal para verificar informações em notas fiscais, medicamentos, etc.
        """
        ctx = context or {}
        metrics = GeminiMetrics()
        t_start = time.perf_counter()

        if not self._api_key:
            metrics.success = False
            metrics.error = "GEMINI_KEY não configurada"
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            return GeminiResponse(
                success=False,
                error="GEMINI_KEY não configurada",
                metrics=metrics
            )

        # Modelo padrão para visão
        if model:
            model = self.normalize_model(model)
        else:
            model = self.DEFAULT_MODELS["visao"]

        metrics.model = model
        metrics.prompt_chars = len(prompt)
        metrics.prompt_tokens_estimated = len(prompt) // 4

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
                t_connect_start = time.perf_counter()
                response = await client.post(url, json=payload)
                metrics.time_connect_ms = (time.perf_counter() - t_connect_start) * 1000

                response.raise_for_status()
                data = response.json()

                content = self._extract_content(data)
                tokens = self._extract_tokens(data)

                metrics.success = True
                metrics.response_tokens = tokens
                metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
                metrics.log()

                # Loga no banco de dados
                asyncio.create_task(self._log_to_db(metrics, ctx, has_images=True, has_search=True, temperature=temperature))

                return GeminiResponse(
                    success=True,
                    content=content,
                    tokens_used=tokens,
                    metrics=metrics
                )

        except httpx.HTTPStatusError as e:
            metrics.success = False
            metrics.error = f"HTTP {e.response.status_code}"
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            metrics.log()
            asyncio.create_task(self._log_to_db(metrics, ctx, has_images=True, has_search=True, temperature=temperature))
            return GeminiResponse(
                success=False,
                error=f"Erro HTTP {e.response.status_code}: {e.response.text[:200]}",
                metrics=metrics
            )
        except Exception as e:
            metrics.success = False
            metrics.error = str(e)[:100]
            metrics.time_total_ms = (time.perf_counter() - t_start) * 1000
            metrics.log()
            asyncio.create_task(self._log_to_db(metrics, ctx, has_images=True, has_search=True, temperature=temperature))
            return GeminiResponse(
                success=False,
                error=f"Erro: {str(e)}",
                metrics=metrics
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


# ============================================
# TRUNCAMENTO INTELIGENTE DE PROMPTS
# ============================================

def truncate_prompt(
    prompt: str,
    max_chars: int = 100000,
    truncate_middle: bool = True,
    placeholder: str = "\n\n[... conteúdo truncado para reduzir tamanho ...]\n\n"
) -> Tuple[str, bool]:
    """
    Trunca prompt muito grande de forma inteligente.

    PROBLEMA: Prompts com 100k+ chars causam latência alta e podem
    exceder limites de contexto do modelo.

    SOLUÇÃO: Trunca o meio do prompt (geralmente documentos anexados)
    preservando início (instruções) e fim (pergunta/tarefa).

    Args:
        prompt: Prompt original
        max_chars: Tamanho máximo em caracteres (default: 100k)
        truncate_middle: Se True, remove o meio; se False, remove o final
        placeholder: Texto que substitui a parte removida

    Returns:
        Tuple[str, bool]: (prompt_truncado, foi_truncado)

    Exemplo:
        prompt, truncado = truncate_prompt(prompt_grande, max_chars=80000)
        if truncado:
            logger.warning("Prompt foi truncado")
    """
    if len(prompt) <= max_chars:
        return prompt, False

    if truncate_middle:
        # Preserva início e fim, remove o meio
        # 40% início, 60% fim (fim geralmente tem a tarefa/pergunta)
        keep_start = int(max_chars * 0.4)
        keep_end = max_chars - keep_start - len(placeholder)

        truncated = (
            prompt[:keep_start] +
            placeholder +
            prompt[-keep_end:]
        )
    else:
        # Remove apenas o final
        truncated = prompt[:max_chars - len(placeholder)] + placeholder

    chars_removed = len(prompt) - len(truncated) + len(placeholder)
    logger.warning(
        f"[Prompt] Truncado de {len(prompt):,} para {len(truncated):,} chars "
        f"(-{chars_removed:,} chars, ~{chars_removed//4:,} tokens)"
    )

    return truncated, True


def estimate_tokens(text: str) -> int:
    """
    Estima número de tokens para texto em português.

    Regra: ~4 caracteres por token para português/inglês.
    Mais preciso que len(text)/4 pois considera espaços.

    Args:
        text: Texto para estimar

    Returns:
        Estimativa de tokens
    """
    # Conta palavras + pontuação como aproximação
    # Português tem ~1.3 tokens por palavra em média
    words = len(text.split())
    chars = len(text)

    # Média ponderada entre contagem de palavras e caracteres
    by_words = int(words * 1.3)
    by_chars = chars // 4

    return (by_words + by_chars) // 2


def smart_truncate_for_context(
    system_prompt: str,
    user_prompt: str,
    max_total_tokens: int = 128000,
    reserve_output_tokens: int = 8000
) -> Tuple[str, str, bool]:
    """
    Trunca prompts para caber no contexto do modelo.

    INTELIGÊNCIA: Prioriza system_prompt (instruções) e trunca
    user_prompt (documentos/dados) quando necessário.

    Args:
        system_prompt: Prompt do sistema (preservado integralmente se possível)
        user_prompt: Prompt do usuário (pode ser truncado)
        max_total_tokens: Limite de contexto do modelo (default: 128k)
        reserve_output_tokens: Tokens reservados para saída (default: 8k)

    Returns:
        Tuple[system_prompt, user_prompt, foi_truncado]

    Exemplo:
        sys, user, truncado = smart_truncate_for_context(
            system_prompt=instrucoes,
            user_prompt=documentos_longos,
            max_total_tokens=128000
        )
    """
    available_tokens = max_total_tokens - reserve_output_tokens

    sys_tokens = estimate_tokens(system_prompt)
    user_tokens = estimate_tokens(user_prompt)
    total_tokens = sys_tokens + user_tokens

    if total_tokens <= available_tokens:
        return system_prompt, user_prompt, False

    # Precisa truncar - prioriza manter system_prompt
    tokens_to_remove = total_tokens - available_tokens

    # Se system_prompt já é grande demais, trunca ambos
    if sys_tokens > available_tokens * 0.3:
        # System prompt usa mais de 30% do contexto - trunca proporcionalmente
        sys_budget = int(available_tokens * 0.3)
        user_budget = available_tokens - sys_budget

        sys_max_chars = sys_budget * 4
        user_max_chars = user_budget * 4

        system_prompt, _ = truncate_prompt(system_prompt, sys_max_chars)
        user_prompt, _ = truncate_prompt(user_prompt, user_max_chars)
    else:
        # Trunca apenas user_prompt
        user_budget = available_tokens - sys_tokens
        user_max_chars = user_budget * 4
        user_prompt, _ = truncate_prompt(user_prompt, user_max_chars)

    logger.info(
        f"[Prompt] Contexto ajustado: system={estimate_tokens(system_prompt)} tokens, "
        f"user={estimate_tokens(user_prompt)} tokens "
        f"(limite: {available_tokens} tokens)"
    )

    return system_prompt, user_prompt, True


# ============================================
# WRAPPER SSE COM HEARTBEAT
# ============================================

async def sse_with_heartbeat(
    generator: AsyncGenerator[str, None],
    heartbeat_interval: float = 15.0,
    heartbeat_comment: str = ": heartbeat"
) -> AsyncGenerator[str, None]:
    """
    Wrapper que adiciona heartbeats a um generator SSE para manter conexão viva.

    PROBLEMA: Proxies reversos (nginx, cloudflare) podem fechar conexões ociosas
    após 30-60s sem dados. Se o modelo demora para gerar o primeiro token,
    a conexão pode cair.

    SOLUÇÃO: Envia comentários SSE periódicos (que o cliente ignora) para
    manter a conexão ativa.

    Args:
        generator: Generator original que produz chunks de texto
        heartbeat_interval: Intervalo entre heartbeats em segundos (default: 15s)
        heartbeat_comment: Formato do comentário SSE (default: ": heartbeat")

    Yields:
        Chunks de texto intercalados com heartbeats

    Exemplo:
        async def stream_response():
            gen = gemini_service.generate_stream(prompt)
            async for chunk in sse_with_heartbeat(gen):
                yield f"data: {json.dumps({'text': chunk})}\\n\\n"
    """
    import json

    last_heartbeat = time.perf_counter()
    generator_exhausted = False
    pending_chunk = None

    while not generator_exhausted:
        try:
            # Tenta obter próximo chunk com timeout
            chunk = await asyncio.wait_for(
                generator.__anext__(),
                timeout=heartbeat_interval
            )
            yield chunk
            last_heartbeat = time.perf_counter()

        except asyncio.TimeoutError:
            # Timeout - envia heartbeat e continua esperando
            yield heartbeat_comment + "\n"
            logger.debug("[SSE] Heartbeat enviado")

        except StopAsyncIteration:
            # Generator terminou
            generator_exhausted = True


async def stream_to_sse(
    generator: AsyncGenerator[str, None],
    event_type: str = "chunk",
    include_heartbeat: bool = True,
    heartbeat_interval: float = 15.0
) -> AsyncGenerator[str, None]:
    """
    Converte generator de texto em eventos SSE formatados.

    Args:
        generator: Generator que produz chunks de texto
        event_type: Tipo do evento SSE (default: "chunk")
        include_heartbeat: Se True, adiciona heartbeats periódicos
        heartbeat_interval: Intervalo entre heartbeats

    Yields:
        Eventos SSE formatados: "event: chunk\\ndata: {...}\\n\\n"

    Exemplo:
        @app.get("/stream")
        async def stream():
            gen = gemini_service.generate_stream(prompt)
            return StreamingResponse(
                stream_to_sse(gen),
                media_type="text/event-stream"
            )
    """
    import json

    # Envia evento de início
    yield f"event: start\ndata: {json.dumps({'status': 'started'})}\n\n"

    full_content = ""
    chunk_count = 0
    last_heartbeat = time.perf_counter()

    try:
        async for chunk in generator:
            # Verifica se é hora de heartbeat
            now = time.perf_counter()
            if include_heartbeat and (now - last_heartbeat) > heartbeat_interval:
                yield ": heartbeat\n\n"
                last_heartbeat = now

            full_content += chunk
            chunk_count += 1

            # Envia chunk como evento SSE
            yield f"event: {event_type}\ndata: {json.dumps({'text': chunk, 'index': chunk_count})}\n\n"
            last_heartbeat = time.perf_counter()

        # Envia evento de conclusão
        yield f"event: done\ndata: {json.dumps({'status': 'completed', 'total_chunks': chunk_count, 'total_chars': len(full_content)})}\n\n"

    except Exception as e:
        # Envia evento de erro
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        logger.error(f"[SSE] Erro no stream: {e}")


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
    # Truncamento de prompts
    "truncate_prompt",
    "estimate_tokens",
    "smart_truncate_for_context",
    # SSE com heartbeat
    "sse_with_heartbeat",
    "stream_to_sse",
    # Diagnóstico
    "get_cache_stats",
    "clear_cache",
    "get_service_status",
]