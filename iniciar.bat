@echo off
title Asistente de Gmail
cd /d "%~dp0"

echo.
echo  ============================================
echo   Asistente Personal de Gmail
echo  ============================================
echo.


:: 1. Verificar Python

python --version >NUL 2>&1
if errorlevel 1 (
    cls
    echo.
    echo  ============================================
    echo   ERROR: Python no esta instalado
    echo  ============================================
    echo.
    echo  Este programa necesita Python para funcionar.
    echo  Python es gratuito y se instala en 2 minutos.
    echo.
    echo  Como instalarlo:
    echo.
    echo   1. Abre el navegador y ve a esta pagina:
    echo      https://www.python.org/downloads/
    echo.
    echo   2. Haz clic en el boton "Download Python"
    echo.
    echo   3. Abre el archivo descargado
    echo.
    echo   4. MUY IMPORTANTE: en la primera pantalla
    echo      marca la casilla "Add Python to PATH"
    echo      Si no la marcas, el programa no funcionara.
    echo.
    echo   5. Haz clic en "Install Now" y espera que termine
    echo.
    echo   6. Cierra esta ventana y vuelve a hacer
    echo      doble clic en iniciar.bat
    echo.
    pause
    exit /b 1
)

echo  [OK] Python encontrado.


:: 2. Instalar dependencias si no estan instaladas

python -c "import streamlit" >NUL 2>&1
if errorlevel 1 (
    echo.
    echo  Instalando el programa por primera vez...
    echo  Puede tardar entre 2 y 5 minutos. No cierres la ventana.
    echo.
    pip install -r requirements.txt --quiet --disable-pip-version-check
    if errorlevel 1 (
        echo.
        echo  ============================================
        echo   ERROR al instalar las dependencias
        echo  ============================================
        echo.
        echo  No se pudieron instalar los componentes.
        echo.
        echo  Que puedes hacer:
        echo   1. Asegurate de tener internet
        echo   2. Vuelve a hacer doble clic en iniciar.bat
        echo   3. Si sigue fallando, pide ayuda a quien
        echo      te paso este programa
        echo.
        pause
        exit /b 1
    )
    echo  [OK] Instalado correctamente.
) else (
    echo  [OK] Dependencias ya instaladas.
)


:: 3. Verificar archivo de credenciales

if not exist "config\credentials.json" (
    echo.
    echo  ============================================
    echo   AVISO: Falta el archivo de credenciales
    echo  ============================================
    echo.
    echo  Para conectar con Gmail se necesita un archivo
    echo  que todavia no esta en tu computadora.
    echo.
    echo  Lee el archivo config\README.md para instrucciones.
    echo.
    pause
    exit /b 1
)

echo  [OK] Credenciales encontradas.
echo.
echo  ============================================
echo.
echo  Abriendo el programa en tu navegador...
echo.
echo  Si el navegador no se abre automaticamente,
echo  escribe esto en la barra del navegador:
echo  http://localhost:8501
echo.
echo  Para cerrar el programa, cierra esta ventana
echo  o presiona Ctrl+C
echo.
echo  ============================================
echo.

set "PATH=%PATH%;%APPDATA%\Python\Python314\Scripts"

:: Abrir el navegador en 3 segundos mientras streamlit arranca
start /min "" powershell -command "Start-Sleep 3; Start-Process 'http://localhost:8501'"

python -m streamlit run app.py --server.headless false

if errorlevel 1 (
    echo.
    echo  El programa se cerro con un error.
    echo  Vuelve a hacer doble clic en iniciar.bat
    echo  para intentarlo de nuevo.
    echo.
    pause
)
