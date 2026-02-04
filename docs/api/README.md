# API

Documentacao da API REST do Portal PGE-MS.

## Conteudo

| Documento | Descricao |
|-----------|-----------|
| [API.md](API.md) | Referencia completa de endpoints |

## Documentacao Interativa

Alem desta documentacao, voce pode acessar a documentacao interativa (OpenAPI/Swagger):

- **Local**: http://localhost:8000/docs
- **Producao**: https://portal-pge.fly.dev/docs

## Autenticacao

Todos os endpoints (exceto `/login` e `/health`) requerem autenticacao JWT.

```bash
# Obter token
curl -X POST /auth/login -d '{"email": "...", "senha": "..."}'

# Usar token
curl -H "Authorization: Bearer <token>" /api/...
```
