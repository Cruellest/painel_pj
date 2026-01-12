# SECURITY.md - Guia de Seguranca

## Reportando Vulnerabilidades

Se voce descobrir uma vulnerabilidade de seguranca, **NAO abra uma issue publica**.

Entre em contato diretamente:
- Email: seguranca@pge.ms.gov.br
- Assunto: [SEGURANCA] Portal PGE-MS - Descricao breve

Responderemos em ate 48 horas uteis.

---

## Configuracao Segura

### Variaveis de Ambiente Obrigatorias

```bash
# OBRIGATORIO em producao - gere com:
# python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=<chave-de-64-caracteres-hexadecimais>

# OBRIGATORIO em producao
ADMIN_PASSWORD=<senha-forte-minimo-16-caracteres>

# OBRIGATORIO - defina as origens permitidas
ALLOWED_ORIGINS=https://portal.pge.ms.gov.br,https://admin.pge.ms.gov.br

# Ambiente (development, production)
ENV=production
```

### Checklist de Deploy

- [ ] SECRET_KEY definida e unica por ambiente
- [ ] ADMIN_PASSWORD forte (minimo 16 caracteres)
- [ ] ALLOWED_ORIGINS configurado com dominios especificos
- [ ] DATABASE_URL usando SSL (`?sslmode=require`)
- [ ] HTTPS habilitado no load balancer
- [ ] Headers de seguranca configurados (HSTS, CSP, etc)
- [ ] Logs de acesso habilitados
- [ ] Backups automaticos configurados

---

## Autenticacao

### JWT Tokens

- **Algoritmo:** HS256
- **Expiracao:** 8 horas (configuravel via ACCESS_TOKEN_EXPIRE_MINUTES)
- **Armazenamento:** Local Storage no frontend (considerar HttpOnly cookies)

### Senhas

- **Hash:** bcrypt com salt automatico
- **Forca minima:** Nao imposta atualmente (TODO: implementar)
- **Troca obrigatoria:** `must_change_password` flag

### Roles

| Role | Descricao | Permissoes |
|------|-----------|------------|
| `admin` | Administrador | Acesso total |
| `user` | Usuario padrao | Acesso aos sistemas permitidos |

---

## Controle de Acesso

### Sistemas

Usuarios tem acesso controlado por sistema via `sistemas_permitidos`:

```json
{
  "gerador_pecas": true,
  "pedido_calculo": true,
  "prestacao_contas": false,
  "matriculas": false,
  "assistencia": true
}
```

### Grupos de Prompts

- Usuarios podem pertencer a multiplos grupos
- Cada grupo tem prompts especificos
- Admins tem acesso a todos os grupos

---

## Protecoes Implementadas

### CORS

```python
# Origens permitidas via ALLOWED_ORIGINS
allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
allow_headers=["Authorization", "Content-Type", "X-Requested-With"]
allow_credentials=True
```

### Path Traversal

Todos os endpoints de arquivos estaticos usam `safe_serve_static()`:
- Valida se arquivo esta dentro do diretorio permitido
- Whitelist de extensoes permitidas
- Bloqueia sequencias `../`

### XXE (XML External Entity)

Parsing XML usa `safe_parse_xml()`:
- Verifica padroes maliciosos antes do parse
- Usa `defusedxml` quando disponivel
- Bloqueia ENTITY declarations, DTDs externos

### SQL Injection

- Todas as queries usam SQLAlchemy ORM
- Parametros sempre passados como bind variables
- Migrations usam ALTER TABLE seguro

---

## Credenciais e Secrets

### Rotacao de Secrets

| Secret | Frequencia | Como Rotacionar |
|--------|------------|-----------------|
| SECRET_KEY | Anual | Gerar nova, atualizar env, reiniciar app |
| ADMIN_PASSWORD | 90 dias | Trocar via UI ou direto no banco |
| API Keys (Gemini) | Quando comprometidas | Revogar no console, gerar nova |
| TJ_WS_PASS | Quando solicitado | Contato com TJ-MS |

### Nunca Commitar

Os seguintes arquivos NUNCA devem ser commitados:
- `.env` (credenciais reais)
- `*.pem`, `*.key` (certificados)
- `portal.db` (banco de dados)
- `settings.json` (configuracoes locais)

Verifique `.gitignore` antes de commits.

---

## Monitoramento

### Logs de Seguranca

Eventos logados:
- Tentativas de login (sucesso/falha)
- Alteracoes de senha
- Criacao/exclusao de usuarios
- Acesso a endpoints admin
- Erros de autenticacao

### Alertas Recomendados

Configurar alertas para:
- 5+ falhas de login do mesmo IP em 5 minutos
- Acesso a /test-tjms por usuario nao-admin
- Erros 403/401 em sequencia
- Picos de uso de CPU/memoria

---

## Vulnerabilidades Conhecidas

### Corrigidas

| Data | CVE/ID | Severidade | Descricao | Commit |
|------|--------|------------|-----------|--------|
| 2026-01-11 | - | Alta | CORS wildcard | e128d35 |
| 2026-01-11 | - | Alta | Path Traversal | e128d35 |
| 2026-01-11 | - | Media | XXE em XML | e128d35 |
| 2026-01-11 | - | Media | Debug sem auth | e128d35 |

### Pendentes (Baixo Risco)

- Rate limiting ausente (mitigado por infra)
- CSRF tokens (mitigado por SameSite cookies)
- Info disclosure em erros (baixo impacto)

---

## Dependencias

### Verificacao de CVEs

```bash
# Instalar pip-audit
pip install pip-audit

# Verificar vulnerabilidades
pip-audit --requirement requirements.txt
```

### Dependencias de Seguranca

| Pacote | Versao | Uso |
|--------|--------|-----|
| python-jose | 3.3.0+ | JWT |
| bcrypt | 4.0.0+ | Hash de senhas |
| defusedxml | 0.7.1+ | Parsing XML seguro |

---

## Contato

- **Seguranca:** seguranca@pge.ms.gov.br
- **Suporte Tecnico:** lab@pge.ms.gov.br
- **Emergencias:** (67) XXXX-XXXX
