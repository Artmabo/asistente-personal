#!/bin/bash
# Asistente Personal de Gmail — Script de inicio para Mac
# Para ejecutarlo: abre Terminal, arrastra este archivo dentro y presiona Enter.

# Cambiar al directorio del script (para que las rutas relativas funcionen)
cd "$(dirname "$0")"

echo ""
echo " ============================================="
echo "  Asistente Personal de Gmail"
echo " ============================================="
echo ""


# ─────────────────────────────────────────────
# 1. Verificar que Python esté instalado
# ─────────────────────────────────────────────
if ! command -v python3 &> /dev/null; then
    clear
    echo ""
    echo " ============================================="
    echo "  Falta instalar Python"
    echo " ============================================="
    echo ""
    echo " Este programa necesita Python para funcionar."
    echo " Python es gratuito y se instala en 2 minutos."
    echo ""
    echo " Cómo instalarlo:"
    echo ""
    echo "  1. Abre Safari u otro navegador"
    echo ""
    echo "  2. Ve a esta página:"
    echo "     https://www.python.org/downloads/"
    echo ""
    echo "  3. Haz clic en el botón grande que dice"
    echo "     \"Download Python 3.x.x\""
    echo ""
    echo "  4. Abre el archivo descargado (.pkg)"
    echo "     y sigue las instrucciones en pantalla"
    echo ""
    echo "  5. Cuando termine, abre una Terminal nueva"
    echo "     y vuelve a ejecutar este archivo"
    echo ""
    echo "  Alternativa rápida si tienes Homebrew:"
    echo "     brew install python3"
    echo ""
    echo " ============================================="
    echo ""
    read -rp " Presiona Enter para cerrar..."
    exit 1
fi

echo " [OK] Python encontrado: $(python3 --version)"


# ─────────────────────────────────────────────
# 2. Instalar dependencias (solo la primera vez)
# ─────────────────────────────────────────────
if ! python3 -c "import streamlit" &> /dev/null; then
    echo ""
    echo " Instalando el programa por primera vez..."
    echo " Esto puede tardar entre 2 y 5 minutos según tu internet."
    echo " No cierres esta ventana mientras trabaja."
    echo ""

    pip3 install -r requirements.txt --quiet --disable-pip-version-check
    if [ $? -ne 0 ]; then
        echo ""
        echo " ============================================="
        echo "  Error al instalar"
        echo " ============================================="
        echo ""
        echo " No se pudieron instalar las partes necesarias."
        echo ""
        echo " Qué puedes hacer:"
        echo ""
        echo "  1. Asegúrate de tener internet"
        echo "  2. Cierra esta ventana y vuelve a"
        echo "     ejecutar el archivo iniciar.sh"
        echo "  3. Si el error sigue, pide ayuda a quien"
        echo "     te pasó este programa"
        echo ""
        read -rp " Presiona Enter para cerrar..."
        exit 1
    fi
    echo ""
    echo " [OK] Programa instalado correctamente."
else
    echo " [OK] Dependencias ya instaladas."
fi


# ─────────────────────────────────────────────
# 3. Verificar archivo de credenciales de Gmail
# ─────────────────────────────────────────────
if [ ! -f "config/credentials.json" ]; then
    echo ""
    echo " ============================================="
    echo "  Falta el archivo de acceso a Gmail"
    echo " ============================================="
    echo ""
    echo " Para conectar con Gmail se necesita un archivo"
    echo " que todavía no está en tu computadora."
    echo ""
    echo " Mira el archivo \"config/README.md\" para ver"
    echo " cómo obtenerlo paso a paso desde Google Cloud."
    echo ""
    read -rp " Presiona Enter para cerrar..."
    exit 1
fi

echo " [OK] Archivo de credenciales encontrado."
echo ""
echo " ─────────────────────────────────────────────"
echo ""
echo " Abriendo el programa en tu navegador..."
echo ""
echo " * En unos segundos se abrirá el navegador solo."
echo " * Si no se abre, entra manualmente a:"
echo "   http://localhost:8501"
echo ""
echo " * Para cerrar el programa, cierra esta ventana"
echo "   o presiona Ctrl+C"
echo ""
echo " ─────────────────────────────────────────────"
echo ""

python3 -m streamlit run app.py

if [ $? -ne 0 ]; then
    echo ""
    echo " El programa se cerró con un error."
    echo ""
    echo " Intenta ejecutar iniciar.sh otra vez."
    echo " Si el problema continúa, pide ayuda a quien"
    echo " te pasó este programa."
    echo ""
    read -rp " Presiona Enter para cerrar..."
fi
