# Checklist de Release para Multiplas Equipes

> Guia padronizado para desenvolvimento, teste e deploy no Portal PGE-MS.

## 1. Setup de Ambiente Local

### 1.1 Pre-requisitos

- [ ] Python 3.10+ instalado
- [ ] PostgreSQL 15+ instalado e rodando
- [ ] Git configurado
- [ ] Node.js 18+ (para frontend)
- [ ] Editor com suporte a Python (VS Code recomendado)

### 1.2 Clone e Configuracao

```bash
# Clone do repositorio
git clone <repo-url>
cd portal-pge

# Criar ambiente virtual
python -m venv venv

# Ativar ambiente
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 1.3 Variaveis de Ambiente

```bash
# Copiar template
cp .env.example .env

# Editar .env com suas credenciais:
# - DATABASE_URL
# - SECRET_KEY
# - GEMINI_KEY
# - TJ_WS_USER / TJ_WS_PASS
# - TJMS_PROXY_URL
```

### 1.4 Banco de Dados

```bash
# Criar tabelas
python -c "from database.init_db import init_db; init_db()"

# Verificar conexao
python -c "from database.connection import engine; print(engine.url)"
```

### 1.5 Executar Servidor

```bash
# Desenvolvimento (com reload)
uvicorn main:app --reload

# Acessar:
# http://localhost:8000 (app)
# http://localhost:8000/docs (OpenAPI)
```

## 2. Executando Testes

### 2.1 Todos os Testes

```bash
# Rodar suite completa
pytest

# Com cobertura
pytest --cov=. --cov-report=html

# Apenas testes rapidos (sem integracao)
pytest -m "not integration"
```

### 2.2 Testes por Modulo

```bash
# Testes do gerador de pecas
pytest tests/test_gerador_pecas.py -v

# Testes de regras deterministicas
pytest tests/test_services_deterministic.py -v

# Testes de autenticacao
pytest tests/test_auth.py -v
```

### 2.3 Verificacao de Lint

```bash
# Verificar estilo (opcional, mas recomendado)
flake8 .

# Verificar tipos (opcional)
mypy .
```

## 3. Padrao de Branches e PRs

### 3.1 Nomenclatura de Branches

| Tipo | Prefixo | Exemplo |
|------|---------|---------|
| Nova feature | `feature/` | `feature/novo-relatorio` |
| Bug fix | `fix/` | `fix/timeout-tjms` |
| Refatoracao | `refactor/` | `refactor/services-extraction` |
| Documentacao | `docs/` | `docs/atualizar-readme` |
| Hotfix producao | `hotfix/` | `hotfix/corrigir-auth` |

### 3.2 Commits Convencionais

```bash
# Formato
<tipo>: <descricao>

# Tipos
feat:     Nova funcionalidade
fix:      Correcao de bug
docs:     Apenas documentacao
style:    Formatacao, ponto-virgula, etc
refactor: Refatoracao sem mudar comportamento
test:     Adicionar ou corrigir testes
chore:    Tarefas de build, configs, etc

# Exemplos
feat: adicionar endpoint de exportacao PDF
fix: corrigir timeout no download de documentos
docs: atualizar README com instrucoes de setup
```

### 3.3 Checklist de PR

Antes de abrir PR, verificar:

- [ ] Branch atualizada com main (`git pull origin main`)
- [ ] Testes passando localmente (`pytest`)
- [ ] Codigo segue padrao do projeto
- [ ] Documentacao atualizada (se aplicavel)
- [ ] Sem secrets/credenciais no codigo
- [ ] Commit messages seguem padrao

### 3.4 Template de PR

```markdown
## Descricao
[Descreva o que foi feito]

## Tipo de mudanca
- [ ] Bug fix
- [ ] Nova feature
- [ ] Breaking change
- [ ] Documentacao

## Como testar
1. [Passos para testar]

## Checklist
- [ ] Testes adicionados/atualizados
- [ ] Documentacao atualizada
- [ ] Sem breaking changes (ou documentados)
```

## 4. Guidelines de Seguranca

### 4.1 Nunca Comitar

- [ ] Credenciais/senhas
- [ ] API keys
- [ ] Arquivos .env
- [ ] Dados de producao
- [ ] Logs com dados sensiveis

### 4.2 Boas Praticas

- [ ] Usar variaveis de ambiente para secrets
- [ ] Validar inputs do usuario (Pydantic)
- [ ] Nao logar dados sensiveis (CPF, senhas)
- [ ] Usar HTTPS para todas integracoes
- [ ] Sanitizar queries SQL (usar ORM)

### 4.3 Revisao de Seguranca

Antes de merge, verificar:

- [ ] Nao ha SQL injection
- [ ] Inputs validados
- [ ] Autenticacao necessaria em rotas protegidas
- [ ] Nao expoe dados sensiveis em logs/erros

## 5. Como Debugar

### 5.1 Logs Locais

```bash
# Ver logs em tempo real
uvicorn main:app --reload --log-level debug

# Logs do TJ-MS
grep "TJ-MS" logs/*.log

# Logs de erro
grep "ERROR" logs/*.log
```

### 5.2 Debugger VS Code

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["main:app", "--reload"],
      "jinja": true
    }
  ]
}
```

### 5.3 Testar Endpoints

```bash
# Usando curl
curl -X GET http://localhost:8000/health

# Com autenticacao
curl -X GET http://localhost:8000/api/user \
  -H "Authorization: Bearer TOKEN"

# POST com JSON
curl -X POST http://localhost:8000/api/endpoint \
  -H "Content-Type: application/json" \
  -d '{"campo": "valor"}'
```

### 5.4 Testar TJ-MS

```bash
# Testar conectividade do proxy
curl -X POST https://tjms-proxy.fly.dev/health

# Ver logs de integracao
grep "tjms_client" logs/*.log
```

## 6. Padrao de Logs

### 6.1 Niveis de Log

| Nivel | Quando Usar |
|-------|-------------|
| DEBUG | Detalhes para desenvolvimento |
| INFO | Eventos normais de operacao |
| WARNING | Situacoes anormais mas nao erros |
| ERROR | Erros que afetam funcionalidade |
| CRITICAL | Erros graves que param o sistema |

### 6.2 Formato de Log

```python
# Bom - contexto util
logger.info(f"Processando CNJ={numero_cnj} user_id={user_id}")

# Ruim - sem contexto
logger.info("Processando...")

# Bom - erro com stack trace
logger.error(f"Erro ao baixar documento: {e}", exc_info=True)

# Ruim - erro sem detalhes
logger.error("Erro!")
```

### 6.3 O que NAO Logar

- CPF, RG, documentos pessoais
- Senhas, tokens, API keys
- Conteudo completo de documentos
- Dados de saude/financeiros

## 7. Deploy

### 7.1 Fluxo de Deploy

```
[Desenvolvedor] → [Feature Branch] → [PR] → [Code Review] → [Merge main] → [Auto-deploy Railway]
```

### 7.2 Ambientes

| Ambiente | Branch | URL |
|----------|--------|-----|
| Desenvolvimento | local | http://localhost:8000 |
| Producao | main | https://portal-pge.up.railway.app |

### 7.3 Checklist Pre-Deploy

- [ ] Testes passando em CI
- [ ] Code review aprovado
- [ ] Migrations testadas localmente
- [ ] Documentacao atualizada
- [ ] Sem breaking changes (ou comunicados)

### 7.4 Rollback

```bash
# Em caso de problema, reverter no Railway:
# 1. Acessar dashboard Railway
# 2. Ir em Deployments
# 3. Clicar em deploy anterior
# 4. "Redeploy"

# Ou via git:
git revert HEAD
git push origin main
```

## 8. Contatos e Suporte

### 8.1 Canais

| Assunto | Canal |
|---------|-------|
| Duvidas de codigo | Slack #pge-dev |
| Bugs em producao | Jira + Slack #pge-alerts |
| Seguranca | Email: seguranca@pge.ms.gov.br |

### 8.2 Responsaveis

| Area | Responsavel |
|------|-------------|
| Backend | Equipe LAB |
| Infra/Deploy | Equipe Infra |
| Integracao TJ-MS | Equipe LAB |

## 9. Recursos Uteis

### 9.1 Documentacao do Projeto

- `CLAUDE.md` - Regras operacionais
- `docs/README.md` - Indice de documentacao
- `docs/sistemas/*.md` - Documentacao por sistema
- `docs/ARCHITECTURE.md` - Detalhes tecnicos

### 9.2 Ferramentas

| Ferramenta | Uso |
|------------|-----|
| Railway | Deploy/hosting |
| PostgreSQL | Banco de dados |
| Gemini | LLM para IA |
| Fly.io | Proxy TJ-MS |

### 9.3 Links Externos

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy Docs](https://docs.sqlalchemy.org/)
- [Pydantic Docs](https://docs.pydantic.dev/)
- [Google AI Docs](https://ai.google.dev/docs)
