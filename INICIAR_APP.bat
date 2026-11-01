@echo off
title Sports Quant App - Cuantitativo de Apuestas
echo ======================================================================
echo                  INICIANDO SPORTS QUANT APP
echo ======================================================================
echo.

cd /d "C:\Users\ALVARO\Desktop\proyectos\inversiones\apuestas_prompt\sports_quant_app"

:: Comprobar si el puerto 8501 ya esta activo
netstat -ano | findstr /R ":8501.*LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] La aplicacion ya esta ejecutandose en segundo plano.
    echo Abriendo en tu navegador...
    start "" "http://localhost:8501"
    timeout /t 3 >nul
    exit /b 0
)

echo Iniciando el servidor Streamlit en el puerto 8501...
start "" "http://localhost:8501"
"C:\Users\ALVARO\Desktop\proyectos\inversiones\app_nba\.venv\Scripts\streamlit.exe" run dashboard.py --server.port 8501 --server.headless true
pause
