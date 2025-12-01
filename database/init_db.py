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
from sistemas.matriculas_confrontantes.models import Analise, Registro, LogSistema, FeedbackMatricula, GrupoAnalise, ArquivoUpload
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


def run_migrations():
    """Executa migrações manuais para ajustar colunas existentes"""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        # Torna file_path nullable na tabela analises
        db.execute(text("ALTER TABLE analises ALTER COLUMN file_path DROP NOT NULL"))
        db.commit()
        print("✅ Migração: file_path agora é nullable")
    except Exception as e:
        db.rollback()
        # Ignora se já foi aplicada ou tabela não existe
        if "does not exist" not in str(e) and "already" not in str(e).lower():
            print(f"⚠️ Migração file_path: {e}")
    
    # Migração: Criar tabela grupos_analise se não existir
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS grupos_analise (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(255),
                descricao TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usuario_id INTEGER REFERENCES users(id),
                status VARCHAR(20) DEFAULT 'pendente',
                resultado_json JSON,
                confianca FLOAT DEFAULT 0.0
            )
        """))
        db.commit()
        print("✅ Migração: tabela grupos_analise criada")
    except Exception as e:
        db.rollback()
        if "already exists" not in str(e).lower():
            print(f"⚠️ Migração grupos_analise: {e}")
    
    # Migração: Adicionar coluna grupo_id na tabela analises
    try:
        db.execute(text("""
            ALTER TABLE analises 
            ADD COLUMN IF NOT EXISTS grupo_id INTEGER REFERENCES grupos_analise(id)
        """))
        db.commit()
        print("✅ Migração: coluna grupo_id adicionada em analises")
    except Exception as e:
        db.rollback()
        if "already exists" not in str(e).lower() and "duplicate column" not in str(e).lower():
            print(f"⚠️ Migração grupo_id: {e}")
    
    # Migração: Adicionar coluna relatorio_texto na tabela analises
    try:
        db.execute(text("""
            ALTER TABLE analises 
            ADD COLUMN IF NOT EXISTS relatorio_texto TEXT
        """))
        db.commit()
        print("✅ Migração: coluna relatorio_texto adicionada em analises")
    except Exception as e:
        db.rollback()
        if "already exists" not in str(e).lower() and "duplicate column" not in str(e).lower():
            print(f"⚠️ Migração relatorio_texto: {e}")
    
    # Migração: Criar tabela arquivos_upload
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS arquivos_upload (
                id SERIAL PRIMARY KEY,
                file_id VARCHAR(255) UNIQUE NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                usuario_id INTEGER NOT NULL REFERENCES users(id),
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        db.commit()
        print("✅ Migração: tabela arquivos_upload criada")
    except Exception as e:
        db.rollback()
        if "already exists" not in str(e).lower():
            print(f"⚠️ Migração arquivos_upload: {e}")
    
    db.close()


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
    run_migrations()  # Aplica migrações
    seed_admin()
    seed_prompts()
    print("✅ Banco de dados inicializado!")


if __name__ == "__main__":
    init_database()
