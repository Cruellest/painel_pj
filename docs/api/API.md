# API

Este arquivo resume endpoints principais e exemplos de payloads reais.
Se um endpoint nao estiver listado aqui, consulte o arquivo `router.py`
correspondente ou a documentacao OpenAPI em `/docs`.

## Autenticacao e headers

- Autenticacao por JWT via cookie `access_token` (HttpOnly) ou header `Authorization: Bearer <token>`.
- Alguns downloads aceitam `?token=<jwt>` (ex.: arquivos).
- JSON por padrao: `Content-Type: application/json`.
- SSE (stream): `text/event-stream`.
- Uploads: `multipart/form-data`.

## Auth

Base: `/auth`

- `POST /auth/login` (form-urlencoded)
- `GET /auth/me`
- `POST /auth/change-password`
- `POST /auth/logout`
- `GET /auth/password-requirements`

Exemplo (login):

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=senha"
```

Exemplo (troca de senha):

```json
{
  "current_password": "senha_atual",
  "new_password": "NovaSenhaForte123!"
}
```

## Users (admin)

Base: `/users`

- `GET /users`
- `POST /users`
- `GET /users/{user_id}`
- `PUT /users/{user_id}`
- `DELETE /users/{user_id}`
- `POST /users/{user_id}/reset-password`

Exemplo (criar usuario):

```json
{
  "username": "joao",
  "full_name": "Joao da Silva",
  "email": "joao@pge.ms.gov.br",
  "role": "user",
  "sistemas_permitidos": ["gerador_pecas", "pedido_calculo"],
  "permissoes_especiais": ["edit_prompts"],
  "default_group_id": 1,
  "allowed_group_ids": [1, 2]
}
```

## Admin (prompts/config)

Base: `/admin`

- `GET /admin/prompts`
- `GET /admin/prompts/{prompt_id}`
- `POST /admin/prompts`
- `PUT /admin/prompts/{prompt_id}`
- `DELETE /admin/prompts/{prompt_id}`
- `GET /admin/config-ia`
- `POST /admin/config-ia/upsert`
- `PUT /admin/config-ia/{config_id}`
- `GET /admin/modelos-ia`
- `PUT /admin/modelos-ia/{sistema}`
- `GET /admin/api-key-status`
- `PUT /admin/api-key`
- `GET /admin/feedbacks/dashboard`
- `GET /admin/feedbacks/lista`
- `GET /admin/feedbacks/consulta/{consulta_id}`
- `GET /admin/feedbacks/exportar`

## Prompts modulares (admin)

Base: `/admin/api/prompts-modulos`

- `GET /admin/api/prompts-modulos`
- `POST /admin/api/prompts-modulos`
- `PUT /admin/api/prompts-modulos/{modulo_id}`
- `DELETE /admin/api/prompts-modulos/{modulo_id}`
- `GET /admin/api/prompts-modulos/{modulo_id}/historico`
- `POST /admin/api/prompts-modulos/{modulo_id}/restaurar/{versao}`
- `GET /admin/api/prompts-modulos/grupos`
- `POST /admin/api/prompts-modulos/grupos`
- `GET /admin/api/prompts-modulos/grupos/{group_id}/subgrupos`
- `POST /admin/api/prompts-modulos/grupos/{group_id}/subgrupos`

Exemplo (criar modulo de conteudo):

```json
{
  "tipo": "conteudo",
  "nome": "medicamento_alto_custo",
  "titulo": "Medicamento de alto custo",
  "categoria": "Merito",
  "conteudo": "Texto do prompt em Markdown...",
  "condicao_ativacao": "Ativar quando medicamento nao esta no SUS",
  "modo_ativacao": "deterministic",
  "regra_deterministica": {
    "type": "condition",
    "variable": "nao_incorporado_sus",
    "operator": "equals",
    "value": true
  },
  "group_id": 1,
  "subgroup_id": 2,
  "subcategoria_ids": [3]
}
```

## Gerador de pecas

Base: `/gerador-pecas/api`

- `GET /gerador-pecas/api/tipos-peca`
- `GET /gerador-pecas/api/grupos-disponiveis`
- `GET /gerador-pecas/api/grupos/{group_id}/subgrupos`
- `POST /gerador-pecas/api/processar`
- `POST /gerador-pecas/api/processar-stream` (SSE)
- `POST /gerador-pecas/api/processar-pdfs-stream` (multipart + SSE)
- `POST /gerador-pecas/api/editar-minuta`
- `POST /gerador-pecas/api/exportar-docx`
- `GET /gerador-pecas/api/download/{filename}`
- `GET /gerador-pecas/api/historico`
- `GET /gerador-pecas/api/historico/{geracao_id}`
- `DELETE /gerador-pecas/api/historico/{geracao_id}`
- `POST /gerador-pecas/api/feedback`

Exemplo (processar por CNJ):

```json
{
  "numero_cnj": "0804330-09.2024.8.12.0017",
  "tipo_peca": "contestacao",
  "observacao_usuario": "Foco em tese X",
  "group_id": 1,
  "subcategoria_ids": [3, 4]
}
```

Exemplo (editar minuta via chat):

```json
{
  "minuta_atual": "# Texto atual...",
  "mensagem": "Ajuste a fundamentacao para incluir jurisprudencia local",
  "historico": []
}
```

### Gerador de pecas (admin)

Base: `/admin/api/gerador-pecas-admin`

- `GET /admin/api/gerador-pecas-admin/geracoes`
- `GET /admin/api/gerador-pecas-admin/geracoes/{geracao_id}`
- `GET /admin/api/gerador-pecas-admin/geracoes/{geracao_id}/prompt`
- `GET /admin/api/gerador-pecas-admin/geracoes/{geracao_id}/versoes`

## Categorias JSON (admin)

Base: `/admin/api/categorias-resumo-json`

- `GET /admin/api/categorias-resumo-json`
- `POST /admin/api/categorias-resumo-json`
- `PUT /admin/api/categorias-resumo-json/{categoria_id}`
- `DELETE /admin/api/categorias-resumo-json/{categoria_id}`
- `GET /admin/api/categorias-resumo-json/{categoria_id}/historico`
- `POST /admin/api/categorias-resumo-json/testar-formato`

Exemplo (criar categoria):

```json
{
  "nome": "peticoes",
  "titulo": "Peticoes",
  "descricao": "Documentos iniciais",
  "codigos_documento": [500, 510, 9500],
  "formato_json": "{\n  \"tipo_documento\": \"string\"\n}",
  "instrucoes_extracao": "Preencha todos os campos",
  "namespace_prefix": "peticao",
  "tipos_logicos_peca": ["peticao inicial"],
  "fonte_verdade_tipo": "peticao inicial",
  "requer_classificacao": true
}
```

## Extracao (admin)

Base: `/admin/api/extraction`

- `GET /admin/api/extraction/categorias/{categoria_id}/perguntas`
- `POST /admin/api/extraction/perguntas`
- `POST /admin/api/extraction/perguntas/lote`
- `GET /admin/api/extraction/variaveis`
- `POST /admin/api/extraction/variaveis`
- `POST /admin/api/extraction/regras-deterministicas/gerar`
- `POST /admin/api/extraction/regras-deterministicas/validar`
- `POST /admin/api/extraction/regras-deterministicas/avaliar`

Exemplo (criar pergunta):

```json
{
  "categoria_id": 1,
  "pergunta": "O medicamento esta incorporado ao SUS?",
  "tipo_sugerido": "boolean",
  "nome_variavel_sugerido": "medicamento_incorporado_sus"
}
```

Exemplo (gerar regra deterministica):

```json
{
  "condicao_texto": "Ativar quando medicamento nao estiver incorporado ao SUS",
  "contexto": "tipo_peca=contestacao; group_id=1"
}
```

## Config de pecas (admin)

Base: `/api/gerador-pecas/config`

- `GET /api/gerador-pecas/config/categorias`
- `POST /api/gerador-pecas/config/categorias`
- `GET /api/gerador-pecas/config/tipos-peca`
- `POST /api/gerador-pecas/config/tipos-peca`
- `PUT /api/gerador-pecas/config/tipos-peca/{tipo_id}/categorias`
- `POST /api/gerador-pecas/config/seed`

## Pedido de calculo

Base: `/pedido-calculo/api`

- `POST /pedido-calculo/api/processar-xml`
- `POST /pedido-calculo/api/baixar-documentos`
- `POST /pedido-calculo/api/extrair-informacoes`
- `POST /pedido-calculo/api/gerar-pedido`
- `POST /pedido-calculo/api/processar-stream` (SSE)
- `POST /pedido-calculo/api/exportar-docx`
- `GET /pedido-calculo/api/download/{filename}`
- `GET /pedido-calculo/api/historico`
- `GET /pedido-calculo/api/historico/{id}`
- `POST /pedido-calculo/api/editar-pedido`
- `POST /pedido-calculo/api/feedback`

Exemplo (processar stream):

```json
{
  "numero_cnj": "0857327-80.2025.8.12.0001",
  "sobrescrever_existente": false
}
```

### Pedido de calculo (admin)

Base: `/pedido-calculo-admin`

- `GET /pedido-calculo-admin/geracoes`
- `GET /pedido-calculo-admin/geracoes/{geracao_id}`
- `GET /pedido-calculo-admin/geracoes/{geracao_id}/logs`
- `GET /pedido-calculo-admin/logs-recentes`

## Prestacao de contas

Base: `/prestacao-contas/api`

- `POST /prestacao-contas/api/analisar-stream` (SSE)
- `POST /prestacao-contas/api/responder-duvida`
- `POST /prestacao-contas/api/feedback`
- `POST /prestacao-contas/api/exportar-parecer`
- `GET /prestacao-contas/api/historico`
- `GET /prestacao-contas/api/historico/{geracao_id}`

Exemplo (analisar stream):

```json
{
  "numero_cnj": "0804330-09.2024.8.12.0017",
  "sobrescrever_existente": false
}
```

### Prestacao de contas (admin)

Base: `/admin/api/prestacao-admin`

- `GET /admin/api/prestacao-admin/geracoes`
- `GET /admin/api/prestacao-admin/geracoes/{geracao_id}`
- `GET /admin/api/prestacao-admin/logs/{geracao_id}`

## Matriculas confrontantes

Base: `/matriculas/api`

- `GET /matriculas/api/files`
- `POST /matriculas/api/files/upload` (multipart)
- `POST /matriculas/api/analisar/{file_id}`
- `POST /matriculas/api/analisar-lote`
- `GET /matriculas/api/resultado/{file_id}`
- `POST /matriculas/api/feedback`

Exemplo (analise em lote):

```json
{
  "file_ids": ["abc123", "def456"],
  "nome_grupo": "Lote janeiro",
  "matricula_principal": "12345"
}
```

## Assistencia judiciaria

Base: `/assistencia/api`

- `GET /assistencia/api/settings`
- `POST /assistencia/api/settings`
- `GET /assistencia/api/test-tjms`
- `POST /assistencia/api/consultar`
- `GET /assistencia/api/historico`
- `POST /assistencia/api/feedback`

Exemplo (consultar):

```json
{
  "cnj": "0804330-09.2024.8.12.0017",
  "model": "google/gemini-3-flash-preview",
  "force": false
}
```

## Erros comuns

- 401: token ausente/invalido
- 403: sem permissao (admin ou sistema)
- 404: recurso nao encontrado
- 422: validacao de payload
- 429: rate limit
- 500: erro interno (detalhes reduzidos em producao)
