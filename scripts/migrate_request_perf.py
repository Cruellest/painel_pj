#!/usr/bin/env python
# scripts/migrate_request_perf.py
"""
Script de migracao para criar a tabela request_perf_logs.

Uso:
    python scripts/migrate_request_perf.py

Este script cria a tabela se nao existir, sem afetar dados existentes.
"""

import sys
import os

# Adiciona o diretorio raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect
from database.connection import engine, Base

# Importa o modelo para registrar no metadata
from admin.models_request_perf import RequestPerfLog


def migrate():
    """Cria a tabela request_perf_logs se nao existir."""
    inspector = inspect(engine)

    if 'request_perf_logs' in inspector.get_table_names():
        print("[OK] Tabela 'request_perf_logs' ja existe")
        return

    print("[...] Criando tabela 'request_perf_logs'...")

    # Cria apenas a tabela deste modelo
    RequestPerfLog.__table__.create(engine)

    print("[OK] Tabela 'request_perf_logs' criada com sucesso!")


if __name__ == "__main__":
    migrate()
