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
from sistemas.gerador_pecas.models import GeracaoPeca, FeedbackPeca
from admin.models import PromptConfig, ConfiguracaoIA
from admin.models_prompts import PromptModulo, PromptModuloHistorico


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
    from sqlalchemy import text, inspect
    db = SessionLocal()
    
    # Detecta se é SQLite ou PostgreSQL
    is_sqlite = 'sqlite' in str(engine.url)
    
    def column_exists(table_name, column_name):
        """Verifica se uma coluna existe na tabela"""
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    
    def table_exists(table_name):
        """Verifica se uma tabela existe"""
        inspector = inspect(engine)
        return table_name in inspector.get_table_names()
    
    # Migração: Criar tabela grupos_analise se não existir
    if not table_exists('grupos_analise'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE grupos_analise (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nome VARCHAR(255),
                        descricao TEXT,
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        usuario_id INTEGER REFERENCES users(id),
                        status VARCHAR(20) DEFAULT 'pendente',
                        resultado_json JSON,
                        confianca FLOAT DEFAULT 0.0
                    )
                """))
            else:
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
            print(f"⚠️ Migração grupos_analise: {e}")
    
    # Migração: Adicionar coluna grupo_id na tabela analises
    if table_exists('analises') and not column_exists('analises', 'grupo_id'):
        try:
            db.execute(text("ALTER TABLE analises ADD COLUMN grupo_id INTEGER REFERENCES grupos_analise(id)"))
            db.commit()
            print("✅ Migração: coluna grupo_id adicionada em analises")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Migração grupo_id: {e}")
    
    # Migração: Adicionar coluna relatorio_texto na tabela analises
    if table_exists('analises') and not column_exists('analises', 'relatorio_texto'):
        try:
            db.execute(text("ALTER TABLE analises ADD COLUMN relatorio_texto TEXT"))
            db.commit()
            print("✅ Migração: coluna relatorio_texto adicionada em analises")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Migração relatorio_texto: {e}")
    
    # Migração: Adicionar coluna modelo_usado na tabela analises
    if table_exists('analises') and not column_exists('analises', 'modelo_usado'):
        try:
            db.execute(text("ALTER TABLE analises ADD COLUMN modelo_usado VARCHAR(100)"))
            db.commit()
            print("✅ Migração: coluna modelo_usado adicionada em analises")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Migração modelo_usado: {e}")
    
    # Migração: Criar tabela arquivos_upload
    if not table_exists('arquivos_upload'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE arquivos_upload (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_id VARCHAR(255) UNIQUE NOT NULL,
                        file_name VARCHAR(255) NOT NULL,
                        usuario_id INTEGER NOT NULL REFERENCES users(id),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
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
            print(f"⚠️ Migração arquivos_upload: {e}")
    
    # Migração: Criar tabelas do novo sistema gerador_pecas
    if not table_exists('geracoes_pecas'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE geracoes_pecas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        numero_cnj VARCHAR(30) NOT NULL,
                        numero_cnj_formatado VARCHAR(30),
                        tipo_peca VARCHAR(50),
                        dados_processo JSON,
                        conteudo_gerado JSON,
                        arquivo_path VARCHAR(500),
                        modelo_usado VARCHAR(100),
                        usuario_id INTEGER REFERENCES users(id),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS geracoes_pecas (
                        id SERIAL PRIMARY KEY,
                        numero_cnj VARCHAR(30) NOT NULL,
                        numero_cnj_formatado VARCHAR(30),
                        tipo_peca VARCHAR(50),
                        dados_processo JSON,
                        conteudo_gerado JSON,
                        arquivo_path VARCHAR(500),
                        modelo_usado VARCHAR(100),
                        usuario_id INTEGER REFERENCES users(id),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            db.commit()
            print("✅ Migração: tabela geracoes_pecas criada")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Migração geracoes_pecas: {e}")
    
    if not table_exists('feedbacks_pecas'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE feedbacks_pecas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        geracao_id INTEGER NOT NULL REFERENCES geracoes_pecas(id),
                        usuario_id INTEGER NOT NULL REFERENCES users(id),
                        avaliacao VARCHAR(20) NOT NULL,
                        nota INTEGER,
                        comentario TEXT,
                        campos_incorretos JSON,
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS feedbacks_pecas (
                        id SERIAL PRIMARY KEY,
                        geracao_id INTEGER NOT NULL REFERENCES geracoes_pecas(id),
                        usuario_id INTEGER NOT NULL REFERENCES users(id),
                        avaliacao VARCHAR(20) NOT NULL,
                        nota INTEGER,
                        comentario TEXT,
                        campos_incorretos JSON,
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            db.commit()
            print("✅ Migração: tabela feedbacks_pecas criada")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Migração feedbacks_pecas: {e}")
    
    # Migração: Adicionar colunas de permissões na tabela users
    if table_exists('users') and not column_exists('users', 'sistemas_permitidos'):
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN sistemas_permitidos JSON"))
            db.commit()
            print("✅ Migração: coluna sistemas_permitidos adicionada em users")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Migração sistemas_permitidos: {e}")
    
    if table_exists('users') and not column_exists('users', 'permissoes_especiais'):
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN permissoes_especiais JSON"))
            db.commit()
            print("✅ Migração: coluna permissoes_especiais adicionada em users")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Migração permissoes_especiais: {e}")
    
    # Migração: Criar tabela prompt_modulos
    if not table_exists('prompt_modulos'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE prompt_modulos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tipo VARCHAR(20) NOT NULL,
                        categoria VARCHAR(50),
                        subcategoria VARCHAR(50),
                        nome VARCHAR(100) NOT NULL,
                        titulo VARCHAR(200) NOT NULL,
                        conteudo TEXT NOT NULL,
                        palavras_chave JSON,
                        tags JSON,
                        ativo BOOLEAN DEFAULT 1,
                        ordem INTEGER DEFAULT 0,
                        versao INTEGER DEFAULT 1,
                        criado_por INTEGER REFERENCES users(id),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        atualizado_por INTEGER REFERENCES users(id),
                        atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tipo, categoria, subcategoria, nome)
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS prompt_modulos (
                        id SERIAL PRIMARY KEY,
                        tipo VARCHAR(20) NOT NULL,
                        categoria VARCHAR(50),
                        subcategoria VARCHAR(50),
                        nome VARCHAR(100) NOT NULL,
                        titulo VARCHAR(200) NOT NULL,
                        conteudo TEXT NOT NULL,
                        palavras_chave JSON,
                        tags JSON,
                        ativo BOOLEAN DEFAULT true,
                        ordem INTEGER DEFAULT 0,
                        versao INTEGER DEFAULT 1,
                        criado_por INTEGER REFERENCES users(id),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        atualizado_por INTEGER REFERENCES users(id),
                        atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tipo, categoria, subcategoria, nome)
                    )
                """))
            db.commit()
            print("✅ Migração: tabela prompt_modulos criada")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Migração prompt_modulos: {e}")
    
    # Migração: Criar tabela prompt_modulos_historico
    if not table_exists('prompt_modulos_historico'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE prompt_modulos_historico (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        modulo_id INTEGER NOT NULL REFERENCES prompt_modulos(id),
                        versao INTEGER NOT NULL,
                        conteudo TEXT NOT NULL,
                        palavras_chave JSON,
                        tags JSON,
                        alterado_por INTEGER REFERENCES users(id),
                        alterado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        motivo TEXT,
                        diff_resumo TEXT
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS prompt_modulos_historico (
                        id SERIAL PRIMARY KEY,
                        modulo_id INTEGER NOT NULL REFERENCES prompt_modulos(id),
                        versao INTEGER NOT NULL,
                        conteudo TEXT NOT NULL,
                        palavras_chave JSON,
                        tags JSON,
                        alterado_por INTEGER REFERENCES users(id),
                        alterado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        motivo TEXT,
                        diff_resumo TEXT
                    )
                """))
            db.commit()
            print("✅ Migração: tabela prompt_modulos_historico criada")
        except Exception as e:
            db.rollback()
            print(f"⚠️ Migração prompt_modulos_historico: {e}")
    
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
