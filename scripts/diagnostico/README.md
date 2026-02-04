# Scripts de Diagnóstico

Scripts utilitários para diagnóstico e correção do banco de dados em produção.

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

### fix_tipo_peca.py (Interativo)

Corrige registros com `tipo_peca` NULL ou inválido, inferindo o tipo a partir do conteúdo gerado.
**Requer confirmação** antes de salvar.

```bash
python scripts/diagnostico/fix_tipo_peca.py  # Local apenas (interativo)
```

### fix_tipo_peca_auto.py (Automático)

Versão automática que corrige sem pedir confirmação. **Use com cuidado!**

```bash
railway run python scripts/diagnostico/fix_tipo_peca_auto.py
```

## Observações

- **Não execute** scripts de diagnóstico sem o `railway run`, pois isso usará o banco local
- Scripts `fix_*` modificam dados - faça backup antes de executar em produção
