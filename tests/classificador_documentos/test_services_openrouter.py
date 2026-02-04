# tests/classificador_documentos/test_services_openrouter.py
"""
Testes unitários do serviço OpenRouter.

Testa:
- Configuração do serviço
- Chamadas à API (com mocks)
- Parsing de respostas JSON
- Retry com backoff
- Tratamento de erros

Autor: LAB/PGE-MS
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import json


class TestOpenRouterConfig:
    """Testes de configuração do OpenRouter"""

    def test_config_default_values(self):
        """Testa valores padrão da configuração"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterConfig

        config = OpenRouterConfig(api_key="test-key")

        assert config.api_key == "test-key"
        assert config.base_url == "https://openrouter.ai/api/v1/chat/completions"
        assert config.timeout == 60.0
        assert config.retry_delays == [5, 15, 30]
        assert config.default_model == "google/gemini-2.5-flash-lite"
        assert config.temperature == 0.1

    def test_config_from_env_without_key(self):
        """Testa carregamento sem API key"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterConfig

        with patch.dict('os.environ', {}, clear=True):
            config = OpenRouterConfig.from_env()
            assert config.api_key == ""

    def test_config_from_env_with_key(self):
        """Testa carregamento com API key"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterConfig

        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test-api-key'}):
            config = OpenRouterConfig.from_env()
            assert config.api_key == "test-api-key"


class TestOpenRouterResult:
    """Testes do dataclass OpenRouterResult"""

    def test_result_success(self):
        """Testa resultado de sucesso"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterResult

        result = OpenRouterResult(
            sucesso=True,
            resultado={"categoria": "teste", "confianca": "alta"},
            tokens_entrada=100,
            tokens_saida=50,
            tempo_ms=500
        )

        assert result.sucesso is True
        assert result.resultado["categoria"] == "teste"
        assert result.erro is None

    def test_result_failure(self):
        """Testa resultado de falha"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterResult

        result = OpenRouterResult(
            sucesso=False,
            erro="Timeout após 60s",
            tempo_ms=60000
        )

        assert result.sucesso is False
        assert result.erro == "Timeout após 60s"
        assert result.resultado is None


class TestOpenRouterService:
    """Testes do serviço OpenRouter"""

    def test_init_with_config(self):
        """Testa inicialização com configuração customizada"""
        from sistemas.classificador_documentos.services_openrouter import (
            OpenRouterService, OpenRouterConfig
        )

        config = OpenRouterConfig(api_key="custom-key", timeout=30.0)
        service = OpenRouterService(config)

        assert service.config.api_key == "custom-key"
        assert service.config.timeout == 30.0

    def test_init_default(self):
        """Testa inicialização com configuração padrão"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'env-key'}):
            service = OpenRouterService()
            assert service.config.api_key == "env-key"

    def test_get_headers(self):
        """Testa geração de headers"""
        from sistemas.classificador_documentos.services_openrouter import (
            OpenRouterService, OpenRouterConfig
        )

        config = OpenRouterConfig(api_key="test-key")
        service = OpenRouterService(config)

        headers = service._get_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json; charset=utf-8"

    @pytest.mark.asyncio
    async def test_classificar_without_api_key(self):
        """Testa classificação sem API key"""
        from sistemas.classificador_documentos.services_openrouter import (
            OpenRouterService, OpenRouterConfig
        )

        config = OpenRouterConfig(api_key="")
        service = OpenRouterService(config)

        result = await service.classificar(
            modelo="google/gemini-2.5-flash-lite",
            prompt_sistema="Teste",
            nome_arquivo="doc.pdf",
            chunk_texto="Texto de teste"
        )

        assert result.sucesso is False
        assert "não configurada" in result.erro

    @pytest.mark.asyncio
    async def test_classificar_success(self):
        """Testa classificação com sucesso (mock)"""
        from sistemas.classificador_documentos.services_openrouter import (
            OpenRouterService, OpenRouterConfig
        )

        config = OpenRouterConfig(api_key="test-key")
        service = OpenRouterService(config)

        # Mock da resposta
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "categoria": "decisao",
                        "subcategoria": "deferida",
                        "confianca": "alta",
                        "justificativa_breve": "Decisão deferitória",
                        "numero_processo_cnj": "0800001-00.2024.8.12.0001"
                    })
                }
            }],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50
            }
        }

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_http_response = Mock()
            mock_http_response.status_code = 200
            mock_http_response.json.return_value = mock_response
            mock_http_response.raise_for_status = Mock()

            mock_instance.post.return_value = mock_http_response

            result = await service.classificar(
                modelo="google/gemini-2.5-flash-lite",
                prompt_sistema="Classifique este documento",
                nome_arquivo="doc.pdf",
                chunk_texto="Texto do documento"
            )

            assert result.sucesso is True
            assert result.resultado["categoria"] == "decisao"
            assert result.resultado["confianca"] == "alta"
            assert result.tokens_entrada == 100
            assert result.tokens_saida == 50


class TestParseJsonResponse:
    """Testes do parser de resposta JSON"""

    def test_parse_valid_json(self):
        """Testa parsing de JSON válido"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        service = OpenRouterService()

        content = json.dumps({
            "categoria": "decisao",
            "confianca": "alta",
            "justificativa_breve": "Decisão válida"
        })

        resultado, erro = service._parsear_resposta_json(content)

        assert erro is None
        assert resultado["categoria"] == "decisao"
        assert resultado["confianca"] == "alta"

    def test_parse_json_with_extra_text(self):
        """Testa parsing de JSON com texto extra"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        service = OpenRouterService()

        content = 'Aqui está a classificação: {"categoria": "teste", "confianca": "media", "justificativa_breve": "OK"}'

        resultado, erro = service._parsear_resposta_json(content)

        assert erro is None
        assert resultado["categoria"] == "teste"

    def test_parse_invalid_json(self):
        """Testa parsing de JSON inválido"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        service = OpenRouterService()

        content = "Texto sem JSON válido"

        resultado, erro = service._parsear_resposta_json(content)

        assert resultado is None
        assert erro is not None
        assert "JSON" in erro

    def test_parse_missing_required_fields(self):
        """Testa parsing com campos obrigatórios faltando"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        service = OpenRouterService()

        content = json.dumps({
            "categoria": "teste"
            # Faltam: confianca, justificativa_breve
        })

        resultado, erro = service._parsear_resposta_json(content)

        assert resultado is None
        assert "obrigatórios faltando" in erro

    def test_parse_invalid_confianca(self):
        """Testa parsing com valor de confiança inválido"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        service = OpenRouterService()

        content = json.dumps({
            "categoria": "teste",
            "confianca": "muito_alta",  # Valor inválido
            "justificativa_breve": "OK"
        })

        resultado, erro = service._parsear_resposta_json(content)

        assert resultado is None
        assert "confiança inválido" in erro

    def test_parse_normalize_media_accent(self):
        """Testa normalização de 'média' para 'media'"""
        from sistemas.classificador_documentos.services_openrouter import OpenRouterService

        service = OpenRouterService()

        content = json.dumps({
            "categoria": "teste",
            "confianca": "média",  # Com acento
            "justificativa_breve": "OK"
        })

        resultado, erro = service._parsear_resposta_json(content)

        assert erro is None
        assert resultado["confianca"] == "media"  # Normalizado


class TestGetOpenRouterService:
    """Testes do singleton"""

    def test_singleton(self):
        """Testa que retorna singleton"""
        from sistemas.classificador_documentos.services_openrouter import get_openrouter_service

        with patch.dict('os.environ', {'OPENROUTER_API_KEY': 'test'}):
            service1 = get_openrouter_service()
            service2 = get_openrouter_service()

            assert service1 is service2
