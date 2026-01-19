@echo off
echo ========================================
echo   Reset do Cache de Inicializacao DB
echo ========================================
echo.

cd /d "%~dp0"

echo Removendo cache de inicializacao...
del /f /q "database\.db_initialized" 2>nul

echo.
echo Cache removido! Na proxima execucao do servidor,
echo o banco sera verificado e reinicializado se necessario.
echo.
pause
