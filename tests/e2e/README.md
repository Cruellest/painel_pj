# Testes E2E - Portal PGE-MS

Testes End-to-End que verificam fluxos críticos de ponta a ponta.

## Estrutura

```
tests/e2e/
├── __init__.py
├── README.md
├── test_critical_flows.py    # Fluxos críticos básicos
└── (futuros testes específicos)
```

## Executar Testes

```bash
# Todos os testes E2E
pytest tests/e2e/ -v

# Teste específico
pytest tests/e2e/test_critical_flows.py -v

# Com coverage
pytest tests/e2e/ --cov=. --cov-report=html

# Apenas testes de health check
pytest tests/e2e/test_critical_flows.py::TestHealthCheck -v
```

## Fluxos Testados

### 1. Health Checks
- `GET /health` - Health básico
- `GET /health/detailed` - Health detalhado
- `GET /health/ready` - Readiness
- `GET /health/live` - Liveness

### 2. Métricas
- `GET /metrics` - Métricas Prometheus

### 3. Autenticação
- `POST /auth/login` - Login com credenciais
- Endpoints protegidos sem token

### 4. Rotas Públicas
- `/` - Rota raiz
- `/docs` - Swagger UI
- `/openapi.json` - Schema OpenAPI

### 5. Dashboard
- `/admin/dashboard` - Dashboard de métricas (auth required)

### 6. Segurança
- Headers de segurança (X-Request-ID, etc.)
- Rate limiting básico

## Adicionar Novos Testes

Para adicionar novos testes E2E:

1. Crie um novo arquivo `test_*.py` em `tests/e2e/`
2. Use as fixtures existentes (`client`, `auth_headers`)
3. Agrupe testes relacionados em classes
4. Documente o que cada teste verifica

Exemplo:

```python
class TestMeuFluxo:
    def test_passo_1(self, client):
        response = client.get("/minha-rota")
        assert response.status_code == 200

    def test_passo_2(self, client, auth_headers):
        response = client.get("/rota-protegida", headers=auth_headers)
        assert response.status_code == 200
```

## Mocks

Para testes que dependem de serviços externos:

```python
from unittest.mock import patch

def test_com_mock(self, client):
    with patch("services.external_service.call") as mock:
        mock.return_value = {"data": "mocked"}
        response = client.get("/endpoint")
        assert response.status_code == 200
```

---

**Autor**: LAB/PGE-MS
