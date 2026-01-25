# Testes

## Visao Geral

O Portal PGE-MS utiliza pytest como framework de testes, com suporte para:

- **Testes unitarios**: Testam componentes isolados
- **Testes de integracao**: Testam interacao entre componentes
- **Testes E2E**: Testam fluxos completos de ponta a ponta
- **Testes de carga**: Testam performance sob carga (k6)

## Estrutura de Testes

```
tests/
├── conftest.py                    # Fixtures globais
├── e2e/                           # Testes end-to-end
│   ├── __init__.py
│   ├── README.md
│   └── test_critical_flows.py     # Fluxos criticos
├── services/                      # Testes de servicos
│   ├── test_gemini_service.py     # Gemini Service
│   └── test_tjms_service.py       # TJ-MS Service
├── load/                          # Testes de carga
│   ├── README.md
│   └── k6_load_test.js            # Script k6
├── ia_extracao_regras/            # Testes do sistema de extracao
│   ├── backend/unit/              # Unitarios
│   ├── backend/integration/       # Integracao
│   ├── backend/runtime/           # Runtime
│   ├── e2e/                       # E2E especificos
│   └── mocks/                     # Mocks Gemini
├── classificador_documentos/      # Testes do classificador
└── text_normalizer/               # Testes do normalizador
```

## Como Rodar

### Todos os Testes (pytest)

```bash
# Todos os testes
pytest

# Com verbose
pytest -v

# Com cobertura
pytest --cov=. --cov-report=html
```

### Testes Especificos

```bash
# Testes E2E
pytest tests/e2e/ -v

# Testes de servicos
pytest tests/services/ -v

# Teste especifico
pytest tests/test_gerador_pecas.py -v

# Por nome de funcao
pytest -k "test_health"
```

### Testes de Carga (k6)

```bash
# Instalar k6
# Windows: choco install k6
# Linux: sudo apt install k6
# macOS: brew install k6

# Teste basico (10 VUs, 30s)
k6 run tests/load/k6_load_test.js

# Contra localhost
k6 run -e BASE_URL=http://localhost:8000 tests/load/k6_load_test.js

# Com mais carga
k6 run --vus 50 --duration 2m tests/load/k6_load_test.js

# Salvar resultados
k6 run --out json=results.json tests/load/k6_load_test.js
```

## Tipos de Testes

### Testes Unitarios

Testam funcoes e classes isoladamente.

```python
# tests/test_exemplo.py
import pytest

def test_funcao_simples():
    resultado = minha_funcao(1, 2)
    assert resultado == 3
```

### Testes de Integracao

Testam interacao entre componentes (APIs, banco, etc).

```python
# tests/test_integration_routes.py
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
```

### Testes E2E

Testam fluxos completos de ponta a ponta.

```python
# tests/e2e/test_critical_flows.py
class TestAuthentication:
    def test_login_requires_credentials(self, client):
        response = client.post("/auth/login")
        assert response.status_code in [400, 422]
```

### Testes de Carga

Testam performance e resiliencia sob carga.

Thresholds configurados:
- 95% das requests < 500ms
- Taxa de erro < 1%

## Mocks e Fixtures

### Fixtures (conftest.py)

```python
@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}
```

### Mocks de Servicos Externos

```python
from unittest.mock import patch

def test_com_mock():
    with patch("services.gemini_service.generate") as mock:
        mock.return_value = {"content": "mocked"}
        # teste aqui
```

## Boas Praticas

1. **Isolar testes**: Cada teste deve ser independente
2. **Usar fixtures**: Reutilizar setup comum via fixtures
3. **Mockar servicos externos**: TJ-MS, Gemini, etc.
4. **Nomear claramente**: `test_<funcionalidade>_<cenario>`
5. **Agrupar em classes**: Testes relacionados na mesma classe
6. **Documentar**: Docstrings explicando o que testa

## Cobertura de Codigo

```bash
# Gerar relatorio HTML
pytest --cov=. --cov-report=html

# Ver no terminal
pytest --cov=. --cov-report=term-missing
```

Relatorio gerado em `htmlcov/index.html`.

## CI/CD

Os testes sao executados automaticamente:

1. **Pre-commit**: Testes rapidos antes de commit
2. **Pull Request**: Suite completa antes de merge
3. **Deploy**: Testes de integracao antes de producao

## Lacunas Conhecidas

- Testes de UI (frontend) nao implementados
- Cobertura de `assistencia_judiciaria` e `matriculas_confrontantes` baixa
- Testes de performance de banco de dados ausentes

---

**Autor**: LAB/PGE-MS
