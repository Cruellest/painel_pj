# RUNBOOK.md - Guia de Operacoes

## Inicio Rapido

### Desenvolvimento Local

```bash
# 1. Clonar e entrar no diretorio
git clone <repo-url>
cd portal-pge

# 2. Criar ambiente virtual
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar ambiente
cp .env.example .env
# Editar .env com suas credenciais

# 5. Rodar servidor
uvicorn main:app --reload --port 8000

# 6. Acessar
# Portal: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Windows (run.bat)

```batch
run.bat
```

---

## Comandos Frequentes

### Servidor

```bash
# Desenvolvimento (com reload)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Producao (multiplos workers)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# Debug (logs verbose)
uvicorn main:app --reload --log-level debug
```

### Banco de Dados

```bash
# Verificar status
sqlite3 portal.db ".tables"

# Backup SQLite
cp portal.db portal.db.backup

# Resetar banco (CUIDADO: perde dados)
rm portal.db
# Reiniciar app para recriar
```

### Testes

```bash
# Rodar todos os testes
pytest tests/

# Com coverage
pytest --cov=. --cov-report=html

# Teste especifico
pytest tests/test_prompt_groups.py -v
```

---

## Troubleshooting

### Erro: "SECRET_KEY nao definida"

**Causa:** Variavel de ambiente ausente em producao.

**Solucao:**
```bash
# Gerar chave segura
python -c "import secrets; print(secrets.token_hex(32))"

# Adicionar ao .env ou variaveis de ambiente
export SECRET_KEY=<chave-gerada>
```

### Erro: "Connection pool exhausted"

**Causa:** Muitas conexoes simultaneas.

**Solucao:**
```bash
# Aumentar pool (Railway)
DB_POOL_SIZE=30
DB_MAX_OVERFLOW=20

# Ou reiniciar app para liberar conexoes
railway restart
```

### Erro: "TJ-MS timeout"

**Causa:** Servidor TJ-MS lento ou indisponivel.

**Solucao:**
1. Verificar status do TJ-MS
2. Tentar novamente em alguns minutos
3. Verificar se proxy esta funcionando

```bash
# Testar conectividade (como admin)
curl -H "Authorization: Bearer <token>" \
  http://localhost:8000/assistencia/api/test-tjms
```

### Erro: "CORS blocked"

**Causa:** Origem nao permitida.

**Solucao:**
```bash
# Adicionar origem permitida
ALLOWED_ORIGINS=http://localhost:3000,https://seu-dominio.com
```

### Erro: "Out of memory"

**Causa:** PDF muito grande em processamento.

**Solucao:**
1. Limitar `max_pages` no processamento
2. Aumentar memoria do container
3. Usar processamento em chunks

---

## Monitoramento

### Health Check

```bash
# Verificar saude da aplicacao
curl http://localhost:8000/health

# Resposta esperada
{
  "status": "ok",
  "service": "portal-pge",
  "has_openrouter_key": true,
  "has_database_url": true
}
```

### Logs

```bash
# Railway
railway logs

# Local
tail -f uvicorn.log

# Filtrar por sistema
grep "gerador_pecas" uvicorn.log
```

### Metricas de Cache

```python
# Acessar stats do cache (via shell)
from utils.cache import config_cache, prompt_cache

print(config_cache.stats())
# {'size': 45, 'hits': 1234, 'misses': 56, 'hit_rate': '95.6%'}
```

---

## Deploy

### Railway (Producao)

```bash
# Deploy automatico via git push
git push origin main

# Verificar status
railway status

# Ver logs em tempo real
railway logs --tail

# Reiniciar servico
railway restart
```

### Variaveis Obrigatorias no Railway

```
DATABASE_URL        # Gerado automaticamente pelo Railway Postgres
SECRET_KEY          # Gerar manualmente
ADMIN_PASSWORD      # Definir senha forte
GEMINI_KEY          # API key do Google
ALLOWED_ORIGINS     # URL do frontend em producao
ENV=production      # Habilita fail-fast para secrets
```

### Rollback

```bash
# Ver deployments anteriores
railway deployments

# Rollback para versao anterior
railway rollback <deployment-id>
```

---

## Backup e Restore

### PostgreSQL (Producao)

```bash
# Backup
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Restore
psql $DATABASE_URL < backup_20260111.sql
```

### SQLite (Dev)

```bash
# Backup
cp portal.db backups/portal_$(date +%Y%m%d).db

# Restore
cp backups/portal_20260111.db portal.db
```

---

## Manutencao

### Atualizar Dependencias

```bash
# Ver outdated
pip list --outdated

# Atualizar especifica
pip install --upgrade fastapi

# Atualizar requirements.txt
pip freeze > requirements.txt
```

### Limpar Cache

```python
# Via codigo
from utils.cache import config_cache, prompt_cache

config_cache.invalidate_all()
prompt_cache.invalidate_all()
```

### Rotacionar Secrets

1. Gerar novo SECRET_KEY
2. Atualizar variavel de ambiente
3. Reiniciar aplicacao
4. Usuarios precisarao fazer login novamente

---

## Contatos

| Funcao | Contato |
|--------|---------|
| Desenvolvimento | lab@pge.ms.gov.br |
| Seguranca | seguranca@pge.ms.gov.br |
| Infra/Railway | infra@pge.ms.gov.br |
| TJ-MS (Suporte) | suporte@tjms.jus.br |
