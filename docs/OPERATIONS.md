# Operacoes e Deploy

## Ambientes

- Dev local: SQLite (`portal.db`) e `.env` local.
- Producao: PostgreSQL e variaveis via Railway.

## Deploy (Railway)

- Arquivos relevantes: `railway.toml`, `nixpacks.toml`, `Procfile`.
- Build instala dependencias e Playwright (chromium) conforme `railway.toml`.
- Comando de start: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
- Health check: `GET /health`.

## Variaveis de ambiente

### Banco

- `DATABASE_URL` (sqlite ou postgresql).
- `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`.

### Auth e seguranca

- `SECRET_KEY` (obrigatorio em producao).
- `ALGORITHM` (default HS256).
- `ACCESS_TOKEN_EXPIRE_MINUTES`.
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
- `DEFAULT_USER_PASSWORD`.
- `ALLOWED_ORIGINS` (CORS).
- `ENV` ou `RAILWAY_ENVIRONMENT` para modo producao.

### IA (Gemini)

- `GEMINI_KEY`.
- `GEMINI_MODEL` (padrao para o portal).

### IA (OpenRouter - legado)

- `OPENROUTER_API_KEY`.
- `OPENROUTER_MODEL`.
- `FULL_REPORT_MODEL`.

### TJ-MS (SOAP/Subconta)

- `TJ_WSDL_URL` (SOAP legado usado por assistencia_judiciaria).
- `TJ_WS_USER`, `TJ_WS_PASS` (credenciais SOAP legado).
- `TJMS_PROXY_URL` (proxy Fly.io para SOAP).
- `TJMS_PROXY_LOCAL_URL` (proxy local/Ngrok para subconta).
- `MNI_USER`, `MNI_PASS` (credenciais SOAP no client centralizado).
- `TJMS_USUARIO`, `TJMS_SENHA` (credenciais web para subconta).
- `TJMS_SOAP_TIMEOUT`, `TJMS_SUBCONTA_TIMEOUT`.

### Rate limit

- `RATE_LIMIT_ENABLED` (true/false).
- `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_LOGIN`, `RATE_LIMIT_AI`.
- `RATE_LIMIT_STORAGE` (ex.: `memory://`).

## Servicos dependentes

- PostgreSQL (prod) ou SQLite (dev).
- Google Gemini API.
- OpenRouter API (legado, usado em matriculas_confrontantes).
- TJ-MS SOAP e Subconta via proxies.

## Build e deploy

```bash
# Railway (git push no branch configurado)
git push origin main

# Health check
curl https://<host>/health
```

## Troubleshooting

- Ver `RUNBOOK.md` para procedimentos detalhados.
- Logs de auditoria: `logs/audit.log`.
- Logs do servidor: output do Uvicorn.

## Pontos nao inferidos com seguranca

- Nao ha pipeline CI formal no repositorio.
- Nao ha jobs cron configurados no codigo.
