# Portal PGE-MS

Portal unificado da Procuradoria-Geral do Estado de Mato Grosso do Sul.

## Sistemas Integrados

- **Assistência Judiciária**: Consulta de processos judiciais no TJ-MS com análise automática por IA
- **Matrículas Confrontantes**: Análise documental de matrículas imobiliárias com IA visual

## Requisitos

- Python 3.10+

## Instalação Local

### 1. Clonar o projeto

```bash
git clone https://github.com/kaoyeoshiro/painel_pj.git
cd painel_pj
```

### 2. Criar ambiente virtual

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# ou
source .venv/bin/activate  # Linux/Mac
```

### 3. Instalar dependências Python

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o arquivo .env com suas configurações
```

### 5. Rodar o servidor

```bash
python main.py
```

ou

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Deploy no Railway

### 1. Criar projeto no Railway

1. Acesse [railway.app](https://railway.app)
2. Crie um novo projeto
3. Adicione um serviço PostgreSQL
4. Conecte o repositório GitHub

### 2. Configurar variáveis de ambiente

No painel do Railway, configure as seguintes variáveis:

```env
# Banco de dados (Railway preenche automaticamente com PostgreSQL)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Autenticação
SECRET_KEY=sua-chave-secreta-muito-forte
ADMIN_USERNAME=admin
ADMIN_PASSWORD=sua-senha-admin

# OpenRouter (IA)
OPENROUTER_API_KEY=sua-api-key
```

### 3. Deploy

O Railway detecta automaticamente o `railway.toml` e faz o deploy.

## Estrutura do Projeto

```
portal-pge/
├── auth/                           # Autenticação JWT
├── admin/                          # Administração de prompts e IA
├── users/                          # CRUD de usuários
├── database/                       # Banco de dados SQLAlchemy
├── sistemas/
│   ├── assistencia_judiciaria/     # Sistema 1
│   └── matriculas_confrontantes/   # Sistema 2
├── frontend/                       # Templates HTML
├── logo/                           # Logotipos
├── main.py                         # Aplicação FastAPI
├── config.py                       # Configurações
├── railway.toml                    # Configuração Railway
└── requirements.txt                # Dependências Python
```

## Usuário Padrão

- **Usuário**: admin
- **Senha**: Definida em `ADMIN_PASSWORD` (deve ser alterada)

## Tecnologias

- **Backend**: FastAPI, SQLAlchemy, Pydantic
- **Frontend**: HTML/CSS/JS (Tailwind CSS)
- **Banco de Dados**: SQLite (desenvolvimento) / PostgreSQL (produção)
- **Autenticação**: JWT
- **IA**: OpenRouter API

## Licença

Uso interno - Procuradoria-Geral do Estado de Mato Grosso do Sul
