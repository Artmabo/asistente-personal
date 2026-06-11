# Mi Asistente de Correo

Aplicación web personal para gestionar Gmail de forma inteligente. Diseñada para que cualquier persona —sin experiencia técnica— pueda mantener su bandeja de entrada organizada, conocer quién le escribe y limpiar correos innecesarios con seguridad.

Usa inteligencia artificial (Claude de Anthropic) para analizar contactos, responder preguntas sobre el correo y generar resúmenes diarios.

---

## Para quién es

- Personas que reciben muchos correos y quieren organizarlos sin complicaciones
- Usuarios que quieren saber quién les escribe y qué les han enviado
- Quienes desean limpiar su bandeja de entrada de forma segura, sin borrar cosas importantes por accidente

---

## Funcionalidades

### Inicio
- Saludo personalizado con fecha actual
- Resumen del día: contactos nuevos, alertas importantes
- Acceso rápido a todas las secciones

### Mis contactos
- Lista de las personas y organizaciones que más te escriben
- Perfil detallado de cada contacto generado con IA: quién es, sobre qué escribe, tono, idioma, documentos enviados
- Clasificación automática: familiar, trabajo, servicio, gobierno
- Línea de tiempo de la relación por año
- Alertas automáticas si detecta algo importante (cobros, documentos pendientes, etc.)

### Analizar correos
- Clasifica automáticamente tus correos en: personal, publicidad, notificación, suscripción, spam
- Modo simulación: ver las decisiones sin aplicar cambios reales
- Aprendizaje: el sistema mejora con el tiempo según tu feedback

### Limpiar correos
- Limpieza segura de correos no importantes
- Protege automáticamente los correos de tus contactos importantes
- Vista previa de lo que se va a eliminar antes de confirmar

### Limpieza automática
- Programa limpiezas periódicas (diaria, semanal, mensual)
- Se ejecuta en segundo plano sin intervención manual
- Configurable con horario y límite de correos por ejecución

### Asistente con IA (chat)
- Chat integrado en el sidebar para hacer preguntas sobre tu correo
- Responde en español con lenguaje simple
- Tiene acceso al contexto de tus contactos y estado del correo
- Ejemplos: "¿Quién es Banamex?", "¿Cuándo fue el último correo de mi hijo?", "¿Qué correos debo revisar hoy?"

### Opciones avanzadas
- Estadísticas del motor de aprendizaje
- Registro de auditoría: historial de cada acción realizada
- Configuración del sistema

---

## Requisitos

- **Python 3.10 o superior**
- Una cuenta de **Gmail**
- Una **API key de Anthropic** (para las funciones de IA)
- Credenciales de la **API de Google Gmail**
- Conexión a internet

---

## Instalación paso a paso

### 1. Instalar Python

Si no tienes Python instalado:

1. Ve a [python.org/downloads](https://www.python.org/downloads/)
2. Descarga e instala la versión más reciente
3. **Solo en Windows:** en la primera pantalla del instalador, marca la casilla **"Add Python to PATH"** antes de continuar

### 2. Descargar el proyecto

Descarga este repositorio como ZIP desde GitHub y descomprímelo en una carpeta de tu computadora (por ejemplo, en el Escritorio).

O si tienes Git instalado:

```bash
git clone https://github.com/Artmabo/asistente-personal.git
cd asistente-personal
```

### 3. Instalar dependencias

Abre una terminal en la carpeta del proyecto y ejecuta:

```bash
pip install -r requirements.txt
```

---

## Configurar Google Gmail API

Para que la aplicación pueda acceder a tu Gmail necesitas crear credenciales de Google. Es un proceso único que solo se hace una vez.

### Paso a paso

1. Ve a [console.cloud.google.com](https://console.cloud.google.com/)
2. Crea un proyecto nuevo (puedes llamarlo "Mi Asistente")
3. En el menú lateral, ve a **APIs y servicios → Biblioteca**
4. Busca **"Gmail API"** y haz clic en **Habilitar**
5. Ve a **APIs y servicios → Credenciales**
6. Haz clic en **Crear credenciales → ID de cliente de OAuth**
7. Selecciona **Aplicación de escritorio** como tipo
8. Descarga el archivo JSON que se genera
9. Renómbralo a `credentials.json` y colócalo dentro de la carpeta `config/` del proyecto

La primera vez que ejecutes la app, se abrirá el navegador para que autorices el acceso a tu Gmail. Después de autorizar, se crea automáticamente un archivo `token.json` que guarda la sesión.

> **Importante:** `credentials.json` y `token.json` son privados. Nunca los compartas ni los subas a GitHub. Ya están excluidos por el `.gitignore`.

---

## Configurar API key de Anthropic

La IA que analiza tus contactos y responde en el chat es Claude de Anthropic.

1. Crea una cuenta en [console.anthropic.com](https://console.anthropic.com/)
2. Ve a **API Keys** y crea una nueva clave
3. En la carpeta del proyecto, crea un archivo llamado `.env` con este contenido:

```
ANTHROPIC_API_KEY=tu_clave_aqui
```

Reemplaza `tu_clave_aqui` por la clave que copiaste de Anthropic.

> **Importante:** El archivo `.env` es privado. Nunca lo compartas. Ya está excluido por el `.gitignore`.

---

## Cómo ejecutar

### Opción A — Doble clic (más fácil, solo Windows)

Haz doble clic en el archivo **`iniciar.bat`** dentro de la carpeta del proyecto. Se abrirá automáticamente en el navegador.

### Opción B — Terminal

```bash
streamlit run app.py
```

La aplicación se abre en el navegador en `http://localhost:8501`.

---

## Estructura del proyecto

```
asistente-personal/
├── app.py                    # Interfaz web principal (Streamlit)
├── requirements.txt          # Dependencias de Python
├── iniciar.bat               # Lanzador para Windows
├── iniciar.sh                # Lanzador para Mac/Linux
├── .env                      # API key de Anthropic (no se sube a git)
├── config/
│   └── credentials.json      # Credenciales de Google (no se sube a git)
├── .streamlit/
│   └── config.toml           # Tema oscuro de la interfaz
└── gmail_processor/
    ├── auth.py               # Autenticación con Gmail
    ├── processor.py          # Motor principal de clasificación
    ├── rules.py              # Reglas de filtrado
    ├── classifier.py         # Clasificador de correos
    ├── contact_profiler.py   # Perfiles de contactos con IA
    ├── assistant_chat.py     # Chat con Claude
    ├── morning_brief.py      # Resumen diario
    ├── learning_engine.py    # Motor de aprendizaje
    ├── scheduler.py          # Limpieza automática programada
    ├── smart_setup.py        # Configuración inicial inteligente
    ├── cleanup_storage.py    # Limpieza de almacenamiento
    ├── storage_analyzer.py   # Análisis de uso de espacio
    ├── audit_log.py          # Registro de auditoría
    └── actions.py            # Acciones sobre correos (archivar, borrar)
```

---

## Archivos generados localmente

Estos archivos se crean automáticamente al usar la app y **no se suben a GitHub**:

| Archivo | Contenido |
|---|---|
| `token.json` | Sesión de Gmail autorizada |
| `contact_profiles.json` | Perfiles de contactos generados con IA |
| `analysis_state.json` | Estado del análisis de correos |
| `chat_history.json` | Historial del chat con el asistente |
| `user_patterns.json` | Patrones aprendidos del usuario |
| `audit_log.jsonl` | Registro completo de acciones |
| `cleanup_schedule.json` | Configuración de limpieza automática |

---

## Seguridad

- Ninguna credencial ni token se sube a GitHub (protegidos por `.gitignore`)
- La app corre completamente en tu computadora — tus correos no salen a ningún servidor externo salvo la API de Anthropic para los análisis de IA
- El modo simulación permite ver qué haría el sistema sin modificar nada real
- Cada acción queda registrada en el audit log

---

## Tecnologías usadas

- [Streamlit](https://streamlit.io/) — interfaz web
- [Google Gmail API](https://developers.google.com/gmail/api) — acceso al correo
- [Anthropic Claude](https://www.anthropic.com/) — análisis con IA y chat
- [APScheduler](https://apscheduler.readthedocs.io/) — limpieza automática programada
