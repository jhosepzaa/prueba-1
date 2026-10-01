@echo off
rem Abre el programa de diseno de cimentaciones.
rem Arranca el servidor (API + interfaz ya compilada) y abre el navegador.
rem Para cerrarlo: cierre esta ventana o pulse Ctrl+C en ella.
chcp 65001 >nul
cd /d "%~dp0"
if not exist "ui\dist\index.html" (
  echo No existe ui\dist: compile la interfaz una vez con
  echo    cd ui ^&^& set NODE_OPTIONS=--max-old-space-size=4096 ^&^& npm run build
  pause
  exit /b 1
)
echo Iniciando el servidor en http://localhost:8000 ...
start "" /b cmd /c "timeout /t 3 >nul & start http://localhost:8000"
py -3 -m uvicorn api.server:app --port 8000
pause
