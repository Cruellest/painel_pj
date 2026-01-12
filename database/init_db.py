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
from sistemas.gerador_pecas.models_resumo_json import CategoriaResumoJSON, CategoriaResumoJSONHistorico
from sistemas.gerador_pecas.models_config_pecas import CategoriaDocumento, TipoPeca, tipo_peca_categorias
from sistemas.pedido_calculo.models import GeracaoPedidoCalculo, FeedbackPedidoCalculo, LogChamadaIA
from sistemas.prestacao_contas.models import GeracaoAnalise, LogChamadaIAPrestacao, FeedbackPrestacao
from admin.models import PromptConfig, ConfiguracaoIA
from admin.models_prompts import PromptModulo, PromptModuloHistorico, ModuloTipoPeca
from admin.models_prompt_groups import PromptGroup, PromptSubgroup


def wait_for_db(max_retries=10, delay=3):
    """Aguarda o banco de dados ficar disponível"""
    for attempt in range(max_retries):
        try:
            # Tenta conectar
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("[OK] Conexao com banco de dados estabelecida!")
            return True
        except OperationalError as e:
            if attempt < max_retries - 1:
                print(f"[...] Aguardando banco de dados... tentativa {attempt + 1}/{max_retries}")
                time.sleep(delay)
            else:
                print(f"[ERRO] Nao foi possivel conectar ao banco apos {max_retries} tentativas")
                raise e
    return False


def create_tables():
    """Cria todas as tabelas no banco de dados"""
    Base.metadata.create_all(bind=engine)
    print("[OK] Tabelas criadas com sucesso!")


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
            print("[OK] Migração: tabela grupos_analise criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração grupos_analise: {e}")
    
    # Migração: Adicionar coluna grupo_id na tabela analises
    if table_exists('analises') and not column_exists('analises', 'grupo_id'):
        try:
            db.execute(text("ALTER TABLE analises ADD COLUMN grupo_id INTEGER REFERENCES grupos_analise(id)"))
            db.commit()
            print("[OK] Migração: coluna grupo_id adicionada em analises")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração grupo_id: {e}")
    
    # Migração: Adicionar coluna relatorio_texto na tabela analises
    if table_exists('analises') and not column_exists('analises', 'relatorio_texto'):
        try:
            db.execute(text("ALTER TABLE analises ADD COLUMN relatorio_texto TEXT"))
            db.commit()
            print("[OK] Migração: coluna relatorio_texto adicionada em analises")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração relatorio_texto: {e}")
    
    # Migração: Adicionar coluna modelo_usado na tabela analises
    if table_exists('analises') and not column_exists('analises', 'modelo_usado'):
        try:
            db.execute(text("ALTER TABLE analises ADD COLUMN modelo_usado VARCHAR(100)"))
            db.commit()
            print("[OK] Migração: coluna modelo_usado adicionada em analises")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração modelo_usado: {e}")
    
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
            print("[OK] Migração: tabela arquivos_upload criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração arquivos_upload: {e}")
    
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
                        documentos_processados JSON,
                        conteudo_gerado TEXT,
                        prompt_enviado TEXT,
                        resumo_consolidado TEXT,
                        historico_chat JSON,
                        arquivo_path VARCHAR(500),
                        modelo_usado VARCHAR(100),
                        tempo_processamento INTEGER,
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
                        documentos_processados JSON,
                        conteudo_gerado TEXT,
                        prompt_enviado TEXT,
                        resumo_consolidado TEXT,
                        historico_chat JSON,
                        arquivo_path VARCHAR(500),
                        modelo_usado VARCHAR(100),
                        tempo_processamento INTEGER,
                        usuario_id INTEGER REFERENCES users(id),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            db.commit()
            print("[OK] Migração: tabela geracoes_pecas criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração geracoes_pecas: {e}")
    
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
            print("[OK] Migração: tabela feedbacks_pecas criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração feedbacks_pecas: {e}")
    
    # Migração: Criar tabela feedbacks_matricula (sistema de matrículas confrontantes)
    if not table_exists('feedbacks_matricula'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE feedbacks_matricula (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        analise_id INTEGER NOT NULL REFERENCES analises(id),
                        usuario_id INTEGER NOT NULL REFERENCES users(id),
                        avaliacao VARCHAR(20) NOT NULL,
                        comentario TEXT,
                        campos_incorretos JSON,
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS feedbacks_matricula (
                        id SERIAL PRIMARY KEY,
                        analise_id INTEGER NOT NULL REFERENCES analises(id),
                        usuario_id INTEGER NOT NULL REFERENCES users(id),
                        avaliacao VARCHAR(20) NOT NULL,
                        comentario TEXT,
                        campos_incorretos JSON,
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            db.commit()
            print("[OK] Migração: tabela feedbacks_matricula criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração feedbacks_matricula: {e}")
    
    # Migração: Adicionar colunas de permissões na tabela users
    if table_exists('users') and not column_exists('users', 'sistemas_permitidos'):
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN sistemas_permitidos JSON"))
            db.commit()
            print("[OK] Migração: coluna sistemas_permitidos adicionada em users")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração sistemas_permitidos: {e}")
    
    if table_exists('users') and not column_exists('users', 'permissoes_especiais'):
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN permissoes_especiais JSON"))
            db.commit()
            print("[OK] Migração: coluna permissoes_especiais adicionada em users")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração permissoes_especiais: {e}")
    
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
            print("[OK] Migração: tabela prompt_modulos criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração prompt_modulos: {e}")
    
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
            print("[OK] Migração: tabela prompt_modulos_historico criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração prompt_modulos_historico: {e}")
    
    # Migracao: Criar tabela prompt_groups
    if not table_exists('prompt_groups'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE prompt_groups (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(100) NOT NULL,
                        slug VARCHAR(50) UNIQUE NOT NULL,
                        active BOOLEAN DEFAULT 1,
                        "order" INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS prompt_groups (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        slug VARCHAR(50) UNIQUE NOT NULL,
                        active BOOLEAN DEFAULT true,
                        "order" INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            db.commit()
            print("[OK] Migracao: tabela prompt_groups criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migracao prompt_groups: {e}")

    # Migracao: Criar tabela prompt_subgroups
    if not table_exists('prompt_subgroups'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE prompt_subgroups (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        group_id INTEGER NOT NULL REFERENCES prompt_groups(id),
                        name VARCHAR(100) NOT NULL,
                        slug VARCHAR(50) NOT NULL,
                        active BOOLEAN DEFAULT 1,
                        "order" INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(group_id, slug)
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS prompt_subgroups (
                        id SERIAL PRIMARY KEY,
                        group_id INTEGER NOT NULL REFERENCES prompt_groups(id),
                        name VARCHAR(100) NOT NULL,
                        slug VARCHAR(50) NOT NULL,
                        active BOOLEAN DEFAULT true,
                        "order" INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(group_id, slug)
                    )
                """))
            db.commit()
            print("[OK] Migracao: tabela prompt_subgroups criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migracao prompt_subgroups: {e}")

    # Migracao: Criar tabela user_prompt_groups
    if not table_exists('user_prompt_groups'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE user_prompt_groups (
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        group_id INTEGER NOT NULL REFERENCES prompt_groups(id),
                        PRIMARY KEY (user_id, group_id)
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS user_prompt_groups (
                        user_id INTEGER NOT NULL REFERENCES users(id),
                        group_id INTEGER NOT NULL REFERENCES prompt_groups(id),
                        PRIMARY KEY (user_id, group_id)
                    )
                """))
            db.commit()
            print("[OK] Migracao: tabela user_prompt_groups criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migracao user_prompt_groups: {e}")

    # Migracao: Adicionar coluna default_group_id na tabela users
    if table_exists('users') and not column_exists('users', 'default_group_id'):
        try:
            db.execute(text("ALTER TABLE users ADD COLUMN default_group_id INTEGER REFERENCES prompt_groups(id)"))
            db.commit()
            print("[OK] Migracao: coluna default_group_id adicionada em users")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migracao default_group_id users: {e}")

    # Migracao: Adicionar colunas group_id e subgroup_id na tabela prompt_modulos
    if table_exists('prompt_modulos') and not column_exists('prompt_modulos', 'group_id'):
        try:
            db.execute(text("ALTER TABLE prompt_modulos ADD COLUMN group_id INTEGER REFERENCES prompt_groups(id)"))
            db.commit()
            print("[OK] Migracao: coluna group_id adicionada em prompt_modulos")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migracao group_id prompt_modulos: {e}")

    if table_exists('prompt_modulos') and not column_exists('prompt_modulos', 'subgroup_id'):
        try:
            db.execute(text("ALTER TABLE prompt_modulos ADD COLUMN subgroup_id INTEGER REFERENCES prompt_subgroups(id)"))
            db.commit()
            print("[OK] Migracao: coluna subgroup_id adicionada em prompt_modulos")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migracao subgroup_id prompt_modulos: {e}")

    # Migracao: Adicionar colunas group_id e subgroup_id na tabela prompt_modulos_historico
    if table_exists('prompt_modulos_historico') and not column_exists('prompt_modulos_historico', 'group_id'):
        try:
            db.execute(text("ALTER TABLE prompt_modulos_historico ADD COLUMN group_id INTEGER REFERENCES prompt_groups(id)"))
            db.commit()
            print("[OK] Migracao: coluna group_id adicionada em prompt_modulos_historico")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migracao group_id prompt_modulos_historico: {e}")

    if table_exists('prompt_modulos_historico') and not column_exists('prompt_modulos_historico', 'subgroup_id'):
        try:
            db.execute(text("ALTER TABLE prompt_modulos_historico ADD COLUMN subgroup_id INTEGER REFERENCES prompt_subgroups(id)"))
            db.commit()
            print("[OK] Migracao: coluna subgroup_id adicionada em prompt_modulos_historico")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migracao subgroup_id prompt_modulos_historico: {e}")

    # Migração: Adicionar coluna documentos_processados na tabela geracoes_pecas
    if table_exists('geracoes_pecas') and not column_exists('geracoes_pecas', 'documentos_processados'):
        try:
            db.execute(text("ALTER TABLE geracoes_pecas ADD COLUMN documentos_processados JSON"))
            db.commit()
            print("[OK] Migração: coluna documentos_processados adicionada em geracoes_pecas")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração documentos_processados: {e}")
    
    # Migração: Adicionar coluna historico_chat na tabela geracoes_pecas
    if table_exists('geracoes_pecas') and not column_exists('geracoes_pecas', 'historico_chat'):
        try:
            db.execute(text("ALTER TABLE geracoes_pecas ADD COLUMN historico_chat JSON"))
            db.commit()
            print("[OK] Migração: coluna historico_chat adicionada em geracoes_pecas")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração historico_chat: {e}")
    
    # Migração: Adicionar coluna prompt_enviado na tabela geracoes_pecas
    if table_exists('geracoes_pecas') and not column_exists('geracoes_pecas', 'prompt_enviado'):
        try:
            db.execute(text("ALTER TABLE geracoes_pecas ADD COLUMN prompt_enviado TEXT"))
            db.commit()
            print("[OK] Migração: coluna prompt_enviado adicionada em geracoes_pecas")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração prompt_enviado: {e}")
    
    # Migração: Adicionar coluna resumo_consolidado na tabela geracoes_pecas
    if table_exists('geracoes_pecas') and not column_exists('geracoes_pecas', 'resumo_consolidado'):
        try:
            db.execute(text("ALTER TABLE geracoes_pecas ADD COLUMN resumo_consolidado TEXT"))
            db.commit()
            print("[OK] Migração: coluna resumo_consolidado adicionada em geracoes_pecas")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração resumo_consolidado: {e}")
    
    # Migração: Adicionar coluna tempo_processamento na tabela geracoes_pecas
    if table_exists('geracoes_pecas') and not column_exists('geracoes_pecas', 'tempo_processamento'):
        try:
            db.execute(text("ALTER TABLE geracoes_pecas ADD COLUMN tempo_processamento INTEGER"))
            db.commit()
            print("[OK] Migração: coluna tempo_processamento adicionada em geracoes_pecas")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração tempo_processamento: {e}")
    
    # Migração: Adicionar coluna condicao_ativacao na tabela prompt_modulos
    if table_exists('prompt_modulos') and not column_exists('prompt_modulos', 'condicao_ativacao'):
        try:
            db.execute(text("ALTER TABLE prompt_modulos ADD COLUMN condicao_ativacao TEXT"))
            db.commit()
            print("[OK] Migração: coluna condicao_ativacao adicionada em prompt_modulos")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração condicao_ativacao prompt_modulos: {e}")
    
    # Migração: Adicionar coluna condicao_ativacao na tabela prompt_modulos_historico
    if table_exists('prompt_modulos_historico') and not column_exists('prompt_modulos_historico', 'condicao_ativacao'):
        try:
            db.execute(text("ALTER TABLE prompt_modulos_historico ADD COLUMN condicao_ativacao TEXT"))
            db.commit()
            print("[OK] Migração: coluna condicao_ativacao adicionada em prompt_modulos_historico")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração condicao_ativacao prompt_modulos_historico: {e}")

    # Migração: Alterar tipo da coluna conteudo_gerado de JSON para TEXT
    if table_exists('geracoes_pecas'):
        try:
            # Verifica o tipo atual da coluna conteudo_gerado
            inspector = inspect(engine)
            columns = {col['name']: col for col in inspector.get_columns('geracoes_pecas')}

            if 'conteudo_gerado' in columns:
                col_type = str(columns['conteudo_gerado']['type']).upper()

                # Se a coluna for JSON, converte para TEXT
                if 'JSON' in col_type:
                    if is_sqlite:
                        # SQLite não suporta ALTER COLUMN TYPE diretamente, precisa recriar a tabela
                        # Por enquanto, apenas log - SQLite aceita qualquer tipo
                        print("[INFO] SQLite: conteudo_gerado ja aceita TEXT mesmo sendo JSON")
                    else:
                        # PostgreSQL: converte JSON para TEXT
                        db.execute(text("ALTER TABLE geracoes_pecas ALTER COLUMN conteudo_gerado TYPE TEXT USING conteudo_gerado::text"))
                        db.commit()
                        print("[OK] Migracao: coluna conteudo_gerado alterada de JSON para TEXT")
                else:
                    print("[INFO] Coluna conteudo_gerado ja e do tipo TEXT")
        except Exception as e:
            db.rollback()
            print(f"[AVISO] Migracao tipo conteudo_gerado: {e}")

    # Migração: Adicionar colunas faltantes em geracoes_pecas
    if table_exists('geracoes_pecas'):
        colunas_para_adicionar = [
            ('documentos_processados', 'JSON'),
            ('prompt_enviado', 'TEXT'),
            ('resumo_consolidado', 'TEXT'),
            ('historico_chat', 'JSON'),
            ('tempo_processamento', 'INTEGER'),
            ('dados_processo', 'JSON'),
        ]
        
        for coluna, tipo in colunas_para_adicionar:
            if not column_exists('geracoes_pecas', coluna):
                try:
                    db.execute(text(f"ALTER TABLE geracoes_pecas ADD COLUMN {coluna} {tipo}"))
                    db.commit()
                    print(f"[OK] Migração: coluna {coluna} adicionada em geracoes_pecas")
                except Exception as e:
                    db.rollback()
                    print(f"[WARN] Migração {coluna} geracoes_pecas: {e}")

    # Migração: Adicionar coluna is_primeiro_documento na tabela categorias_documento
    if table_exists('categorias_documento') and not column_exists('categorias_documento', 'is_primeiro_documento'):
        try:
            if is_sqlite:
                db.execute(text("ALTER TABLE categorias_documento ADD COLUMN is_primeiro_documento BOOLEAN DEFAULT 0"))
            else:
                db.execute(text("ALTER TABLE categorias_documento ADD COLUMN is_primeiro_documento BOOLEAN DEFAULT false"))
            db.commit()
            print("[OK] Migração: coluna is_primeiro_documento adicionada em categorias_documento")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração is_primeiro_documento: {e}")

    # Migração: Criar tabela geracoes_pedido_calculo
    if not table_exists('geracoes_pedido_calculo'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE geracoes_pedido_calculo (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        numero_cnj VARCHAR(30) NOT NULL,
                        numero_cnj_formatado VARCHAR(30),
                        dados_processo JSON,
                        dados_agente1 JSON,
                        dados_agente2 JSON,
                        documentos_baixados JSON,
                        conteudo_gerado TEXT,
                        historico_chat JSON,
                        arquivo_path VARCHAR(500),
                        modelo_usado VARCHAR(100),
                        tempo_processamento INTEGER,
                        usuario_id INTEGER REFERENCES users(id),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS geracoes_pedido_calculo (
                        id SERIAL PRIMARY KEY,
                        numero_cnj VARCHAR(30) NOT NULL,
                        numero_cnj_formatado VARCHAR(30),
                        dados_processo JSON,
                        dados_agente1 JSON,
                        dados_agente2 JSON,
                        documentos_baixados JSON,
                        conteudo_gerado TEXT,
                        historico_chat JSON,
                        arquivo_path VARCHAR(500),
                        modelo_usado VARCHAR(100),
                        tempo_processamento INTEGER,
                        usuario_id INTEGER REFERENCES users(id),
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            db.commit()
            print("[OK] Migração: tabela geracoes_pedido_calculo criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração geracoes_pedido_calculo: {e}")

    # Migração: Criar tabela feedbacks_pedido_calculo
    if not table_exists('feedbacks_pedido_calculo'):
        try:
            if is_sqlite:
                db.execute(text("""
                    CREATE TABLE feedbacks_pedido_calculo (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        geracao_id INTEGER NOT NULL REFERENCES geracoes_pedido_calculo(id),
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
                    CREATE TABLE IF NOT EXISTS feedbacks_pedido_calculo (
                        id SERIAL PRIMARY KEY,
                        geracao_id INTEGER NOT NULL REFERENCES geracoes_pedido_calculo(id),
                        usuario_id INTEGER NOT NULL REFERENCES users(id),
                        avaliacao VARCHAR(20) NOT NULL,
                        nota INTEGER,
                        comentario TEXT,
                        campos_incorretos JSON,
                        criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
            db.commit()
            print("[OK] Migração: tabela feedbacks_pedido_calculo criada")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração feedbacks_pedido_calculo: {e}")

    # Migração: Adicionar coluna extrato_subconta_pdf_base64 na tabela geracoes_prestacao_contas
    if table_exists('geracoes_prestacao_contas') and not column_exists('geracoes_prestacao_contas', 'extrato_subconta_pdf_base64'):
        try:
            db.execute(text("ALTER TABLE geracoes_prestacao_contas ADD COLUMN extrato_subconta_pdf_base64 TEXT"))
            db.commit()
            print("[OK] Migração: coluna extrato_subconta_pdf_base64 adicionada em geracoes_prestacao_contas")
        except Exception as e:
            db.rollback()
            print(f"[WARN] Migração extrato_subconta_pdf_base64: {e}")

    # Migração: Adicionar outras colunas faltantes em geracoes_prestacao_contas
    if table_exists('geracoes_prestacao_contas'):
        colunas_prestacao = [
            ('irregularidades', 'JSON'),
            ('documentos_anexos', 'JSON'),
            ('dados_processo_xml', 'JSON'),
            ('peticoes_relevantes', 'JSON'),
        ]

        for coluna, tipo in colunas_prestacao:
            if not column_exists('geracoes_prestacao_contas', coluna):
                try:
                    db.execute(text(f"ALTER TABLE geracoes_prestacao_contas ADD COLUMN {coluna} {tipo}"))
                    db.commit()
                    print(f"[OK] Migração: coluna {coluna} adicionada em geracoes_prestacao_contas")
                except Exception as e:
                    db.rollback()
                    print(f"[WARN] Migração {coluna} geracoes_prestacao_contas: {e}")

    seed_prompt_groups(db)


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
            print(f"[OK] Usuário admin '{ADMIN_USERNAME}' criado com sucesso!")
            print(f"   Senha inicial: {ADMIN_PASSWORD}")
            print(f"   [WARN]  Altere a senha no primeiro acesso!")
        else:
            print(f"[INFO]  Usuário admin '{ADMIN_USERNAME}' já existe.")
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
            print("[OK] Prompts e configurações de IA padrão criados!")
        else:
            print(f"[INFO]  {existing} prompt(s) já existem no banco.")
    finally:
        db.close()


def seed_prompt_groups(db: Session):
    """Cria grupos padrao e garante vinculacoes basicas."""
    import re

    def slugify(valor: str) -> str:
        if not valor:
            return ""
        slug = re.sub(r"[^a-z0-9]+", "_", valor.strip().lower())
        slug = slug.strip("_")
        return slug or "geral"

    grupos_padrao = [
        {"name": "PS", "slug": "ps", "order": 1},
        {"name": "PP", "slug": "pp", "order": 2},
        {"name": "DETRAN", "slug": "detran", "order": 3},
    ]

    grupos = {}
    for info in grupos_padrao:
        grupo = db.query(PromptGroup).filter(PromptGroup.slug == info["slug"]).first()
        if not grupo:
            grupo = PromptGroup(
                name=info["name"],
                slug=info["slug"],
                active=True,
                order=info["order"]
            )
            db.add(grupo)
            db.flush()
        grupos[info["slug"]] = grupo

    db.commit()

    grupo_ps = grupos.get("ps")
    if not grupo_ps:
        return

    # Vincula prompts de conteudo existentes ao grupo PS
    modulos_sem_grupo = db.query(PromptModulo).filter(
        PromptModulo.tipo == "conteudo",
        PromptModulo.group_id.is_(None)
    ).all()
    for modulo in modulos_sem_grupo:
        modulo.group_id = grupo_ps.id

    # Garante grupo nos historicos antigos
    db.query(PromptModuloHistorico).filter(
        PromptModuloHistorico.group_id.is_(None)
    ).update({PromptModuloHistorico.group_id: grupo_ps.id}, synchronize_session=False)

    # Cria subgrupos a partir das categorias existentes (PS)
    # Apenas modulos ativos sao considerados para criar subgrupos
    categorias = db.query(PromptModulo.categoria).filter(
        PromptModulo.tipo == "conteudo",
        PromptModulo.categoria.isnot(None),
        PromptModulo.group_id == grupo_ps.id,
        PromptModulo.ativo == True
    ).distinct().all()

    for (categoria,) in categorias:
        slug = slugify(categoria)
        if not slug:
            continue
        subgrupo = db.query(PromptSubgroup).filter(
            PromptSubgroup.group_id == grupo_ps.id,
            PromptSubgroup.slug == slug
        ).first()
        if not subgrupo:
            subgrupo = PromptSubgroup(
                group_id=grupo_ps.id,
                name=categoria,
                slug=slug,
                active=True,
                order=0
            )
            db.add(subgrupo)
            db.flush()

        db.query(PromptModulo).filter(
            PromptModulo.tipo == "conteudo",
            PromptModulo.group_id == grupo_ps.id,
            PromptModulo.subgroup_id.is_(None),
            PromptModulo.categoria == categoria,
            PromptModulo.ativo == True
        ).update({PromptModulo.subgroup_id: subgrupo.id}, synchronize_session=False)

    # Garante grupos permitidos e grupo padrao para usuarios
    usuarios = db.query(User).all()
    for usuario in usuarios:
        if not usuario.default_group_id:
            usuario.default_group_id = grupo_ps.id
        if grupo_ps not in usuario.allowed_groups:
            usuario.allowed_groups.append(grupo_ps)

    db.commit()


def seed_prompt_modulos():
    """Cria os módulos de prompt do gerador de peças se não existirem"""
    from admin.seed_prompts import PROMPT_SYSTEM_GERADOR_PECAS
    
    db = SessionLocal()
    try:
        # Verifica se já existem módulos BASE
        existing_base = db.query(PromptModulo).filter(
            PromptModulo.tipo == "base"
        ).count()
        
        if existing_base == 0:
            # Cria o módulo BASE principal com o prompt do sistema
            modulo_base = PromptModulo(
                tipo="base",
                categoria=None,
                subcategoria=None,
                nome="system_prompt",
                titulo="Prompt de Sistema - Gerador de Peças",
                conteudo=PROMPT_SYSTEM_GERADOR_PECAS,
                palavras_chave=[],
                tags=["base", "sistema", "gerador"],
                ativo=True,
                ordem=0,
                versao=1
            )
            db.add(modulo_base)
            
            # Cria módulos de PEÇA para cada tipo
            tipos_peca = [
                {
                    "categoria": "contestacao",
                    "nome": "contestacao",
                    "titulo": "Contestação",
                    "conteudo": """## ESTRUTURA DA CONTESTAÇÃO

1. **ENDEREÇAMENTO** - Juízo competente
2. **QUALIFICAÇÃO** - Identificação do Estado como réu
3. **PRELIMINARES** (se houver):
   - Ilegitimidade passiva
   - Incompetência
   - Litispendência/Coisa julgada
   - Prescrição/Decadência
4. **MÉRITO**:
   - Impugnação específica dos fatos
   - Fundamentação jurídica
   - Jurisprudência aplicável
5. **PEDIDOS**:
   - Acolhimento das preliminares (se houver)
   - Improcedência dos pedidos
   - Condenação em honorários

Use linguagem formal, técnico-jurídica, com parágrafos justificados e citações em recuo."""
                },
                {
                    "categoria": "recurso_apelacao",
                    "nome": "recurso_apelacao",
                    "titulo": "Recurso de Apelação",
                    "conteudo": """## ESTRUTURA DO RECURSO DE APELAÇÃO

1. **ENDEREÇAMENTO** - Tribunal de Justiça de MS
2. **TEMPESTIVIDADE** - Demonstrar prazo
3. **PREPARO** - Isenção do Estado
4. **RAZÕES RECURSAIS**:
   - Síntese da sentença
   - Preliminares (nulidades, cerceamento)
   - Mérito recursal
   - Error in procedendo / Error in judicando
5. **PEDIDOS**:
   - Conhecimento e provimento
   - Reforma da sentença
   - Inversão dos ônus sucumbenciais

Demonstre o error in judicando ou procedendo de forma clara e objetiva."""
                },
                {
                    "categoria": "contrarrazoes",
                    "nome": "contrarrazoes",
                    "titulo": "Contrarrazões de Recurso",
                    "conteudo": """## ESTRUTURA DAS CONTRARRAZÕES

1. **ENDEREÇAMENTO** - Tribunal competente
2. **SÍNTESE DO RECURSO** - Resumo das razões do apelante
3. **PRELIMINARES DE INADMISSIBILIDADE** (se houver):
   - Intempestividade
   - Irregularidade formal
   - Falta de interesse recursal
4. **MÉRITO**:
   - Refutação ponto a ponto
   - Manutenção da sentença
   - Jurisprudência favorável
5. **PEDIDOS**:
   - Não conhecimento (preliminares)
   - Desprovimento
   - Majoração de honorários

Rebata cada argumento do recurso de forma sistemática."""
                },
                {
                    "categoria": "parecer",
                    "nome": "parecer",
                    "titulo": "Parecer Jurídico",
                    "conteudo": """## ESTRUTURA DO PARECER JURÍDICO

1. **EMENTA** - Síntese da consulta e conclusão
2. **RELATÓRIO** - Fatos e documentos analisados
3. **FUNDAMENTAÇÃO**:
   - Análise legal
   - Doutrina aplicável
   - Jurisprudência pertinente
   - Aspectos técnicos (se houver NAT)
4. **CONCLUSÃO**:
   - Resposta objetiva à consulta
   - Recomendações práticas
   - Encaminhamentos sugeridos

Seja objetivo e fundamente cada conclusão com base legal."""
                }
            ]
            
            for tipo_peca in tipos_peca:
                modulo = PromptModulo(
                    tipo="peca",
                    categoria=tipo_peca["categoria"],
                    subcategoria=None,
                    nome=tipo_peca["nome"],
                    titulo=tipo_peca["titulo"],
                    conteudo=tipo_peca["conteudo"],
                    palavras_chave=[tipo_peca["categoria"]],
                    tags=["peca", tipo_peca["categoria"]],
                    ativo=True,
                    ordem=0,
                    versao=1
                )
                db.add(modulo)
            
            db.commit()
            print("[OK] Módulos de prompt do gerador de peças criados!")
        else:
            print(f"[INFO]  {existing_base} módulo(s) BASE já existem no banco.")
    finally:
        db.close()


def seed_categorias_resumo_json():
    """Cria as categorias de formato de resumo JSON padrão"""
    
    db = SessionLocal()
    try:
        # Verifica se já existem categorias
        existing = db.query(CategoriaResumoJSON).count()
        
        if existing == 0:
            # Formato JSON residual (padrão para todos os documentos)
            formato_residual = '''{
  "tipo_documento": "string - tipo identificado do documento",
  "partes": {
    "autor": "string ou null",
    "reu": "string ou null"
  },
  "pedido_objeto": "string - o que está sendo requerido ou discutido",
  "diagnostico_cid": "string ou null - diagnóstico/CID se mencionado",
  "tratamento_solicitado": {
    "tipo": "medicamento | cirurgia | procedimento | outro | null",
    "descricao": "string - descrição do tratamento",
    "medicamento": {
      "nome_comercial": "string ou null",
      "principio_ativo": "string ou null",
      "posologia": "string ou null",
      "incorporado_sus": "boolean ou null",
      "componente_sus": "string ou null - Básico/Estratégico/Especializado"
    },
    "cirurgia": {
      "procedimento": "string ou null",
      "urgente": "boolean ou null",
      "responsabilidade": "string ou null"
    }
  },
  "argumentos_principais": ["string - lista de argumentos apresentados"],
  "decisao_dispositivo": "string ou null - o que foi decidido, prazos, multas",
  "processo_origem": "string ou null - número CNJ do processo de origem (se Agravo)",
  "pontos_relevantes": ["string - outros pontos importantes"],
  "irrelevante": false
}'''
            
            instrucoes_residual = """Este é o formato padrão para todos os documentos.
Preencha TODOS os campos aplicáveis. Use null para campos não encontrados no documento.
Para campos de lista (argumentos_principais, pontos_relevantes), use array vazio [] se não houver conteúdo.
O campo "irrelevante" deve ser true apenas se o documento for meramente administrativo (procuração, AR, etc)."""
            
            categoria_residual = CategoriaResumoJSON(
                nome="residual",
                titulo="Formato Padrão (Residual)",
                descricao="Formato JSON padrão aplicado a todos os documentos que não pertencem a uma categoria específica.",
                codigos_documento=[],
                formato_json=formato_residual,
                instrucoes_extracao=instrucoes_residual,
                is_residual=True,
                ativo=True,
                ordem=999
            )
            db.add(categoria_residual)
            
            # Categoria para Petições
            formato_peticoes = '''{
  "tipo_documento": "string - Petição Inicial | Petição Intermediária | Contestação | etc",
  "partes": {
    "autor": "string",
    "reu": "string",
    "advogado_autor": "string ou null",
    "procurador_reu": "string ou null"
  },
  "valor_causa": "string ou null",
  "pedidos": [
    {
      "tipo": "principal | subsidiario | tutela_urgencia",
      "descricao": "string - descrição do pedido"
    }
  ],
  "fundamentos_juridicos": ["string - dispositivos legais citados"],
  "narrativa_fatos": "string - resumo da narrativa fática",
  "tutela_urgencia": {
    "requerida": "boolean",
    "tipo": "liminar | antecipacao_tutela | null",
    "fundamento_urgencia": "string ou null - periculum in mora alegado"
  },
  "provas_indicadas": ["string - provas documentais mencionadas"],
  "diagnostico_cid": "string ou null",
  "tratamento_solicitado": {
    "tipo": "medicamento | cirurgia | procedimento | outro | null",
    "descricao": "string ou null",
    "medicamento": {
      "nome_comercial": "string ou null",
      "principio_ativo": "string ou null",
      "posologia": "string ou null"
    }
  },
  "irrelevante": false
}'''
            
            categoria_peticoes = CategoriaResumoJSON(
                nome="peticoes",
                titulo="Petições",
                descricao="Formato para petições iniciais, intermediárias e contestações.",
                codigos_documento=[500, 510, 9500, 8320],  # Petição Inicial, Petição Intermediária, Petição, Contestação
                formato_json=formato_peticoes,
                instrucoes_extracao="Extraia TODOS os pedidos formulados, separando por tipo (principal, subsidiário, tutela de urgência). Liste todos os fundamentos jurídicos citados.",
                is_residual=False,
                ativo=True,
                ordem=1
            )
            db.add(categoria_peticoes)
            
            # Categoria para Decisões Judiciais
            formato_decisoes = '''{
  "tipo_documento": "string - Sentença | Decisão Interlocutória | Despacho | Acórdão",
  "juiz_relator": "string ou null",
  "data_decisao": "string ou null - data da decisão",
  "dispositivo": {
    "resultado": "procedente | improcedente | parcialmente_procedente | deferido | indeferido | outro",
    "descricao": "string - descrição do que foi decidido"
  },
  "fundamentacao_resumo": "string - principais razões de decidir",
  "obrigacoes_impostas": [
    {
      "obrigado": "string - quem deve cumprir",
      "obrigacao": "string - o que deve fazer",
      "prazo": "string ou null",
      "multa": "string ou null - astreintes se houver"
    }
  ],
  "honorarios": {
    "fixados": "boolean",
    "percentual_valor": "string ou null"
  },
  "recurso_cabivel": "string ou null",
  "transitou_julgado": "boolean ou null",
  "irrelevante": false
}'''
            
            categoria_decisoes = CategoriaResumoJSON(
                nome="decisoes",
                titulo="Decisões Judiciais",
                descricao="Formato para sentenças, decisões interlocutórias, despachos e acórdãos.",
                codigos_documento=[8, 6, 15, 137, 34, 44],  # Sentença, Despacho, Decisões Interlocutórias, etc
                formato_json=formato_decisoes,
                instrucoes_extracao="Identifique claramente o DISPOSITIVO da decisão (procedente/improcedente/etc). Liste TODAS as obrigações impostas com prazos e multas.",
                is_residual=False,
                ativo=True,
                ordem=2
            )
            db.add(categoria_decisoes)
            
            # Categoria para Recursos
            formato_recursos = '''{
  "tipo_documento": "string - Recurso de Apelação | Contrarrazões | Agravo de Instrumento | Embargos",
  "recorrente": "string",
  "recorrido": "string",
  "decisao_recorrida": "string - qual decisão está sendo impugnada",
  "teses_recursais": [
    {
      "tipo": "preliminar | merito",
      "argumento": "string - descrição do argumento"
    }
  ],
  "pedido_recursal": "string - o que pede (reforma, anulação, etc)",
  "processo_origem": "string ou null - número CNJ do processo de origem (para Agravo)",
  "efeito_suspensivo": {
    "requerido": "boolean",
    "fundamento": "string ou null"
  },
  "irrelevante": false
}'''
            
            categoria_recursos = CategoriaResumoJSON(
                nome="recursos",
                titulo="Recursos",
                descricao="Formato para recursos de apelação, contrarrazões, agravos e embargos.",
                codigos_documento=[8335, 8305],  # Recurso de Apelação, Contrarrazões de Apelação
                formato_json=formato_recursos,
                instrucoes_extracao="Liste TODAS as teses recursais separando preliminares de mérito. Para Agravo de Instrumento, SEMPRE identifique o processo de origem.",
                is_residual=False,
                ativo=True,
                ordem=3
            )
            db.add(categoria_recursos)
            
            # Categoria para Pareceres Técnicos (NAT/CATES)
            formato_pareceres = '''{
  "tipo_documento": "string - Parecer do NAT | Parecer do CATES | Laudo Pericial | Parecer do MP",
  "orgao_emissor": "string",
  "data_parecer": "string ou null",
  "objeto_consulta": "string - qual foi a pergunta/demanda",
  "medicamento_procedimento_analisado": {
    "nome": "string",
    "principio_ativo": "string ou null",
    "indicacao_solicitada": "string ou null"
  },
  "analise_incorporacao_sus": {
    "incorporado": "boolean ou null",
    "componente": "string ou null - Básico/Estratégico/Especializado",
    "para_quais_indicacoes": "string ou null",
    "caso_enquadra": "boolean ou null - o caso do autor se enquadra?"
  },
  "alternativas_terapeuticas": ["string - alternativas disponíveis no SUS"],
  "evidencia_cientifica": "string ou null - análise de eficácia/segurança",
  "conclusao": "string - conclusão/recomendação do parecer",
  "ressalvas": ["string - ressalvas ou condicionantes"],
  "irrelevante": false
}'''
            
            categoria_pareceres = CategoriaResumoJSON(
                nome="pareceres",
                titulo="Pareceres Técnicos",
                descricao="Formato para pareceres do NAT, CATES, NATJus, laudos periciais e pareceres do MP.",
                codigos_documento=[8369, 8333, 30],  # Laudo Pericial, Manifestação do MP, Peças do MP
                formato_json=formato_pareceres,
                instrucoes_extracao="TRANSCREVA a conclusão do parecer. Identifique claramente se o medicamento/procedimento está incorporado ao SUS e para quais indicações.",
                is_residual=False,
                ativo=True,
                ordem=4
            )
            db.add(categoria_pareceres)
            
            db.commit()
            print("[OK] Categorias de formato de resumo JSON criadas!")
        else:
            print(f"[INFO]  {existing} categoria(s) de resumo JSON já existem no banco.")
    finally:
        db.close()


def init_database():
    """Inicializa o banco de dados completo"""
    print("[*] Inicializando banco de dados...")
    wait_for_db()  # Aguarda o banco ficar disponível
    create_tables()
    run_migrations()  # Aplica migrações
    seed_admin()
    seed_prompts()
    seed_prompt_modulos()  # Cria módulos do gerador de peças
    seed_categorias_resumo_json()  # Cria categorias de formato JSON
    print("[OK] Banco de dados inicializado!")


if __name__ == "__main__":
    init_database()
