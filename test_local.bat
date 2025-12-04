@echo off
echo Iniciando Portal PGE-MS (Local)...
echo.
echo Certifique-se de que o ambiente virtual esta ativado se necessario.
echo.
echo Iniciando Backend (FastAPI)...
start cmd /k "uvicorn main:app --reload --host 0.0.0.0 --port 8000"
echo.
echo Aguardando inicializacao...
timeout /t 5
echo.
echo Abrindo Frontend no navegador...
start http://localhost:8000/matriculas/
echo.
echo Pressione qualquer tecla para encerrar o script (o servidor continuara rodando).
pause
