# database/init_db.py
"""
Inicialização do banco de dados e seed do usuário admin
"""

import time
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from sqlalchemy import text
from database.connection import engine, Base, SessionLocal
from auth.models import User
from auth.security import get_password_hash
from config import ADMIN_USERNAME, ADMIN_PASSWORD

# Importa modelos para criar tabelas
from sistemas.matriculas_confrontantes.models import Analise, Registro, LogSistema, FeedbackMatricula
from sistemas.assistencia_judiciaria.models import ConsultaProcesso, FeedbackAnalise
from admin.models import PromptConfig, ConfiguracaoIA


def wait_for_db(max_retries=10, delay=3):
    """Aguarda o banco de dados ficar disponível"""
    for attempt in range(max_retries):
        try:
            # Tenta conectar
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("✅ Conexão com banco de dados estabelecida!")
            return True
        except OperationalError as e:
            if attempt < max_retries - 1:
                print(f"⏳ Aguardando banco de dados... tentativa {attempt + 1}/{max_retries}")
                time.sleep(delay)
            else:
                print(f"❌ Não foi possível conectar ao banco após {max_retries} tentativas")
                raise e
    return False


def create_tables():
    """Cria todas as tabelas no banco de dados"""
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelas criadas com sucesso!")


def seed_admin():
    """Cria o usuário administrador inicial se não existir"""
    db = SessionLocal()
    try:
        # Verifica se já existe um admin
        existing_admin = db.query(User).filter(User.username == ADMIN_USERNAME).first()
        
        if not existing_admin:
            admin = User(
                username=ADMIN_USERNAME,
                full_name="Administrador",
                email=None,
                hashed_password=get_password_hash(ADMIN_PASSWORD),
                role="admin",
                must_change_password=True,
                is_active=True
            )
            db.add(admin)
            db.commit()
            print(f"✅ Usuário admin '{ADMIN_USERNAME}' criado com sucesso!")
            print(f"   Senha inicial: {ADMIN_PASSWORD}")
            print(f"   ⚠️  Altere a senha no primeiro acesso!")
        else:
            print(f"ℹ️  Usuário admin '{ADMIN_USERNAME}' já existe.")
    finally:
        db.close()


def seed_prompts():
    """Cria os prompts padrão se não existirem"""
    from admin.seed_prompts import seed_all_defaults
    
    db = SessionLocal()
    try:
        # Verifica se já existem prompts
        existing = db.query(PromptConfig).count()
        
        if existing == 0:
            seed_all_defaults(db)
            print("✅ Prompts e configurações de IA padrão criados!")
        else:
            print(f"ℹ️  {existing} prompt(s) já existem no banco.")
    finally:
        db.close()


def init_database():
    """Inicializa o banco de dados completo"""
    print("🔧 Inicializando banco de dados...")
    wait_for_db()  # Aguarda o banco ficar disponível
    create_tables()
    seed_admin()
    seed_prompts()
    print("✅ Banco de dados inicializado!")


if __name__ == "__main__":
    init_database()
