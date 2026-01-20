# scripts/criar_tabela_regras_tipo_peca.py
"""
Script para criar a tabela regra_deterministica_tipo_peca se não existir.

Execute este script se você receber o erro:
    sqlite3.OperationalError: no such table: regra_deterministica_tipo_peca

Uso:
    python scripts/criar_tabela_regras_tipo_peca.py
"""

import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from database.connection import engine

# SQL para criar a tabela diretamente (compatível com SQLite)
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS regra_deterministica_tipo_peca (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo_id INTEGER NOT NULL,
    tipo_peca VARCHAR(50) NOT NULL,
    regra_deterministica JSON NOT NULL,
    regra_texto_original TEXT,
    ativo BOOLEAN DEFAULT 1,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    criado_por INTEGER,
    atualizado_por INTEGER,
    FOREIGN KEY (modulo_id) REFERENCES prompt_modulos(id) ON DELETE CASCADE
);
"""

# Índices para performance
CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_regra_det_tipo_peca_modulo_id ON regra_deterministica_tipo_peca(modulo_id);",
    "CREATE INDEX IF NOT EXISTS ix_regra_det_tipo_peca_tipo_peca ON regra_deterministica_tipo_peca(tipo_peca);",
]


def criar_tabela():
    """Cria a tabela regra_deterministica_tipo_peca se não existir."""

    # Verifica se a tabela já existe
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if 'regra_deterministica_tipo_peca' in existing_tables:
        print("[OK] Tabela 'regra_deterministica_tipo_peca' já existe!")
        return

    print("[...] Criando tabela 'regra_deterministica_tipo_peca'...")

    with engine.connect() as conn:
        # Cria a tabela
        conn.execute(text(CREATE_TABLE_SQL))
        conn.commit()

        # Cria índices
        for idx_sql in CREATE_INDEXES_SQL:
            try:
                conn.execute(text(idx_sql))
                conn.commit()
            except Exception as e:
                print(f"[AVISO] Índice pode já existir: {e}")

    # Verifica se foi criada
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if 'regra_deterministica_tipo_peca' in existing_tables:
        print("[OK] Tabela 'regra_deterministica_tipo_peca' criada com sucesso!")
    else:
        print("[ERRO] Falha ao criar a tabela. Verifique os logs.")


if __name__ == "__main__":
    criar_tabela()
