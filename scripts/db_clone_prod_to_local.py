#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para clonar banco de PRODUCAO para DESENVOLVIMENTO
==========================================================
Este script faz dump do banco de producao e restaura no banco de desenvolvimento.

Uso:
    python scripts/db_clone_prod_to_local.py              # Clone completo
    python scripts/db_clone_prod_to_local.py --schema     # Apenas schema
    python scripts/db_clone_prod_to_local.py --minimal    # Schema + essenciais

Requisitos:
    - pg_dump e psql instalados (vem com PostgreSQL)
    - URLs de producao e desenvolvimento configuradas no .env
"""

import os
import sys
import subprocess
import tempfile
import gzip
import re
from pathlib import Path
from datetime import datetime

# Cores para terminal (funciona em Windows 10+)
os.system('')  # Habilita ANSI no Windows

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def print_color(color, message):
    print(f"{color}{message}{RESET}")


def get_db_urls():
    """Obtem URLs dos bancos de producao e desenvolvimento"""
    env_path = Path(__file__).parent.parent / '.env'

    prod_url = None
    dev_url = None

    # Primeiro, tenta variaveis de ambiente
    prod_url = os.getenv('PROD_DATABASE_URL')
    dev_url = os.getenv('DATABASE_URL')

    # Le do .env
    if env_path.exists():
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # URL de desenvolvimento (linha ativa)
                if line.startswith('DATABASE_URL=') and not line.startswith('#'):
                    dev_url = line.split('=', 1)[1].strip()

                # URL de producao (linha comentada com "PRODUCAO" ou "yamanote")
                if ('PRODUCAO' in line.upper() or 'yamanote' in line.lower()) and 'postgresql' in line:
                    match = re.search(r'postgresql://[^\s]+', line)
                    if match:
                        prod_url = match.group(0)

    return prod_url, dev_url


def mask_password(url):
    """Mascara a senha na URL para exibicao"""
    return re.sub(r':([^:@]+)@', ':****@', url)


def check_psql_installed():
    """Verifica se pg_dump e psql estao instalados"""
    try:
        subprocess.run(['pg_dump', '--version'], capture_output=True, check=True)
        subprocess.run(['psql', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def test_connection(url, name):
    """Testa conexao com um banco"""
    try:
        result = subprocess.run(
            ['psql', url, '-c', 'SELECT 1'],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def dump_production(prod_url, mode='full'):
    """Faz dump do banco de producao"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    dump_dir = Path(__file__).parent.parent / 'dumps'
    dump_dir.mkdir(exist_ok=True)
    dump_file = dump_dir / f'prod_dump_{timestamp}.sql'

    print_color(YELLOW, f'\nFazendo dump de producao ({mode})...')

    cmd = ['pg_dump', prod_url, '--no-owner', '--no-privileges']

    if mode == 'schema':
        cmd.extend(['--schema-only', '--no-comments'])
    elif mode == 'full':
        cmd.extend(['--clean', '--if-exists'])

    cmd.extend(['-f', str(dump_file)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print_color(RED, f'Erro no pg_dump: {result.stderr}')
            return None
    except subprocess.TimeoutExpired:
        print_color(RED, 'Timeout no dump (>10min)')
        return None
    except FileNotFoundError:
        print_color(RED, 'pg_dump nao encontrado. Instale o PostgreSQL.')
        return None

    # Se modo minimal, adiciona dados das tabelas essenciais
    if mode == 'minimal':
        print_color(YELLOW, 'Adicionando dados das tabelas essenciais...')
        essential_tables = ['users', 'prompt_configs', 'configuracoes_ia',
                          'prompt_groups', 'prompt_subgroups', 'prompt_modulos']

        with open(dump_file, 'a', encoding='utf-8') as f:
            f.write('\n-- Dados das tabelas essenciais\n')

        for table in essential_tables:
            print(f'  Exportando: {table}')
            try:
                result = subprocess.run(
                    ['pg_dump', prod_url, '--data-only', '--no-owner', '--table', table],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0 and result.stdout:
                    with open(dump_file, 'a', encoding='utf-8') as f:
                        f.write(result.stdout)
            except Exception:
                print(f'    (tabela {table} nao encontrada, ignorando)')

    # Compacta
    print_color(YELLOW, 'Compactando...')
    gz_file = str(dump_file) + '.gz'
    with open(dump_file, 'rb') as f_in:
        with gzip.open(gz_file, 'wb') as f_out:
            f_out.writelines(f_in)
    dump_file.unlink()  # Remove arquivo nao compactado

    size = Path(gz_file).stat().st_size / (1024 * 1024)
    print_color(GREEN, f'Dump criado: {gz_file} ({size:.2f} MB)')

    return gz_file


def restore_to_dev(dump_file, dev_url):
    """Restaura dump no banco de desenvolvimento"""
    print_color(YELLOW, '\nRestaurando no banco de desenvolvimento...')

    # Descompacta se necessario
    if dump_file.endswith('.gz'):
        print('  Descompactando...')
        temp_file = tempfile.NamedTemporaryFile(mode='wb', suffix='.sql', delete=False)
        with gzip.open(dump_file, 'rb') as f_in:
            temp_file.write(f_in.read())
        temp_file.close()
        sql_file = temp_file.name
    else:
        sql_file = dump_file

    try:
        # Extrai nome do banco da URL
        db_match = re.search(r'/([^/?]+)(\?|$)', dev_url)
        db_name = db_match.group(1) if db_match else 'railway'

        # URL base (sem o nome do banco) para conectar ao postgres
        base_url = re.sub(r'/[^/?]+(\?|$)', '/postgres', dev_url)

        # Drop e recria banco
        print('  Limpando banco de desenvolvimento...')

        # Desconecta usuarios
        subprocess.run(
            ['psql', base_url, '-c',
             f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();"],
            capture_output=True, timeout=30
        )

        # Drop e recria
        subprocess.run(
            ['psql', base_url, '-c', f"DROP DATABASE IF EXISTS {db_name};"],
            capture_output=True, timeout=30
        )
        subprocess.run(
            ['psql', base_url, '-c', f"CREATE DATABASE {db_name};"],
            capture_output=True, timeout=30
        )

        # Restaura dump
        print('  Importando dados...')
        result = subprocess.run(
            ['psql', dev_url, '-f', sql_file],
            capture_output=True, text=True, timeout=600
        )

        # Ignora warnings, so reporta erros criticos
        if result.returncode != 0:
            errors = [l for l in result.stderr.split('\n') if 'ERROR' in l and 'does not exist' not in l]
            if errors:
                print_color(YELLOW, 'Alguns erros durante restauracao (podem ser ignorados):')
                for e in errors[:5]:
                    print(f'  {e}')

    finally:
        # Limpa arquivo temporario
        if dump_file.endswith('.gz') and os.path.exists(sql_file):
            os.unlink(sql_file)

    print_color(GREEN, 'Restauracao concluida!')
    return True


def main():
    print_color(YELLOW, '=' * 60)
    print_color(YELLOW, 'Clone: Producao -> Desenvolvimento')
    print_color(YELLOW, '=' * 60)

    # Parse argumentos
    mode = 'full'
    if '--schema' in sys.argv:
        mode = 'schema'
    elif '--minimal' in sys.argv:
        mode = 'minimal'

    print(f'\nModo: {mode}')

    # Verifica pg_dump/psql
    if not check_psql_installed():
        print_color(RED, '\nERRO: pg_dump/psql nao encontrados!')
        print('\nInstale o PostgreSQL:')
        print('  Windows: https://www.postgresql.org/download/windows/')
        print('  Adicione ao PATH: C:\\Program Files\\PostgreSQL\\17\\bin')
        sys.exit(1)

    # Obtem URLs
    prod_url, dev_url = get_db_urls()

    if not prod_url:
        print_color(RED, '\nERRO: URL de producao nao encontrada!')
        print('\nAdicione no .env (pode ser comentada):')
        print('  # PRODUCAO: DATABASE_URL=postgresql://...')
        sys.exit(1)

    if not dev_url:
        print_color(RED, '\nERRO: URL de desenvolvimento nao encontrada!')
        print('\nConfigure DATABASE_URL no .env')
        sys.exit(1)

    # Exibe URLs (mascaradas)
    print(f'\nProducao: {mask_password(prod_url)}')
    print(f'Desenvolvimento: {mask_password(dev_url)}')

    # Verifica conexoes
    print('\nTestando conexoes...')

    if not test_connection(prod_url, 'producao'):
        print_color(RED, 'ERRO: Nao foi possivel conectar ao banco de producao')
        sys.exit(1)
    print_color(GREEN, '  Producao: OK')

    if not test_connection(dev_url, 'desenvolvimento'):
        print_color(RED, 'ERRO: Nao foi possivel conectar ao banco de desenvolvimento')
        sys.exit(1)
    print_color(GREEN, '  Desenvolvimento: OK')

    # Confirma
    print_color(RED, '\nATENCAO: Isso vai APAGAR todos os dados do banco de DESENVOLVIMENTO!')
    print('(O banco de producao NAO sera alterado - apenas leitura)')
    response = input('\nContinuar? (s/N) ').strip().lower()
    if response != 's':
        print('Operacao cancelada.')
        sys.exit(0)

    # Executa
    dump_file = dump_production(prod_url, mode)
    if not dump_file:
        sys.exit(1)

    restore_to_dev(dump_file, dev_url)

    print_color(GREEN, '\n' + '=' * 60)
    print_color(GREEN, 'Clone concluido com sucesso!')
    print_color(GREEN, '=' * 60)
    print('\nProximos passos:')
    print('  1. Executar migrations: python -m database.init_db')
    print('  2. Iniciar servidor: uvicorn main:app --reload')


if __name__ == '__main__':
    main()
