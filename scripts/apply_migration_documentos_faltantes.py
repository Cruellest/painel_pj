#!/usr/bin/env python
"""
Script para aplicar migração dos campos de documentos faltantes.

Adiciona as colunas:
- documentos_faltantes (JSON)
- mensagem_erro_usuario (TEXT)
- estado_expira_em (TIMESTAMP)

Uso:
    python scripts/apply_migration_documentos_faltantes.py
"""

import sys
sys.path.insert(0, ".")

from database.connection import engine
from sqlalchemy import text


def check_columns_exist():
    """Verifica se as colunas já existem."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'geracoes_prestacao_contas'
            AND column_name IN ('documentos_faltantes', 'mensagem_erro_usuario', 'estado_expira_em')
        """))
        existing = [row[0] for row in result.fetchall()]
        return existing


def apply_migration():
    """Aplica a migração."""
    with engine.connect() as conn:
        existing_columns = check_columns_exist()

        # Adiciona documentos_faltantes
        if 'documentos_faltantes' not in existing_columns:
            print("Adicionando coluna documentos_faltantes...")
            conn.execute(text("""
                ALTER TABLE geracoes_prestacao_contas
                ADD COLUMN documentos_faltantes JSONB
            """))
            print("  - documentos_faltantes adicionada!")
        else:
            print("  - documentos_faltantes já existe")

        # Adiciona mensagem_erro_usuario
        if 'mensagem_erro_usuario' not in existing_columns:
            print("Adicionando coluna mensagem_erro_usuario...")
            conn.execute(text("""
                ALTER TABLE geracoes_prestacao_contas
                ADD COLUMN mensagem_erro_usuario TEXT
            """))
            print("  - mensagem_erro_usuario adicionada!")
        else:
            print("  - mensagem_erro_usuario já existe")

        # Adiciona estado_expira_em
        if 'estado_expira_em' not in existing_columns:
            print("Adicionando coluna estado_expira_em...")
            conn.execute(text("""
                ALTER TABLE geracoes_prestacao_contas
                ADD COLUMN estado_expira_em TIMESTAMP
            """))
            print("  - estado_expira_em adicionada!")
        else:
            print("  - estado_expira_em já existe")

        conn.commit()
        print("\nMigração concluída!")


def main():
    print("=" * 50)
    print("MIGRAÇÃO: Campos de documentos faltantes")
    print("=" * 50)

    print("\nVerificando colunas existentes...")
    existing = check_columns_exist()
    print(f"Colunas encontradas: {existing if existing else 'nenhuma'}")

    if len(existing) == 3:
        print("\nTodas as colunas já existem. Nada a fazer.")
        return

    print("\nAplicando migração...")
    apply_migration()

    print("\nVerificando resultado...")
    final = check_columns_exist()
    print(f"Colunas após migração: {final}")


if __name__ == "__main__":
    main()
