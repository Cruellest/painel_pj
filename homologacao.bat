@echo off
title Portal PGE - HOMOLOGACAO
color 0E

echo ========================================
echo    PORTAL PGE - AMBIENTE HOMOLOGACAO
echo ========================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo Ambiente virtual nao encontrado!
    echo Execute: python -m venv .venv
    pause
    exit /b 1
)

echo Iniciando servidor de homologacao...
echo Acesse: http://localhost:8000
echo.
echo [CTRL+C para encerrar]
echo.

python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
