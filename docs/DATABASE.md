# Banco de dados

## Visao geral

- ORM: SQLAlchemy 2.0 (`database/connection.py`).
- Dev: SQLite (WAL habilitado).
- Producao: PostgreSQL.
- Migrations manuais: `database/init_db.py` (executadas no startup).
- Script util: `run_migration.py`.

## Tabelas por dominio

### Autenticacao e usuarios

- `users`
  - Campos-chave: `username`, `hashed_password`, `role`, `is_active`.
  - Permissoes: `sistemas_permitidos` e `permissoes_especiais` (JSON).
  - Grupos de prompts: `default_group_id`.

- `user_prompt_groups`
  - Relacao N:N entre `users` e `prompt_groups`.

### Admin e prompts

- `prompt_configs`
  - Prompts legados por sistema/tipo.

- `configuracoes_ia`
  - Configs por sistema (modelos, temperaturas, chaves).

- `prompt_modulos`
  - Modulos de prompt (base, peca, conteudo) com `modo_ativacao`.

- `prompt_modulos_historico`
  - Historico de versoes de `prompt_modulos`.

- `prompt_modulo_tipo_peca`
  - Vinculo de modulos de conteudo a tipos de peca.

- `prompt_groups` / `prompt_subgroups`
  - Agrupamento de prompts modulares.

- `prompt_subcategorias`
  - Subcategorias adicionais para filtros de prompts.

- `categoria_ordem`
  - Ordem de exibicao de categorias de modulos no texto.

- `prompt_modulo_subcategorias`
  - Relacao N:N entre `prompt_modulos` e `prompt_subcategorias`.

### Gerador de pecas

- `geracoes_pecas`
  - Processo, resumo consolidado, prompt enviado, conteudo gerado.

- `versoes_pecas`
  - Versionamento do texto gerado.

- `feedbacks_pecas`
  - Feedback do usuario sobre a peca.

- `categorias_resumo_json`
  - Categorias e formatos de extracao JSON.

- `categorias_resumo_json_historico`
  - Historico de formatos JSON.

- `extraction_questions`
  - Perguntas em linguagem natural.

- `extraction_models`
  - Schema JSON (manual/gerado por IA).

- `extraction_variables`
  - Variaveis normalizadas.

- `prompt_variable_usage`
  - Uso de variaveis em prompts.

- `prompt_activation_logs`
  - Log de ativacao de prompts (LLM/deterministico).

- `categorias_documento`
  - Categorias de documento (legado do gerador de pecas).

- `tipos_peca`
  - Tipos de pecas juridicas.

- `tipo_peca_categorias`
  - Relacao N:N entre `tipos_peca` e `categorias_documento`.

### Pedido de calculo

- `geracoes_pedido_calculo`
  - Resultado e metadados da geracao.

- `logs_chamada_ia_pedido_calculo`
  - Logs de chamadas de IA por etapa.

- `feedbacks_pedido_calculo`
  - Feedback do usuario.

### Prestacao de contas

- `geracoes_prestacao_contas`
  - Dados coletados, parecer e status.

- `logs_chamada_ia_prestacao`
  - Logs de IA.

- `feedbacks_prestacao_contas`
  - Feedback do usuario.

### Matriculas confrontantes

- `arquivos_upload`
  - Controle de uploads por usuario.

- `grupos_analise`
  - Agrupamento de analises em lote.

- `analises`
  - Resultado estruturado e metadados.

- `feedbacks_matricula`
  - Feedback do usuario.

- `registros`
  - Registros manuais.

- `logs_sistema`
  - Logs do modulo.

### Assistencia judiciaria

- `consultas_processos`
  - Historico de consultas e relatorios.

- `feedbacks_analise`
  - Feedback do usuario.

## Relacionamentos chave

- `geracoes_pecas.usuario_id -> users.id`.
- `feedbacks_pecas.geracao_id -> geracoes_pecas.id`.
- `versoes_pecas.geracao_id -> geracoes_pecas.id`.
- `prompt_modulos.group_id -> prompt_groups.id`.
- `prompt_modulos.subgroup_id -> prompt_subgroups.id`.
- `extraction_variables.categoria_id -> categorias_resumo_json.id`.
- `extraction_questions.categoria_id -> categorias_resumo_json.id`.
- `geracoes_pedido_calculo.usuario_id -> users.id`.
- `geracoes_prestacao_contas.usuario_id -> users.id`.

## Migrations e seeds

- Migrations e seeds ficam em `database/init_db.py`.
- O startup do FastAPI executa `init_database()` (cria tabelas, migra e semeia).
- Script manual: `python run_migration.py`.

## Reset do banco local (SQLite)

```bash
# CUIDADO: apaga dados
rm portal.db
# Reinicie a app para recriar tabelas
```

## Pontos nao inferidos com seguranca

- Nao ha migrations autom?ticas (Alembic) no repositorio.
