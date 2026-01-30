"""
scripts/fix_empty_fullname.py

Script utilitário para corrigir registros de usuários cujo `full_name` ficou vazio
após sanitização (causando `ResponseValidationError` na serialização).

Uso:
    python scripts/fix_empty_fullname.py

O script substitui `full_name` inválido (tamanho < 2) pelo `username`.
"""
from sqlalchemy import func, or_
from database.connection import get_db_context
from auth.models import User


def fix_full_names():
    with get_db_context() as db:
        # Busca usuários cujo full_name tem comprimento menor que 2 ou é string vazia
        users = db.query(User).filter(or_(func.length(User.full_name) < 2, User.full_name == "")).all()
        if not users:
            print("Nenhum usuário com full_name inválido encontrado.")
            return

        print(f"Encontrados {len(users)} usuário(s) com full_name inválido. Corrigindo...")
        for u in users:
            new_name = u.username or "Usuário"
            print(f"  - Atualizando user id={u.id} username={u.username} -> full_name='{new_name}'")
            u.full_name = new_name
        # Commit pelo context manager
        print("Correção aplicada. Commit realizado.")


if __name__ == '__main__':
    fix_full_names()
