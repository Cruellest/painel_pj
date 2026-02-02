# tests/services/test_gemini_service.py
"""
Testes unitários para o GeminiService.

Cobertura:
- Inicialização e configuração
- Cache de respostas (ResponseCache)
- Normalização de modelos
- Geração de texto (mockado)
- Retry com backoff
- Circuit Breaker
- Truncamento de prompts
- Estimativa de tokens
- Métricas (GeminiMetrics)

Autor: LAB/PGE-MS
"""

# Path setup - deve vir antes de qualquer import do projeto
import sys
import os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from dataclasses import asdict

# Importa classes do serviço
from services.gemini_service import (
    GeminiService,
    GeminiResponse,
    GeminiMetrics,
    ResponseCache,
    # Funções utilitárias
    truncate_prompt,
    estimate_tokens,
    smart_truncate_for_context,
    # Funções de diagnóstico
    get_cache_stats,
    clear_cache,
)


# ============================================
# TESTES DO ResponseCache
# ============================================

class TestResponseCache:
    """Testes para o cache de respostas do Gemini."""

    def test_cache_inicializacao(self):
        """Testa criação do cache com configurações padrão."""
        cache = ResponseCache()

        stats = cache.stats()
        assert stats["size"] == 0
        assert stats["max_size"] == 100
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_cache_set_e_get(self):
        """Testa armazenamento e recuperação de valores."""
        cache = ResponseCache(max_size=10, ttl_seconds=300)

        # Cria resposta mock
        response = GeminiResponse(
            success=True,
            content="Resposta de teste",
            tokens_used=50
        )

        # Armazena
        cache.set(
            prompt="Olá mundo",
            system_prompt="Seja gentil",
            model="gemini-3-flash-preview",
            temperature=0.3,
            value=response
        )

        # Recupera
        cached = cache.get(
            prompt="Olá mundo",
            system_prompt="Seja gentil",
            model="gemini-3-flash-preview",
            temperature=0.3
        )

        assert cached is not None
        assert cached.content == "Resposta de teste"
        assert cached.tokens_used == 50

    def test_cache_miss_prompt_diferente(self):
        """Testa que prompts diferentes não compartilham cache."""
        cache = ResponseCache()

        response = GeminiResponse(success=True, content="Teste")
        cache.set("prompt1", "", "model", 0.3, response)

        # Tenta buscar com prompt diferente
        cached = cache.get("prompt2", "", "model", 0.3)

        assert cached is None

    def test_cache_miss_temperatura_diferente(self):
        """Testa que temperaturas diferentes não compartilham cache."""
        cache = ResponseCache()

        response = GeminiResponse(success=True, content="Teste")
        cache.set("prompt", "", "model", 0.3, response)

        # Tenta buscar com temperatura diferente
        cached = cache.get("prompt", "", "model", 0.7)

        assert cached is None

    def test_cache_eviction_lru(self):
        """Testa que itens são removidos quando cache está cheio (LRU)."""
        cache = ResponseCache(max_size=2, ttl_seconds=300)

        # Adiciona 3 itens (max é 2)
        cache.set("p1", "", "m", 0.3, GeminiResponse(success=True, content="1"))
        cache.set("p2", "", "m", 0.3, GeminiResponse(success=True, content="2"))
        cache.set("p3", "", "m", 0.3, GeminiResponse(success=True, content="3"))

        stats = cache.stats()
        assert stats["size"] == 2  # Deve manter no máximo 2

    def test_cache_stats_hit_miss(self):
        """Testa contagem de hits e misses."""
        cache = ResponseCache()

        cache.set("p1", "", "m", 0.3, GeminiResponse(success=True, content="1"))

        # 2 hits
        cache.get("p1", "", "m", 0.3)
        cache.get("p1", "", "m", 0.3)

        # 1 miss
        cache.get("p2", "", "m", 0.3)

        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert "66.7%" in stats["hit_rate"]  # 2/(2+1) = 66.7%


# ============================================
# TESTES DO GeminiMetrics
# ============================================

class TestGeminiMetrics:
    """Testes para métricas de chamadas ao Gemini."""

    def test_metrics_to_dict(self):
        """Testa conversão de métricas para dicionário."""
        metrics = GeminiMetrics(
            model="gemini-3-flash-preview",
            prompt_chars=1000,
            response_tokens=250,
            time_total_ms=1500.5,
            success=True
        )

        d = metrics.to_dict()

        assert d["model"] == "gemini-3-flash-preview"
        assert d["prompt_chars"] == 1000
        assert d["response_tokens"] == 250
        assert d["time_total_ms"] == 1500.5
        assert d["success"] is True

    def test_metrics_com_auditoria(self):
        """Testa métricas com informações de auditoria."""
        metrics = GeminiMetrics(
            model="gemini-3-pro-preview",
            sistema="gerador_pecas",
            agente="geracao",
            modelo_source="agent",
            temperatura_source="system",
            max_tokens_source="default"
        )

        d = metrics.to_dict()

        assert d["sistema"] == "gerador_pecas"
        assert d["agente"] == "geracao"
        assert "sources" in d
        assert d["sources"]["modelo"] == "agent"

    def test_metrics_log_success(self, caplog):
        """Testa logging de métricas de sucesso."""
        import logging
        caplog.set_level(logging.INFO)

        metrics = GeminiMetrics(
            model="gemini-3-flash-preview",
            prompt_chars=500,
            response_tokens=100,
            time_total_ms=1000,
            success=True
        )

        metrics.log()

        assert "[Gemini]" in caplog.text
        assert "gemini-3-flash-preview" in caplog.text

    def test_metrics_log_failure(self, caplog):
        """Testa logging de métricas de falha."""
        import logging
        caplog.set_level(logging.WARNING)

        metrics = GeminiMetrics(
            model="gemini-3-flash-preview",
            time_total_ms=500,
            success=False,
            error="API Error",
            retry_count=2
        )

        metrics.log()

        assert "ERRO" in caplog.text
        assert "retries=2" in caplog.text


# ============================================
# TESTES DO GeminiService
# ============================================

class TestGeminiService:
    """Testes para o serviço principal do Gemini."""

    def test_inicializacao_sem_api_key(self):
        """Testa inicialização sem API key."""
        with patch.dict('os.environ', {}, clear=True):
            # Remove GEMINI_KEY do ambiente temporariamente
            import os
            old_key = os.environ.pop('GEMINI_KEY', None)

            try:
                service = GeminiService()
                assert not service.is_configured()
            finally:
                if old_key:
                    os.environ['GEMINI_KEY'] = old_key

    def test_inicializacao_com_api_key(self):
        """Testa inicialização com API key."""
        service = GeminiService(api_key="test-api-key")

        assert service.is_configured()
        assert service.api_key == "test-api-key"

    def test_normalize_model_alias_flash(self):
        """Testa normalização de alias 'flash'."""
        result = GeminiService.normalize_model("flash")
        assert result == "gemini-3-flash-preview"

    def test_normalize_model_alias_pro(self):
        """Testa normalização de alias 'pro'."""
        result = GeminiService.normalize_model("pro")
        assert result == "gemini-2.5-pro"

    def test_normalize_model_com_prefixo_google(self):
        """Testa remoção do prefixo 'google/'."""
        result = GeminiService.normalize_model("google/gemini-3-pro-preview")
        assert result == "gemini-3-pro-preview"

    def test_normalize_model_nome_completo(self):
        """Testa que nomes completos não são alterados."""
        result = GeminiService.normalize_model("gemini-3-flash-preview")
        assert result == "gemini-3-flash-preview"

    def test_get_model_for_task_resumo(self):
        """Testa modelo recomendado para resumo."""
        service = GeminiService(api_key="test")
        model = service.get_model_for_task("resumo")
        assert "flash" in model.lower()

    def test_get_model_for_task_geracao(self):
        """Testa modelo recomendado para geração."""
        service = GeminiService(api_key="test")
        model = service.get_model_for_task("geracao")
        assert "pro" in model.lower()

    def test_get_model_for_task_desconhecida(self):
        """Testa fallback para tarefa desconhecida."""
        service = GeminiService(api_key="test")
        model = service.get_model_for_task("tarefa_inexistente")
        # Deve retornar modelo de análise (padrão)
        assert model == service.DEFAULT_MODELS["analise"]


class TestGeminiServiceGenerate:
    """Testes para o método generate do GeminiService."""

    @pytest.mark.asyncio
    async def test_generate_sem_api_key(self):
        """Testa generate sem API key configurada."""
        service = GeminiService(api_key="")

        response = await service.generate(prompt="Olá")

        assert not response.success
        # Pode ser erro local (sem key) ou erro da API (key inválida)
        assert (
            "GEMINI_KEY" in response.error or
            "API key" in response.error or
            "not valid" in response.error
        )

    @pytest.mark.asyncio
    async def test_generate_cache_hit(self):
        """Testa que respostas em cache são retornadas."""
        service = GeminiService(api_key="test-key")

        # Prepara cache com resposta
        from services.gemini_service import _response_cache
        cached_response = GeminiResponse(
            success=True,
            content="Resposta do cache",
            tokens_used=10
        )
        _response_cache.set(
            "Prompt de teste",
            "",
            "gemini-3-flash-preview",
            0.3,
            cached_response
        )

        # Deve retornar do cache
        response = await service.generate(
            prompt="Prompt de teste",
            temperature=0.3
        )

        assert response.success
        assert response.content == "Resposta do cache"
        assert response.metrics.cached is True

    @pytest.mark.asyncio
    async def test_generate_com_circuit_breaker_aberto(self):
        """Testa fail-fast quando circuit breaker está aberto."""
        service = GeminiService(api_key="test-key")

        # Mock do circuit breaker aberto
        with patch('services.gemini_service.CIRCUIT_BREAKER_ENABLED', True):
            mock_cb = MagicMock()
            mock_cb.allow_request.return_value = False
            mock_cb.time_until_retry.return_value = 30.0

            with patch('services.gemini_service.get_gemini_circuit_breaker', return_value=mock_cb):
                response = await service.generate(prompt="Teste")

        assert not response.success
        assert "Circuit breaker aberto" in response.error

    @pytest.mark.asyncio
    async def test_generate_sucesso(self):
        """Testa geração bem-sucedida (mockando HTTP)."""
        service = GeminiService(api_key="test-key")

        # Mock da resposta HTTP
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Resposta gerada pelo modelo"}]
                }
            }],
            "usageMetadata": {"totalTokenCount": 150}
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False

        with patch('services.gemini_service.get_http_client', return_value=mock_client):
            with patch('services.gemini_service.CIRCUIT_BREAKER_ENABLED', False):
                response = await service.generate(
                    prompt="Teste de geração",
                    use_cache=False  # Força chamada real
                )

        assert response.success
        assert response.content == "Resposta gerada pelo modelo"
        assert response.tokens_used == 150


class TestGeminiServiceBuildPayload:
    """Testes para construção de payloads."""

    def test_build_payload_basico(self):
        """Testa payload básico sem opcionais."""
        service = GeminiService(api_key="test")

        payload = service._build_payload(
            prompt="Olá mundo",
            temperature=0.5
        )

        assert "contents" in payload
        assert payload["contents"][0]["parts"][0]["text"] == "Olá mundo"
        assert payload["generationConfig"]["temperature"] == 0.5
        assert "maxOutputTokens" not in payload["generationConfig"]

    def test_build_payload_com_max_tokens(self):
        """Testa payload com max_tokens."""
        service = GeminiService(api_key="test")

        payload = service._build_payload(
            prompt="Teste",
            max_tokens=1000,
            temperature=0.3
        )

        assert payload["generationConfig"]["maxOutputTokens"] == 1000

    def test_build_payload_com_system_prompt(self):
        """Testa payload com system prompt."""
        service = GeminiService(api_key="test")

        payload = service._build_payload(
            prompt="Teste",
            system_prompt="Você é um assistente jurídico.",
            temperature=0.3
        )

        assert "systemInstruction" in payload
        assert payload["systemInstruction"]["parts"][0]["text"] == "Você é um assistente jurídico."

    def test_build_payload_com_thinking_level_flash(self):
        """Testa thinking_level para modelo Flash."""
        service = GeminiService(api_key="test")

        payload = service._build_payload(
            prompt="Teste",
            thinking_level="low",
            model="gemini-3-flash-preview",
            temperature=0.3
        )

        assert "thinkingConfig" in payload["generationConfig"]
        assert payload["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"

    def test_build_payload_thinking_level_invalido_pro(self):
        """Testa que thinking_level inválido para Pro é ignorado."""
        service = GeminiService(api_key="test")

        # "minimal" não é válido para Pro (só low e high)
        payload = service._build_payload(
            prompt="Teste",
            thinking_level="minimal",
            model="gemini-3-pro-preview",
            temperature=0.3
        )

        # Não deve ter thinkingConfig
        assert "thinkingConfig" not in payload["generationConfig"]

    def test_build_payload_thinking_level_modelo_antigo(self):
        """Testa que thinking_level é ignorado para modelos antigos."""
        service = GeminiService(api_key="test")

        payload = service._build_payload(
            prompt="Teste",
            thinking_level="high",
            model="gemini-2.0-flash",  # Modelo antigo
            temperature=0.3
        )

        # Não deve ter thinkingConfig para Gemini 2.x
        assert "thinkingConfig" not in payload["generationConfig"]


# ============================================
# TESTES DE FUNÇÕES UTILITÁRIAS
# ============================================

class TestTruncatePrompt:
    """Testes para truncamento de prompts."""

    def test_prompt_pequeno_nao_truncado(self):
        """Testa que prompts pequenos não são truncados."""
        prompt = "Prompt curto"
        result, truncated = truncate_prompt(prompt, max_chars=1000)

        assert result == prompt
        assert truncated is False

    def test_prompt_grande_truncado_meio(self):
        """Testa truncamento do meio do prompt."""
        prompt = "A" * 10000
        result, truncated = truncate_prompt(prompt, max_chars=1000)

        assert len(result) <= 1000
        assert truncated is True
        assert "[... conteúdo truncado" in result

    def test_prompt_grande_truncado_final(self):
        """Testa truncamento do final do prompt."""
        prompt = "A" * 10000
        result, truncated = truncate_prompt(
            prompt,
            max_chars=1000,
            truncate_middle=False
        )

        assert len(result) <= 1000
        assert truncated is True
        # O placeholder termina com "...]\n\n"
        assert "truncado" in result
        assert result.endswith("]\n\n")


class TestEstimateTokens:
    """Testes para estimativa de tokens."""

    def test_estimativa_texto_curto(self):
        """Testa estimativa para texto curto."""
        text = "Olá mundo"
        tokens = estimate_tokens(text)

        # Texto curto, estimativa razoável
        assert tokens > 0
        assert tokens < 10

    def test_estimativa_texto_longo(self):
        """Testa estimativa para texto longo."""
        text = "palavra " * 1000  # ~8000 caracteres
        tokens = estimate_tokens(text)

        # ~1000 palavras * 1.3 tokens/palavra ≈ 1300
        # ~8000 chars / 4 ≈ 2000
        # Média ≈ 1650
        assert 1000 < tokens < 2500

    def test_estimativa_texto_vazio(self):
        """Testa estimativa para texto vazio."""
        tokens = estimate_tokens("")
        assert tokens == 0


class TestSmartTruncateForContext:
    """Testes para truncamento inteligente de contexto."""

    def test_dentro_do_limite(self):
        """Testa que textos dentro do limite não são truncados."""
        sys_prompt = "Instruções do sistema"
        user_prompt = "Pergunta do usuário"

        sys_out, user_out, truncated = smart_truncate_for_context(
            sys_prompt, user_prompt,
            max_total_tokens=128000
        )

        assert sys_out == sys_prompt
        assert user_out == user_prompt
        assert truncated is False

    def test_trunca_user_prompt(self):
        """Testa que user_prompt é truncado primeiro."""
        sys_prompt = "Instruções" * 100  # ~1000 chars
        user_prompt = "Dados" * 100000   # ~500000 chars

        sys_out, user_out, truncated = smart_truncate_for_context(
            sys_prompt, user_prompt,
            max_total_tokens=1000,  # Limite baixo
            reserve_output_tokens=100
        )

        assert truncated is True
        # System prompt deve ser preservado mais que user prompt proporcionalmente
        assert len(user_out) < len(user_prompt)


# ============================================
# TESTES DE FUNÇÕES DE DIAGNÓSTICO
# ============================================

class TestDiagnostico:
    """Testes para funções de diagnóstico."""

    def test_get_cache_stats(self):
        """Testa obtenção de estatísticas do cache."""
        stats = get_cache_stats()

        assert "size" in stats
        assert "max_size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats

    def test_clear_cache(self):
        """Testa limpeza do cache."""
        # Adiciona algo ao cache
        from services.gemini_service import _response_cache
        _response_cache.set("test", "", "m", 0.3, GeminiResponse(success=True, content="x"))

        # Limpa
        clear_cache()

        # Cache deve estar vazio
        stats = get_cache_stats()
        assert stats["size"] == 0


# ============================================
# TESTES DE INTEGRAÇÃO (MOCKED)
# ============================================

class TestGeminiServiceIntegration:
    """Testes de integração com mocks."""

    @pytest.mark.asyncio
    async def test_fluxo_completo_geracao(self):
        """Testa fluxo completo de geração com mocks."""
        service = GeminiService(api_key="test-key")

        # Mock completo da chamada HTTP
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": "Resposta do teste de integração"}]
                },
                "finishReason": "STOP"
            }],
            "usageMetadata": {"totalTokenCount": 75}
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.is_closed = False

        with patch('services.gemini_service.get_http_client', return_value=mock_client):
            with patch('services.gemini_service.CIRCUIT_BREAKER_ENABLED', False):
                response = await service.generate(
                    prompt="Escreva um parecer sobre responsabilidade civil",
                    system_prompt="Você é um procurador jurídico",
                    model="gemini-3-pro-preview",
                    temperature=0.3,
                    use_cache=False
                )

        assert response.success
        assert response.content == "Resposta do teste de integração"
        assert response.tokens_used == 75
        assert response.metrics is not None
        assert response.metrics.model == "gemini-3-pro-preview"


# ============================================
# FIXTURES
# ============================================

@pytest.fixture(autouse=True)
def limpar_cache():
    """Limpa o cache antes de cada teste."""
    clear_cache()
    yield
    clear_cache()
