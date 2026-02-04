#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de validacao do ambiente de desenvolvimento
==================================================
Verifica se tudo esta configurado corretamente.

Uso:
    python scripts/db_validate_local.py

Checklist:
    [x] Arquivo .env configurado
    [x] DATABASE_URL aponta para PostgreSQL
    [x] Conexao com banco OK
    [x] Tabelas criadas
    [x] Usuario admin existe
    [x] Aplicacao importavel
"""

import os
import sys
from pathlib import Path

# Adiciona raiz do projeto ao path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Cores para terminal
os.system('')  # Habilita ANSI no Windows

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'


def print_status(ok, message):
    """Imprime status com cor"""
    if ok:
        print(f"  {GREEN}[OK]{RESET} {message}")
    else:
        print(f"  {RED}[ERRO]{RESET} {message}")
    return ok


def check_env_file():
    """Verifica se .env existe e tem DATABASE_URL"""
    env_path = PROJECT_ROOT / '.env'
    if not env_path.exists():
        return False, "Arquivo .env nao encontrado"

    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
        if 'DATABASE_URL' not in content:
            return False, "DATABASE_URL nao definida no .env"

        # Verifica se ainda esta usando SQLite (linha ativa, nao comentada)
        for line in content.split('\n'):
            if line.strip().startswith('DATABASE_URL=') and 'sqlite' in line.lower():
                return False, "DATABASE_URL ainda aponta para SQLite! Use PostgreSQL."

    return True, "Arquivo .env configurado"


def check_postgres_url():
    """Verifica se DATABASE_URL aponta para PostgreSQL"""
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / '.env')
    except ImportError:
        pass

    db_url = os.getenv('DATABASE_URL', '')

    if not db_url:
        return False, "DATABASE_URL nao definida"

    if 'sqlite' in db_url.lower():
        return False, "DATABASE_URL aponta para SQLite"

    if 'postgresql' not in db_url.lower():
        return False, f"DATABASE_URL nao parece ser PostgreSQL: {db_url[:30]}..."

    return True, "DATABASE_URL aponta para PostgreSQL"


def check_db_connection():
    """Verifica conexao com o banco via SQLAlchemy"""
    try:
        from database.connection import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()

        if 'PostgreSQL' not in version:
            return False, f"Banco nao e PostgreSQL: {version}"

        return True, f"Conexao OK (PostgreSQL)"
    except Exception as e:
        return False, f"Falha na conexao: {e}"


def check_tables_exist():
    """Verifica se as tabelas principais existem"""
    try:
        from database.connection import engine
        from sqlalchemy import inspect

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())

        required = {'users', 'geracoes_pecas', 'consultas_processos'}
        missing = required - tables

        if missing:
            return False, f"Tabelas faltando: {missing}. Execute: python -m database.init_db"

        return True, f"{len(tables)} tabelas encontradas"
    except Exception as e:
        return False, f"Erro ao verificar tabelas: {e}"


def check_admin_user():
    """Verifica se usuario admin existe"""
    try:
        from database.connection import SessionLocal
        from auth.models import User

        db = SessionLocal()
        admin = db.query(User).filter(User.username == 'admin').first()
        db.close()

        if not admin:
            return False, "Usuario admin nao existe. Execute: python -m database.init_db"

        return True, "Usuario admin existe"
    except Exception as e:
        return False, f"Erro ao verificar admin: {e}"


def check_app_import():
    """Verifica se a aplicacao FastAPI e importavel"""
    try:
        from main import app
        if app:
            return True, "Aplicacao FastAPI OK"
        return False, "app e None"
    except Exception as e:
        return False, f"Erro ao importar app: {e}"


def main():
    print(f"\n{YELLOW}{'=' * 60}{RESET}")
    print(f"{YELLOW}Validacao do Ambiente de Desenvolvimento{RESET}")
    print(f"{YELLOW}{'=' * 60}{RESET}\n")

    # Carrega .env
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / '.env')
    except ImportError:
        print(f"{YELLOW}[WARN] python-dotenv nao instalado{RESET}\n")

    checks = [
        ("Arquivo .env", check_env_file),
        ("DATABASE_URL", check_postgres_url),
        ("Conexao com banco", check_db_connection),
        ("Tabelas do banco", check_tables_exist),
        ("Usuario admin", check_admin_user),
        ("Importacao do app", check_app_import),
    ]

    results = []
    print(f"{BLUE}Executando verificacoes...{RESET}\n")

    for name, check_func in checks:
        try:
            ok, message = check_func()
        except Exception as e:
            ok, message = False, f"Excecao: {e}"

        print_status(ok, f"{name}: {message}")
        results.append(ok)

    # Sumario
    passed = sum(results)
    total = len(results)

    print(f"\n{YELLOW}{'=' * 60}{RESET}")

    if all(results):
        print(f"{GREEN}SUCESSO! Todas as {total} verificacoes passaram.{RESET}")
        print(f"\n{GREEN}Seu ambiente esta pronto para desenvolvimento!{RESET}")
        print(f"\nInicie o servidor com:")
        print(f"  uvicorn main:app --reload")
        return 0
    else:
        print(f"{RED}FALHA: {passed}/{total} verificacoes passaram.{RESET}")
        print(f"\n{YELLOW}Corrija os erros acima antes de continuar.{RESET}")
        print(f"\nDicas:")
        print(f"  1. Verifique o .env (DATABASE_URL deve ser PostgreSQL)")
        print(f"  2. Execute migrations: python -m database.init_db")
        return 1


if __name__ == '__main__':
    sys.exit(main())
