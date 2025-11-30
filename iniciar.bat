@echo off
chcp 65001 >nul
title Portal PGE-MS
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    PORTAL PGE-MS                             ║
echo ║          Procuradoria-Geral do Estado de MS                  ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

:: ============================================================
:: FASE 1: Verificar Python
:: ============================================================
echo [1/5] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ERRO: Python nao encontrado!
    echo   Instale Python 3.10+ em: https://python.org/downloads
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo       Python !PYVER! encontrado.

:: ============================================================
:: FASE 2: Criar/Verificar ambiente virtual
:: ============================================================
echo [2/5] Verificando ambiente virtual...
if not exist ".venv\Scripts\activate.bat" (
    echo       Criando ambiente virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo   ERRO: Falha ao criar ambiente virtual.
        pause
        exit /b 1
    )
    echo       Ambiente virtual criado!
    set INSTALL_DEPS=1
) else (
    echo       Ambiente virtual OK.
    set INSTALL_DEPS=0
)

:: Ativa o ambiente virtual
call .venv\Scripts\activate.bat

:: ============================================================
:: FASE 3: Instalar/Verificar dependências
:: ============================================================
echo [3/5] Verificando dependencias Python...

:: Verifica se fastapi está instalado
python -c "import fastapi" >nul 2>&1
if errorlevel 1 set INSTALL_DEPS=1

:: Verifica se bcrypt está instalado
python -c "import bcrypt" >nul 2>&1
if errorlevel 1 set INSTALL_DEPS=1

if "!INSTALL_DEPS!"=="1" (
    echo       Instalando dependencias ^(pode demorar alguns minutos^)...
    pip install --upgrade pip --quiet >nul 2>&1
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo   ERRO: Falha ao instalar dependencias.
        echo   Tente manualmente: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo       Dependencias instaladas!
) else (
    echo       Dependencias OK.
)

:: ============================================================
:: FASE 4: Criar .env se não existir
:: ============================================================
echo [4/5] Verificando configuracao...
if not exist ".env" (
    copy .env.example .env >nul 2>&1
    echo       Arquivo .env criado a partir do exemplo.
) else (
    echo       Arquivo .env OK.
)

:: ============================================================
:: FASE 5: Verificar imports
:: ============================================================
echo [5/5] Verificando aplicacao...
python -c "from main import app" >nul 2>&1
if errorlevel 1 (
    echo.
    echo   ERRO: Falha ao carregar aplicacao.
    echo   Execute: python -c "from main import app"
    echo   para ver o erro detalhado.
    echo.
    pause
    exit /b 1
)
echo       Aplicacao OK!

:: ============================================================
:: INICIAR SERVIDOR
:: ============================================================
echo.
echo ══════════════════════════════════════════════════════════════
echo.
echo   Portal:    http://localhost:8000
echo   API Docs:  http://localhost:8000/docs
echo   Login:     admin / admin
echo.
echo ══════════════════════════════════════════════════════════════
echo.
echo   Pressione Ctrl+C para encerrar o servidor
echo.

python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

echo.
echo Servidor encerrado.
pause
