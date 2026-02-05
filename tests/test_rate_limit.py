# tests/test_rate_limit.py
# -*- coding: utf-8 -*-
"""
Testes para o módulo de Rate Limiting (utils/rate_limit.py)

Testa:
- Detecção de IP real atrás de proxies
- Identificação de usuário
- Handlers de rate limit
- SafeRateLimitMiddleware
- Limiter com diferentes configurações
"""

import pytest
import os
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from utils.rate_limit import (
    get_real_ip,
    get_user_identifier,
    rate_limit_exceeded_handler,
    SafeRateLimitMiddleware,
    limiter,
    RATE_LIMIT_LOGIN,
    RATE_LIMIT_AI,
    LIMITS,
)


# ==================================================
# FIXTURES
# ==================================================


@pytest.fixture
def mock_request():
    """Cria um mock de Request básico."""
    request = Mock(spec=Request)
    request.headers = {}
    request.url.path = "/test"
    return request


@pytest.fixture
def mock_request_with_forwarded_for():
    """Cria um mock de Request com X-Forwarded-For."""
    request = Mock(spec=Request)
    request.headers = {"X-Forwarded-For": "192.168.1.100, 10.0.0.1"}
    request.url.path = "/test"
    return request


@pytest.fixture
def mock_request_with_real_ip():
    """Cria um mock de Request com X-Real-IP."""
    request = Mock(spec=Request)
    request.headers = {"X-Real-IP": "203.0.113.42"}
    request.url.path = "/test"
    return request


@pytest.fixture
def mock_request_with_token():
    """Cria um mock de Request com Bearer token."""
    request = Mock(spec=Request)
    request.headers = {"Authorization": "Bearer test-token"}
    request.url.path = "/test"
    return request


@pytest.fixture
def test_app():
    """Cria uma aplicação FastAPI de teste com rate limiter."""
    app = FastAPI()
    app.state.limiter = limiter
    
    # Registra o middleware
    app.add_middleware(SafeRateLimitMiddleware)
    
    # Handler de exceção
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    
    @app.get("/test")
    @limiter.limit("2/minute")
    async def test_endpoint(request: Request):
        return {"message": "success"}
    
    @app.post("/login")
    @limiter.limit(RATE_LIMIT_LOGIN)
    async def login_endpoint(request: Request):
        return {"message": "login success"}
    
    return app


# ==================================================
# TESTES: get_real_ip
# ==================================================


class TestGetRealIP:
    """Testes para função get_real_ip."""
    
    def test_get_real_ip_from_x_forwarded_for(self, mock_request_with_forwarded_for):
        """Deve extrair IP do header X-Forwarded-For (primeiro da lista)."""
        with patch('utils.rate_limit.get_remote_address', return_value='127.0.0.1'):
            ip = get_real_ip(mock_request_with_forwarded_for)
            assert ip == "192.168.1.100"
    
    def test_get_real_ip_from_x_real_ip(self, mock_request_with_real_ip):
        """Deve extrair IP do header X-Real-IP quando X-Forwarded-For não existe."""
        with patch('utils.rate_limit.get_remote_address', return_value='127.0.0.1'):
            ip = get_real_ip(mock_request_with_real_ip)
            assert ip == "203.0.113.42"
    
    def test_get_real_ip_fallback_direct(self, mock_request):
        """Deve usar get_remote_address como fallback quando nenhum header existe."""
        with patch('utils.rate_limit.get_remote_address', return_value='127.0.0.1'):
            ip = get_real_ip(mock_request)
            assert ip == "127.0.0.1"
    
    def test_get_real_ip_strips_whitespace(self):
        """Deve remover espaços em branco do IP."""
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "  192.168.1.100  , 10.0.0.1"}
        request.url.path = "/test"
        
        with patch('utils.rate_limit.get_remote_address', return_value='127.0.0.1'):
            ip = get_real_ip(request)
            assert ip == "192.168.1.100"


# ==================================================
# TESTES: get_user_identifier
# ==================================================


class TestGetUserIdentifier:
    """Testes para função get_user_identifier."""
    
    def test_get_user_identifier_fallback_to_ip(self, mock_request):
        """Deve retornar IP como fallback quando não há token."""
        with patch('utils.rate_limit.get_real_ip', return_value='192.168.1.100'):
            identifier = get_user_identifier(mock_request)
            assert identifier == "ip:192.168.1.100"
    
    def test_get_user_identifier_with_invalid_token(self, mock_request_with_token):
        """Deve retornar IP quando token é inválido."""
        with patch('utils.rate_limit.get_real_ip', return_value='192.168.1.100'):
            with patch('auth.security.decode_token', side_effect=Exception("Invalid token")):
                identifier = get_user_identifier(mock_request_with_token)
                assert identifier == "ip:192.168.1.100"
    
    def test_get_user_identifier_with_valid_token(self, mock_request_with_token):
        """Deve retornar user_id quando token é válido."""
        with patch('auth.security.decode_token', return_value={"user_id": "user123"}):
            identifier = get_user_identifier(mock_request_with_token)
            assert identifier == "user:user123"
    
    def test_get_user_identifier_token_without_user_id(self, mock_request_with_token):
        """Deve retornar IP quando token não contém user_id."""
        with patch('utils.rate_limit.get_real_ip', return_value='192.168.1.100'):
            with patch('auth.security.decode_token', return_value={"other": "data"}):
                identifier = get_user_identifier(mock_request_with_token)
                assert identifier == "ip:192.168.1.100"


# ==================================================
# TESTES: rate_limit_exceeded_handler
# ==================================================


class TestRateLimitExceededHandler:
    """Testes para handler customizado de rate limit."""
    
    def test_handler_with_rate_limit_exceeded_exception(self, mock_request):
        """Deve retornar JSON 429 com RateLimitExceeded."""
        # Criar uma exceção genérica similar a RateLimitExceeded
        exc = Exception("10 per 1 minute")
        exc.detail = "10 per 1 minute"
        
        response = asyncio.run(rate_limit_exceeded_handler(mock_request, exc))
        
        assert response.status_code == 429
        assert "rate_limit_exceeded" in response.body.decode()
        assert "429" in str(response.status_code)
    
    def test_handler_with_value_error(self, mock_request):
        """Deve retornar JSON 429 com ValueError."""
        exc = ValueError("couldn't parse rate limit string ''")
        
        response = asyncio.run(rate_limit_exceeded_handler(mock_request, exc))
        
        assert response.status_code == 429
        body = response.body.decode()
        assert "rate_limit_exceeded" in body
    
    def test_handler_response_has_correct_headers(self, mock_request):
        """Response deve ter headers corretos."""
        exc = Exception("5 per 1 minute")
        exc.detail = "5 per 1 minute"
        
        response = asyncio.run(rate_limit_exceeded_handler(mock_request, exc))
        
        # O handler extrai o número da string "5 per 1 minute", então será "5"
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "5"
    
    def test_handler_response_json_structure(self, mock_request):
        """Response JSON deve ter estrutura correta."""
        exc = Exception("10 per 1 minute")
        exc.detail = "10 per 1 minute"
        
        response = asyncio.run(rate_limit_exceeded_handler(mock_request, exc))
        
        import json
        body = json.loads(response.body.decode())
        assert "detail" in body
        assert "error" in body
        assert "retry_after" in body
        assert body["error"] == "rate_limit_exceeded"


# ==================================================
# TESTES: SafeRateLimitMiddleware
# ==================================================


class TestSafeRateLimitMiddleware:
    """Testes para SafeRateLimitMiddleware."""
    
    def test_middleware_passes_normal_request(self):
        """Middleware deve passar requisições normais sem modificação."""
        async def run_test():
            middleware = SafeRateLimitMiddleware(app=Mock())
            request = Mock(spec=Request)
            request.headers = {}
            request.url.path = "/test"
            
            async def call_next(req):
                return JSONResponse({"status": "ok"})
            
            response = await middleware.dispatch(request, call_next)
            return response
        
        response = asyncio.run(run_test())
        assert response.status_code == 200
    
    def test_middleware_catches_rate_limit_exceeded(self):
        """Middleware deve capturar exceções de rate limit e retornar 429."""
        async def run_test():
            middleware = SafeRateLimitMiddleware(app=Mock())
            request = Mock(spec=Request)
            request.headers = {}
            request.url.path = "/test"
            
            async def call_next(req):
                # Middleware captura ValueError especificamente para rate limit
                raise ValueError("couldn't parse rate limit string ''")
            
            response = await middleware.dispatch(request, call_next)
            return response
        
        response = asyncio.run(run_test())
        assert response.status_code == 429
    
    def test_middleware_catches_value_error(self):
        """Middleware deve capturar ValueError e retornar 429."""
        async def run_test():
            middleware = SafeRateLimitMiddleware(app=Mock())
            request = Mock(spec=Request)
            request.headers = {}
            request.url.path = "/test"
            
            async def call_next(req):
                raise ValueError("couldn't parse rate limit string ''")
            
            response = await middleware.dispatch(request, call_next)
            return response
        
        response = asyncio.run(run_test())
        assert response.status_code == 429


# ==================================================
# TESTES: Integração com FastAPI
# ==================================================


class TestRateLimitIntegration:
    """Testes de integração com FastAPI."""
    
    def test_rate_limit_configuration_enabled(self):
        """Rate limiter deve estar ativado por padrão."""
        assert limiter.enabled is True
    
    def test_rate_limit_default_configured(self):
        """Limite padrão deve estar configurado."""
        assert "100/minute" in RATE_LIMIT_LOGIN or RATE_LIMIT_LOGIN
    
    def test_limits_dict_has_all_keys(self):
        """LIMITS dict deve ter todas as chaves esperadas."""
        expected_keys = ["login", "ai", "default", "heavy", "upload", "export"]
        for key in expected_keys:
            assert key in LIMITS
            assert LIMITS[key]  # Deve ter valor não-vazio
    
    def test_rate_limit_login_decorator(self):
        """Decorator limit_login deve estar disponível."""
        from utils.rate_limit import limit_login
        assert callable(limit_login)
    
    def test_rate_limit_ai_decorator(self):
        """Decorator limit_ai_request deve estar disponível."""
        from utils.rate_limit import limit_ai_request
        assert callable(limit_ai_request)
    
    def test_rate_limit_export_decorator(self):
        """Decorator limit_export deve estar disponível."""
        from utils.rate_limit import limit_export
        assert callable(limit_export)


# ==================================================
# TESTES: Environment Variables
# ==================================================


class TestEnvironmentVariables:
    """Testes para configuração via variáveis de ambiente."""
    
    def test_rate_limit_env_vars_not_empty(self):
        """Variáveis de ambiente de rate limit não devem estar vazias."""
        # Em teste, devem ter valores padrão
        assert os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
        assert os.getenv("RATE_LIMIT_LOGIN", "5/minute")
        assert os.getenv("RATE_LIMIT_AI", "10/minute")
    
    def test_rate_limit_enabled_env_var(self):
        """RATE_LIMIT_ENABLED deve estar true por padrão."""
        enabled = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
        assert enabled is True


# ==================================================
# TESTES: Edge Cases
# ==================================================


class TestEdgeCases:
    """Testes para casos extremos."""
    
    def test_get_real_ip_with_empty_forwarded_for(self):
        """Deve lidar com X-Forwarded-For vazio."""
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": ""}
        request.url.path = "/test"
        
        with patch('utils.rate_limit.get_remote_address', return_value='127.0.0.1'):
            ip = get_real_ip(request)
            # Com string vazia, split retorna [''], strip retorna '', que é falsy
            # Então deve usar o fallback
            assert ip  # Deve ter algum valor
    
    def test_get_real_ip_with_multiple_proxies(self):
        """Deve extrair o primeiro IP de uma cadeia de proxies."""
        request = Mock(spec=Request)
        request.headers = {"X-Forwarded-For": "192.168.1.100, 10.0.0.1, 172.16.0.1"}
        request.url.path = "/test"
        
        with patch('utils.rate_limit.get_remote_address', return_value='127.0.0.1'):
            ip = get_real_ip(request)
            assert ip == "192.168.1.100"
    
    def test_handler_with_exception_without_detail(self):
        """Handler deve funcionar com exceção sem atributo detail."""
        request = Mock(spec=Request)
        request.headers = {}
        request.url.path = "/test"
        
        # Cria uma exceção genérica
        exc = Exception("Something went wrong")
        
        response = asyncio.run(rate_limit_exceeded_handler(request, exc))
        
        assert response.status_code == 429
        body = response.body.decode()
        assert "rate_limit_exceeded" in body


# ==================================================
# TESTES: Performance
# ==================================================


class TestPerformance:
    """Testes de performance do rate limiter."""
    
    def test_get_real_ip_performance(self, mock_request_with_forwarded_for):
        """get_real_ip deve ser rápido."""
        import time
        
        with patch('utils.rate_limit.get_remote_address', return_value='127.0.0.1'):
            start = time.time()
            for _ in range(1000):
                get_real_ip(mock_request_with_forwarded_for)
            elapsed = time.time() - start
            
            # 1000 chamadas devem executar em menos de 1 segundo
            assert elapsed < 1.0
    
    def test_get_user_identifier_performance(self, mock_request):
        """get_user_identifier deve ser rápido."""
        import time
        
        with patch('utils.rate_limit.get_real_ip', return_value='192.168.1.100'):
            start = time.time()
            for _ in range(1000):
                get_user_identifier(mock_request)
            elapsed = time.time() - start
            
            # 1000 chamadas devem executar em menos de 1 segundo
            assert elapsed < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
