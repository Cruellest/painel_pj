@echo off
chcp 65001 >nul
title Portal PGE-MS - Dev Server
cd /d "%~dp0"

echo.
echo ========================================
echo    Portal PGE-MS - Dev Server
echo ========================================
echo.

:: Ativa ambiente virtual
call .venv\Scripts\activate.bat

:: Limpa cache Python para garantir codigo atualizado
echo Limpando cache Python...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d" 2>nul
del /s /q *.pyc 2>nul
echo Cache limpo!
echo.

:: Exibe URLs
echo   Portal:           http://localhost:8000
echo   Prestacao Contas: http://localhost:8000/prestacao-contas
echo   Gerador Pecas:    http://localhost:8000/gerador-pecas
echo   API Docs:         http://localhost:8000/docs
echo.
echo   Pressione Ctrl+C para encerrar
echo ========================================
echo.

:: Inicia servidor com reload
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

echo.
echo Servidor encerrado.
pause
