@echo off
cd /d %~dp0
echo.
echo ========================================
echo    Portal PGE-MS - Iniciando...
echo ========================================
echo.
echo Acesse: http://localhost:8000
echo.
start http://localhost:8000
.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8000
echo.
echo ========================================
echo    Servidor encerrado ou erro!
echo ========================================
pause
