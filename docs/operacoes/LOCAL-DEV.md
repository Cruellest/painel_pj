# Desenvolvimento Local com PostgreSQL

Este documento descreve como configurar o ambiente de desenvolvimento local usando PostgreSQL no Railway.

**IMPORTANTE:** PostgreSQL e obrigatorio. O sistema nao suporta mais SQLite.

---

## Quick Start

```bash
# 1. Configure o .env (DATABASE_URL ja aponta para PostgreSQL dev)
# Verifique se o arquivo .env existe e tem DATABASE_URL correto

# 2. Crie as tabelas
python -m database.init_db

# 3. Inicie o servidor
uvicorn main:app --reload

# 4. (Opcional) Clone dados de producao para desenvolvimento
python scripts/db_clone_prod_to_local.py
```

---

## Configuracao

### Bancos de Dados

Temos **dois bancos** no Railway:

| Ambiente | Uso | URL |
|----------|-----|-----|
| **Desenvolvimento** | Testes locais | `centerbeam.proxy.rlwy.net:50662` |
| **Producao** | App em producao | `yamanote.proxy.rlwy.net:48085` |

### Arquivo .env

O `.env` local deve apontar para o banco de **desenvolvimento**:

```env
DATABASE_URL=postgresql://postgres:SENHA@centerbeam.proxy.rlwy.net:50662/railway
```

**NUNCA** aponte o `.env` local para producao, a menos que seja para fazer dump (leitura).

---

## Clonar Dados de Producao

Para testar com dados reais, clone o banco de producao para desenvolvimento:

```bash
python scripts/db_clone_prod_to_local.py
```

### Modos de Clone

```bash
# Clone completo (todos os dados)
python scripts/db_clone_prod_to_local.py

# Apenas schema (sem dados)
python scripts/db_clone_prod_to_local.py --schema

# Schema + tabelas essenciais (users, configs)
python scripts/db_clone_prod_to_local.py --minimal
```

### Requisitos

- `pg_dump` e `psql` instalados no PATH
- Windows: Instale o PostgreSQL (apenas client tools) ou use o instalador
- A URL de producao deve estar no `.env` (linha comentada com "PRODUCAO")

### Instalando PostgreSQL Client no Windows

1. Baixe o instalador: https://www.postgresql.org/download/windows/
2. Durante a instalacao, selecione apenas "Command Line Tools"
3. Adicione ao PATH: `C:\Program Files\PostgreSQL\17\bin`

---

## Validar Ambiente

Execute o script de validacao:

```bash
python scripts/db_validate_local.py
```

Checklist:
- [x] Arquivo .env configurado
- [x] Conexao PostgreSQL OK
- [x] Tabelas criadas
- [x] Usuario admin existe
- [x] Aplicacao importavel

---

## Comandos Uteis

### Aplicacao

```bash
# Iniciar servidor de desenvolvimento
uvicorn main:app --reload

# Rodar em porta diferente
uvicorn main:app --reload --port 8001

# Rodar migrations
python -m database.init_db

# Rodar testes
pytest
```

### Banco de Dados (via psql)

```bash
# Conectar ao banco de desenvolvimento
psql "postgresql://postgres:SENHA@centerbeam.proxy.rlwy.net:50662/railway"

# Listar tabelas
\dt

# Ver estrutura de uma tabela
\d users

# Sair
\q
```

---

## Troubleshooting

### Erro: "connection refused" ou timeout

- Verifique se a URL no `.env` esta correta
- Verifique sua conexao com a internet
- O Railway pode estar em manutencao (raro)

### Erro: "database does not exist"

Execute as migrations:
```bash
python -m database.init_db
```

### Erro: "pg_dump: command not found"

PostgreSQL client nao esta instalado ou nao esta no PATH.

**Windows:** Instale o PostgreSQL e adicione ao PATH:
```
C:\Program Files\PostgreSQL\17\bin
```

### Erro de encoding (emojis)

Isso e um problema de encoding do Windows, nao afeta a funcionalidade.
O banco e as tabelas sao criados corretamente.

---

## Estrutura de Arquivos

```
portal-pge/
├── .env                        # Variaveis de ambiente (nao commitado)
├── .env.example                # Template para novos devs
├── .env.local.example          # Template alternativo
├── scripts/
│   ├── db_clone_prod_to_local.py  # Clone producao -> desenvolvimento
│   ├── db_dump_prod.sh         # Dump producao (Bash)
│   ├── db_restore_local.sh     # Restore desenvolvimento (Bash)
│   └── db_validate_local.py    # Validacao do ambiente
├── dumps/                      # Dumps de banco (gitignored)
│   └── prod_dump_*.sql.gz
└── database/
    ├── connection.py           # Config SQLAlchemy
    └── init_db.py              # Migrations e seeds
```

---

## Seguranca

### Dados Sensiveis

Ao clonar producao, voce tera dados reais no banco de desenvolvimento. Cuide para:

- **NAO commitar dumps** (ja esta no .gitignore)
- **NAO expor .env** com credenciais
- **NAO compartilhar URLs** de banco publicamente

### Separacao de Ambientes

| Ambiente | Banco | Risco |
|----------|-------|-------|
| Local | Desenvolvimento | Baixo - pode apagar tudo |
| Producao | Producao | Alto - dados reais de usuarios |

**Regra de ouro:** Na duvida, trabalhe no banco de desenvolvimento.
