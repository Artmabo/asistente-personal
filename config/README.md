# config/

Esta carpeta debe contener tu archivo `credentials.json` descargado de Google Cloud Console.

**El archivo `credentials.json` NO está incluido en el repositorio por razones de seguridad.**

## Cómo obtenerlo

1. Ve a [Google Cloud Console](https://console.cloud.google.com)
2. Crea o selecciona un proyecto
3. Activa la **Gmail API** desde "APIs y servicios" → "Biblioteca"
4. Ve a "APIs y servicios" → "Credenciales" → "Crear credenciales" → "ID de cliente OAuth 2.0"
5. Selecciona **Aplicación de escritorio**
6. Descarga el JSON y guárdalo aquí como `config/credentials.json`

El archivo `token.json` (generado automáticamente en la raíz del proyecto) tampoco debe compartirse.
