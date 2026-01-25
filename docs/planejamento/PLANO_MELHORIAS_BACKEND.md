# Plano de Melhorias do Backend

> Diagnostico arquitetural e roadmap de melhorias para o Portal PGE-MS.

## 1. Diagnostico Arquitetural

### 1.1 Pontos Fortes

| Aspecto | Avaliacao | Observacao |
|---------|-----------|------------|
| Estrutura de modulos | Bom | Separacao clara por sistema |
| API REST | Bom | FastAPI bem utilizado, OpenAPI automatico |
| Integracao TJ-MS | Adequado | Proxy funciona, mas fragil |
| Pipeline de IA | Bom | 3 agentes bem definidos |
| Modelo de dados | Solido | SQLAlchemy bem estruturado |

### 1.2 Pontos de Atencao

| Aspecto | Avaliacao | Problema |
|---------|-----------|----------|
| Testes | Insuficiente | Cobertura baixa, poucos testes E2E |
| Observabilidade | Basico | Logs nao estruturados, sem metricas |
| Tratamento de erros | Inconsistente | Mensagens genericas em alguns casos |
| Documentacao de codigo | Parcial | Docstrings incompletas |
| Cache | Ausente | Resumos re-processados a cada chamada |

## 2. Problemas de Clean Code

### 2.1 Naming

| Problema | Exemplo | Sugestao |
|----------|---------|----------|
| Nomes genericos | `services.py`, `utils.py` | `document_classifier_service.py` |
| Abreviacoes | `req`, `res`, `cfg` | `request`, `response`, `config` |
| Inconsistencia | `processar_xml` vs `processXml` | Padronizar snake_case |

### 2.2 Responsabilidades

| Problema | Localizacao | Sugestao |
|----------|-------------|----------|
| Routers com logica | `sistemas/*/router.py` | Mover logica para services |
| Services monoliticos | `gerador_pecas/services.py` | Separar por responsabilidade |
| Duplicacao de codigo | Validadores de CNJ em multiplos lugares | Criar utils/validators.py |

### 2.3 Complexidade

| Problema | Arquivo | Sugestao |
|----------|---------|----------|
| Funcoes longas | `orquestrador_agentes.py` | Extrair metodos menores |
| Aninhamento profundo | Varios | Usar early returns |
| Magica de strings | Codigos TJ-MS hardcoded | Criar enums/constants |

## 3. Seguranca

### 3.1 Autenticacao

| Item | Status | Acao |
|------|--------|------|
| JWT tokens | OK | - |
| Refresh tokens | OK | - |
| Rate limiting | FALTA | Implementar |
| Brute force protection | FALTA | Implementar |

### 3.2 Secrets

| Item | Status | Acao |
|------|--------|------|
| Env vars para credenciais | OK | - |
| .env no .gitignore | OK | - |
| Rotacao de secrets | FALTA | Documentar processo |
| Audit de acesso | PARCIAL | Melhorar logs |

### 3.3 Validacao

| Item | Status | Acao |
|------|--------|------|
| Input validation (Pydantic) | OK | - |
| SQL injection | OK (SQLAlchemy ORM) | - |
| XSS | PARCIAL | Revisar templates |
| CORS | OK | - |

## 4. Performance e Confiabilidade

### 4.1 Timeouts

| Integracao | Atual | Recomendado | Acao |
|------------|-------|-------------|------|
| TJ-MS SOAP | 30s | 30s (OK) | - |
| Gemini API | Indefinido | 60s | Implementar |
| Downloads PDF | Indefinido | 30s | Implementar |

### 4.2 Retries

| Integracao | Atual | Recomendado | Acao |
|------------|-------|-------------|------|
| TJ-MS SOAP | Nenhum | 3 com backoff | Implementar |
| Gemini API | Nenhum | 2 com backoff | Implementar |
| Storage | Nenhum | 3 | Implementar |

### 4.3 Circuit Breaker

| Integracao | Status | Acao |
|------------|--------|------|
| TJ-MS | FALTA | Implementar |
| Gemini | FALTA | Implementar |

### 4.4 Jobs e Background Tasks

| Problema | Impacto | Acao |
|----------|---------|------|
| Jobs travados (BERT) | Medio | Implementar watchdog |
| Sem heartbeat timeout | Medio | Definir timeout de heartbeat |
| Sem cancelamento | Baixo | Implementar endpoint de cancel |

## 5. Observabilidade

### 5.1 Logs

| Item | Status | Acao |
|------|--------|------|
| Logs estruturados (JSON) | FALTA | Implementar com structlog |
| Request ID | FALTA | Adicionar middleware |
| Log rotation | OK (Railway) | - |
| Sensitive data redaction | PARCIAL | Revisar |

### 5.2 Metricas

| Metrica | Status | Acao |
|---------|--------|------|
| Tempo de resposta | FALTA | Implementar |
| Taxa de erro | FALTA | Implementar |
| Uso de IA (tokens) | FALTA | Implementar |
| Filas (BERT) | FALTA | Implementar |

### 5.3 Alertas

| Alerta | Status | Acao |
|--------|--------|------|
| Erro 5xx | FALTA | Implementar |
| TJ-MS indisponivel | FALTA | Implementar |
| Job travado | FALTA | Implementar |

## 6. Testes

### 6.1 Situacao Atual

| Tipo | Cobertura | Alvo |
|------|-----------|------|
| Unitarios | ~20% | 60% |
| Integracao | ~5% | 30% |
| E2E | ~0% | 10% |

### 6.2 Estrategia Proposta

1. **Fase 1**: Testes para servicos criticos (TJ-MS, Gemini)
2. **Fase 2**: Testes para rotas principais
3. **Fase 3**: Testes E2E com playwright/selenium

### 6.3 Mocks Necessarios

| Integracao | Mock | Prioridade |
|------------|------|------------|
| TJ-MS SOAP | Responses XML gravadas | P0 |
| Gemini API | Responses JSON gravadas | P0 |
| Storage | In-memory | P1 |

## 7. Deploy e Ambiente

### 7.1 Railway (Producao)

| Item | Status | Acao |
|------|--------|------|
| Auto-deploy (main) | OK | - |
| Health checks | PARCIAL | Melhorar endpoint |
| Zero-downtime | OK (Railway) | - |
| Rollback | MANUAL | Documentar processo |

### 7.2 Migrations

| Item | Status | Acao |
|------|--------|------|
| Alembic setup | FALTA | Implementar |
| Migrations automaticas | FALTA | init_db.py e ad-hoc |
| Rollback de migrations | FALTA | Implementar |

### 7.3 Config Management

| Item | Status | Acao |
|------|--------|------|
| Env-based config | OK | - |
| Feature flags | FALTA | Considerar |
| Config validation | PARCIAL | Melhorar |

## 8. Plano Incremental

### Fase 1: Fundacao (P0) - Critico

| Item | Descricao | Esforco |
|------|-----------|---------|
| Timeouts globais | Adicionar timeout a todas integracoes | Pequeno |
| Retry com backoff | Implementar para TJ-MS e Gemini | Pequeno |
| Logs estruturados | Migrar para structlog | Medio |
| Request ID | Middleware de correlacao | Pequeno |
| Testes TJ-MS | Mocks e testes unitarios | Medio |

### Fase 2: Robustez (P1) - Alto

| Item | Descricao | Esforco |
|------|-----------|---------|
| Circuit breaker | TJ-MS e Gemini | Medio |
| Rate limiting | Por usuario/endpoint | Medio |
| Metricas basicas | Prometheus/custom | Medio |
| Health check melhorado | Checar dependencias | Pequeno |
| Testes de rotas | Principais endpoints | Medio |

### Fase 3: Evolucao (P2) - Medio

| Item | Descricao | Esforco |
|------|-----------|---------|
| Alembic migrations | Setup e migracao inicial | Medio |
| Cache de resumos | Redis ou in-memory | Medio |
| Watchdog BERT | Jobs travados | Medio |
| Feature flags | Sistema simples | Pequeno |
| Testes E2E | Fluxos criticos | Grande |

### Fase 4: Maturidade (P3) - Baixo

| Item | Descricao | Esforco |
|------|-----------|---------|
| Alertas automaticos | Integrar com Slack/email | Medio |
| Dashboard de metricas | Grafana/custom | Grande |
| Load testing | k6 ou locust | Medio |
| Documentacao OpenAPI completa | Schemas detalhados | Medio |

## 9. Backlog Priorizado

### P0 - Critico (Fazer Primeiro)

| ID | Item | Tamanho | Justificativa |
|----|------|---------|---------------|
| P0-01 | Timeouts em todas integracoes | Pequeno | Evita requests eternos |
| P0-02 | Retry com backoff TJ-MS | Pequeno | Resiliencia |
| P0-03 | Logs estruturados | Medio | Debugabilidade |
| P0-04 | Testes unitarios servicos core | Medio | Confianca em mudancas |

### P1 - Alto (Fazer Logo)

| ID | Item | Tamanho | Justificativa |
|----|------|---------|---------------|
| P1-01 | Circuit breaker | Medio | Resiliencia em cascata |
| P1-02 | Rate limiting | Medio | Seguranca e custo |
| P1-03 | Metricas de request | Medio | Visibilidade |
| P1-04 | Testes de integracao | Medio | Cobertura |

### P2 - Medio (Planejar)

| ID | Item | Tamanho | Justificativa |
|----|------|---------|---------------|
| P2-01 | Alembic migrations | Medio | Evoluibilidade |
| P2-02 | Cache de resumos | Medio | Performance e custo |
| P2-03 | Watchdog BERT | Medio | Confiabilidade |
| P2-04 | Health checks completos | Pequeno | Monitoramento |

### P3 - Baixo (Backlog)

| ID | Item | Tamanho | Justificativa |
|----|------|---------|---------------|
| P3-01 | Dashboard de metricas | Grande | Visibilidade |
| P3-02 | Alertas automaticos | Medio | Proatividade |
| P3-03 | Load testing | Medio | Capacidade |
| P3-04 | Feature flags | Pequeno | Flexibilidade |

## 10. Criterios de Aceite

### Para considerar um item FEITO:

1. **Codigo implementado** e funcionando
2. **Testes** cobrindo o novo codigo (quando aplicavel)
3. **Documentacao** atualizada (se necessario)
4. **Code review** aprovado
5. **Deploy** em producao sem erros

### Para considerar uma FASE concluida:

1. Todos os itens P0 da fase concluidos
2. Metricas basicas funcionando (se aplicavel)
3. Documentacao de operacao atualizada
4. Treinamento da equipe (se necessario)
