# Scripts de Diagnóstico

Scripts utilitários para diagnóstico e verificação do banco de dados em produção.

## Uso

Estes scripts devem ser executados com `railway run` para acessar o banco de produção:

```bash
railway run python scripts/diagnostico/<nome_do_script>.py
```

## Scripts Disponíveis

### check_tipo_peca.py

Verificação básica de registros com `tipo_peca` NULL na tabela de gerações de peças.

```bash
railway run python scripts/diagnostico/check_tipo_peca.py
```

### check_tipo_peca_detalhado.py

Diagnóstico detalhado que mostra:
- Contagem de valores NULL vs string "null" vs valores preenchidos
- Todos os valores distintos de `tipo_peca` no banco
- Últimas 10 gerações para análise de padrão

```bash
railway run python scripts/diagnostico/check_tipo_peca_detalhado.py
```

## Observações

- **Não execute** estes scripts sem o `railway run`, pois isso usará o banco local ao invés de produção
- Os scripts são apenas de leitura (SELECT), não modificam dados
