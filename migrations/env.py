# migrations/env.py
"""
Configuracao do ambiente Alembic para migrations.

Este arquivo importa todos os modelos do projeto para que
o autogenerate funcione corretamente.

Autor: LAB/PGE-MS
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Adiciona o diretorio raiz ao path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carrega variaveis de ambiente do .env
from dotenv import load_dotenv
load_dotenv()

# Importa a configuracao do banco de dados
from config import DATABASE_URL

# Importa o Base e todos os models
from database.connection import Base

# ==================================================
# IMPORTA TODOS OS MODELS PARA AUTOGENERATE
# ==================================================
# IMPORTANTE: Adicionar aqui todos os modelos do projeto
# para que o Alembic possa detectar mudancas automaticamente.

# Autenticacao (importa User e modelos relacionados)
from auth.models import User

# Admin - Prompts e Configuracoes
try:
    from admin.models import PromptConfig, ConfiguracaoIA
except ImportError:
    pass

try:
    from admin.models_prompts import PromptModulo
except ImportError:
    pass

try:
    from admin.models_prompt_groups import PromptGroup
except ImportError:
    pass

try:
    from admin.models_performance import PerformanceLog, RouteSystemMap
except ImportError:
    pass

try:
    from admin.models_gemini_log import GeminiCallLog
except ImportError:
    pass

# Sistemas
try:
    from sistemas.gerador_pecas.models import (
        TipoPeca, Pergunta, Prompt, Processo, Documento
    )
except ImportError:
    pass

try:
    from sistemas.pedido_calculo.models import PedidoCalculo
except ImportError:
    pass

try:
    from sistemas.prestacao_contas.models import PrestacaoContas
except ImportError:
    pass

try:
    from sistemas.bert_training.models import (
        BertTrainingRun, BertTrainingEpochLog, BertTrainingPrediction
    )
except ImportError:
    pass

try:
    from sistemas.classificador_documentos.models import (
        ClassificadorDocumentosJob, ClassificadorDocumentoResult
    )
except ImportError:
    pass

try:
    from sistemas.relatorio_cumprimento.models import RelatorioCumprimento
except ImportError:
    pass

# Servicos
try:
    from services.text_normalizer.models import TextNormalizerPattern
except ImportError:
    pass

# ==================================================
# CONFIGURACAO DO ALEMBIC
# ==================================================

# Objeto de configuracao do Alembic (do alembic.ini)
config = context.config

# Configura logging do arquivo ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata dos models para autogenerate
target_metadata = Base.metadata

# Substitui sqlalchemy.url com a URL do .env
config.set_main_option("sqlalchemy.url", DATABASE_URL)


def run_migrations_offline() -> None:
    """
    Executa migrations em modo 'offline'.

    Gera SQL puro sem conexao com o banco.
    Util para revisar as mudancas antes de aplicar.

    Uso: alembic upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Executa migrations em modo 'online'.

    Conecta ao banco e aplica as mudancas diretamente.

    Uso: alembic upgrade head
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # Ignora tabelas que nao sao gerenciadas pelo Alembic
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
