"""
Script para executar migrações do banco de dados manualmente
"""

from database.init_db import run_migrations

if __name__ == "__main__":
    print("Executando migracoes do banco de dados...")
    try:
        run_migrations()
        print("Migracoes executadas com sucesso!")
    except Exception as e:
        print(f"Erro ao executar migracoes: {e}")
        raise
