# Sistema: Assistencia Judiciaria

> Documentacao tecnica do modulo de consulta e relatorio de processos de assistencia judiciaria.

## A) Visao Geral

O sistema de Assistencia Judiciaria permite que procuradores consultem processos no TJ-MS e gerem relatorios automatizados com auxilio de IA. O objetivo e agilizar a analise de processos de cumprimento de sentenca e outros procedimentos relacionados a assistencia judiciaria gratuita.

**Usuarios**: Procuradores e servidores da PGE-MS
**Problema resolvido**: Automatizar a consulta e geracao de relatorios sobre processos de assistencia judiciaria

## B) Regras de Negocio

### B.1) Consulta de Processos

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Formato CNJ | O numero do processo deve seguir o padrao CNJ (20 digitos) | `sistemas/assistencia_judiciaria/router.py:194-210` |
| Classes de Cumprimento | Processos sao filtrados por classes especificas: 155, 156, 12231, 15430, 12078, 15215, 15160, 12246, 10980, 157, 15161, 10981, 229 | `config.py:143-146` |
| Cache de Consultas | Consultas podem ser cacheadas no banco para evitar chamadas repetidas ao TJ-MS | `sistemas/assistencia_judiciaria/models.py` |

### B.2) Geracao de Relatorio

| Regra | Descricao | Fonte no Codigo |
|-------|-----------|-----------------|
| Modelo de IA | Usa Google Gemini (default: gemini-3-flash-preview) para gerar relatorio | `sistemas/assistencia_judiciaria/core/logic.py:42-80` |
| Dados do Processo | Extrai polo ativo, polo passivo, movimentos e dados basicos do XML | `sistemas/assistencia_judiciaria/core/logic.py:82-150` |
| Formato Saida | Relatorio em texto estruturado, exportavel para DOCX/PDF | `sistemas/assistencia_judiciaria/core/document.py` |

### B.3) Tratamento de Excecoes

| Situacao | Comportamento | Fonte no Codigo |
|----------|---------------|-----------------|
| Processo nao encontrado | Retorna erro 404 com mensagem explicativa | `sistemas/assistencia_judiciaria/router.py` |
| TJ-MS indisponivel | Timeout de 30s, retorna erro 503 | `services/tjms_client.py` |
| Gemini indisponivel | Retorna erro 502, relatorio nao e gerado | `sistemas/assistencia_judiciaria/core/logic.py` |
| XML malformado | Log de erro, tenta parser tolerante | `sistemas/assistencia_judiciaria/core/logic.py` |

## C) Fluxo Funcional

```
[Usuario] Informa numero CNJ
    |
    v
[Router] POST /assistencia/api/consultar
    |
    v
[Logic] Consulta SOAP no TJ-MS via tjms_client
    |
    v
[XML Parser] Extrai dados basicos, partes e movimentos
    |
    v
[Gemini Service] Gera relatorio com IA
    |
    v
[Document] Formata saida (texto/DOCX/PDF)
    |
    v
[Banco] Persiste consulta em consultas_processos
    |
    v
[Response] Retorna relatorio ao usuario
```

## D) API/Rotas

### Endpoints Principais

| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/assistencia/api/settings` | Obter configuracoes do sistema |
| POST | `/assistencia/api/settings` | Atualizar configuracoes |
| GET | `/assistencia/api/test-tjms` | Testar conectividade com TJ-MS |
| POST | `/assistencia/api/consultar` | Consultar processo e gerar relatorio |
| GET | `/assistencia/api/historico` | Listar consultas anteriores |
| POST | `/assistencia/api/feedback` | Enviar feedback sobre relatorio |

### Payload de Consulta

```json
{
  "cnj": "0804330-09.2024.8.12.0017",
  "model": "google/gemini-3-flash-preview",
  "force": false
}
```

### Resposta de Consulta

```json
{
  "success": true,
  "dados_processo": {
    "numero": "0804330-09.2024.8.12.0017",
    "polo_ativo": [...],
    "polo_passivo": [...],
    "classe": "Cumprimento de Sentenca",
    "movimentos": [...]
  },
  "relatorio": "## Relatorio de Analise\n\n..."
}
```

## E) Dados e Persistencia

### Tabelas

| Tabela | Descricao |
|--------|-----------|
| `consultas_processos` | Historico de consultas e relatorios gerados |
| `feedbacks_analise` | Feedback dos usuarios sobre relatorios |

### Modelo `ConsultaProcesso`

| Campo | Tipo | Descricao |
|-------|------|-----------|
| id | Integer | PK auto-incremento |
| numero_processo | String | Numero CNJ |
| dados_xml | Text | XML cru do TJ-MS |
| dados_json | JSON | Dados parseados |
| relatorio | Text | Relatorio gerado |
| modelo_ia | String | Modelo usado na geracao |
| usuario_id | Integer | FK para users |
| created_at | DateTime | Data da consulta |

### O que NAO e persistido

- PDFs e documentos do processo (apenas referenciados)
- Dados sensiveis de partes (anonimizados no relatorio)

## F) Integracoes Externas

### TJ-MS (SOAP/MNI)

| Configuracao | Variavel de Ambiente | Descricao |
|--------------|---------------------|-----------|
| URL WSDL | `TJ_WSDL_URL` | Endpoint SOAP (via proxy Fly.io) |
| Usuario | `TJ_WS_USER` | Credencial MNI |
| Senha | `TJ_WS_PASS` | Credencial MNI |

### Google Gemini

| Configuracao | Variavel de Ambiente | Descricao |
|--------------|---------------------|-----------|
| API Key | `GEMINI_KEY` | Chave de acesso |
| Modelo | `GEMINI_MODEL` | Modelo default |

### Pontos Frageis

- Proxy TJ-MS (Fly.io) pode estar indisponivel
- Rate limiting do TJ-MS pode bloquear consultas em massa
- Gemini pode ter latencia alta em horarios de pico

## G) Operacao e Validacao

### Como Rodar

```bash
# Subir servidor com sistema ativo
uvicorn main:app --reload

# Acessar frontend
http://localhost:8000/assistencia
```

### Como Testar

```bash
# Testar endpoint de consulta
curl -X POST http://localhost:8000/assistencia/api/consultar \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"cnj": "0804330-09.2024.8.12.0017"}'

# Testar conectividade TJ-MS
curl http://localhost:8000/assistencia/api/test-tjms \
  -H "Authorization: Bearer TOKEN"
```

### Logs e Telemetria

- Logs de consulta: `logs/audit.log`
- Metricas de IA: tabela `consultas_processos` (tempo de geracao)

## H) Riscos e Dividas Tecnicas

### Riscos

| Risco | Impacto | Mitigacao Sugerida |
|-------|---------|-------------------|
| Dependencia de proxy TJ-MS | Alto - sistema inoperante se proxy cair | Implementar fallback para SOAP direto |
| Timeout em processos grandes | Medio - XML muito grande pode travar | Implementar paginacao de movimentos |
| Custo de Gemini | Baixo - consultas sao pontuais | Monitorar uso e cachear respostas |

### Dividas Tecnicas

| Item | Descricao | Prioridade |
|------|-----------|------------|
| Testes automatizados | Nao ha suite de testes para este sistema | P1 |
| Tratamento de erros | Mensagens de erro genericas em alguns casos | P2 |
| Cache de XML | XML do TJ-MS nao e cacheado adequadamente | P2 |
| Documentacao de API | OpenAPI incompleto para alguns endpoints | P3 |

## Arquivos Principais

| Arquivo | Descricao |
|---------|-----------|
| `sistemas/assistencia_judiciaria/router.py` | Endpoints FastAPI |
| `sistemas/assistencia_judiciaria/core/logic.py` | Logica de consulta e geracao |
| `sistemas/assistencia_judiciaria/core/document.py` | Exportacao DOCX/PDF |
| `sistemas/assistencia_judiciaria/models.py` | Modelos SQLAlchemy |
| `sistemas/assistencia_judiciaria/templates/` | Frontend SPA |
