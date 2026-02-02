"""
Migration: Adiciona colunas de upload ao classificador de documentos

Adiciona as seguintes colunas à tabela codigos_documento_projeto:
- arquivo_nome: Nome original do arquivo uploadado
- arquivo_hash: SHA256 para deduplicacao
- texto_extraido: Cache do texto extraido do PDF
- tipo_documento: Tipo do documento no TJ-MS

Uso: python scripts/apply_migration_classificador_upload.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import engine
from sqlalchemy import text


def apply_migration():
    """Aplica a migration para adicionar colunas de upload"""

    columns_to_add = [
        ("arquivo_nome", "VARCHAR(500)"),
        ("arquivo_hash", "VARCHAR(64)"),
        ("texto_extraido", "TEXT"),
        ("tipo_documento", "VARCHAR(10)"),
    ]

    with engine.connect() as conn:
        # Verifica quais colunas ja existem
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'codigos_documento_projeto'
        """))
        existing_columns = {row[0] for row in result}

        print(f"[INFO] Colunas existentes: {existing_columns}")

        # Adiciona colunas faltantes
        for col_name, col_type in columns_to_add:
            if col_name not in existing_columns:
                print(f"[ADD] Adicionando coluna: {col_name} ({col_type})")
                conn.execute(text(f"""
                    ALTER TABLE codigos_documento_projeto
                    ADD COLUMN {col_name} {col_type}
                """))
            else:
                print(f"[OK] Coluna ja existe: {col_name}")

        conn.commit()
        print("[SUCCESS] Migration aplicada com sucesso!")


if __name__ == "__main__":
    apply_migration()
