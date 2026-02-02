#!/usr/bin/env python
"""
Script para aplicar migração do campo status.

Problema: Campo status é VARCHAR(20) mas 'aguardando_documentos' tem 21 chars.
Solução: Aumentar para VARCHAR(30).

Uso:
    python scripts/apply_migration_status.py
"""

import sys
sys.path.insert(0, ".")

from database.connection import engine
from sqlalchemy import text


def check_column_size():
    """Verifica o tamanho atual da coluna."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'geracoes_prestacao_contas'
            AND column_name = 'status'
        """))
        row = result.fetchone()
        if row:
            print(f"Coluna: {row[0]}")
            print(f"Tipo: {row[1]}")
            print(f"Tamanho máximo: {row[2]}")
            return row[2]
        else:
            print("Coluna não encontrada!")
            return None


def apply_migration():
    """Aplica a migração."""
    with engine.connect() as conn:
        print("Aplicando migração...")
        conn.execute(text("""
            ALTER TABLE geracoes_prestacao_contas
            ALTER COLUMN status TYPE VARCHAR(30)
        """))
        conn.commit()
        print("Migração aplicada com sucesso!")


def main():
    print("=" * 50)
    print("MIGRAÇÃO: Fix status column size")
    print("=" * 50)

    print("\nAntes da migração:")
    size_before = check_column_size()

    if size_before and size_before >= 30:
        print(f"\nColuna já tem tamanho suficiente ({size_before}). Nada a fazer.")
        return

    print("\nAplicando migração...")
    apply_migration()

    print("\nDepois da migração:")
    check_column_size()

    print("\nMigração concluída!")


if __name__ == "__main__":
    main()
