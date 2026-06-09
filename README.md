# Gmail Intelligence — Asistente Personal

Sistema de automatización inteligente para Gmail con aprendizaje adaptativo, menú interactivo CLI y trazabilidad completa de decisiones.

---

## Características

- **Menú interactivo** — opera todo el sistema sin tocar código
- **Clasificador por reglas** — contactos, dominios, keywords, categorías Gmail
- **Cleanup inteligente** — limpieza de almacenamiento con protecciones automáticas
- **Aprendizaje adaptativo** — mejora sus decisiones con feedback del usuario
- **Audit log** — historial completo de cada decisión tomada
- **Modo DRY RUN** — simula todas las acciones sin modificar tu bandeja
- **Debug mode** — traza completa del pipeline por cada correo

---

## Instalación

### Requisitos

- Python 3.10 o superior
- Cuenta de Gmail con API habilitada

### 1. Clonar el repositorio

```bash
git clone https://github.com/Artmabo/asistente-personal.git
cd asistente-personal
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar credenciales de Gmail API

1. Ve a [Google Cloud Console](https://console.cloud.google.com)
2. Crea un proyecto y activa la **Gmail API**
3. Crea credenciales: **APIs y servicios → Credenciales → Crear → ID de cliente OAuth 2.0 → Aplicación de escritorio**
4. Descarga el JSON y guárdalo como `config/credentials.json`

> El archivo `credentials.json` nunca se sube al repositorio. Cada usuario genera el suyo.

### 4. Primera autenticación

Al ejecutar el sistema por primera vez se abrirá el navegador para autorizar el acceso a tu Gmail. Esto genera `token.json` localmente.

```bash
python procesar_correos.py
```

---

## Inicio rápido

```bash
python procesar_correos.py
```

Sin argumentos se abre el **menú interactivo**. Es el modo recomendado para uso diario.

---

## Menú interactivo — Referencia completa

```
══════════════════════════════════════════════════════
  Gmail Intelligence — Asistente Personal
══════════════════════════════════════════════════════
  1.  Procesar inbox      clasificar y etiquetar
  2.  Cleanup seguro      limpiar almacenamiento
  3.  Estadísticas        métricas y aprendizaje
  4.  Audit log           historial de decisiones
  5.  Feedback            corregir una decisión
  6.  Configuración       reglas y contactos
  7.  Debug mode          traza completa del pipeline
  0.  Salir
```

### Opción 1 — Procesar inbox

Clasifica los correos del inbox según las reglas configuradas en `gmail_processor/rules.py`:

- **Contactos protegidos** → etiqueta, nunca elimina
- **Palabras clave** → etiqueta según tipo (facturas, spam, trabajo)
- **Categorías Gmail** → archiva promociones, social, actualizaciones
- **Dominios conocidos** → finanzas y gobierno marcados como importantes

Te pregunta si quieres ejecutar en **LIVE** antes de hacer cualquier cambio real.

### Opción 2 — Cleanup seguro

Identifica correos expirados o irrelevantes y los mueve a la **papelera** (no elimina permanentemente).

Protecciones automáticas que **nunca se saltan**:
- Correos marcados con estrella (`STARRED`)
- Correos marcados como importantes (`IMPORTANT`)
- Contactos en `CONTACT_RULES`
- Dominios financieros / gobierno configurados como `mark_important`

Targets por defecto:
| Regla | Criterio |
|---|---|
| `promotions_60d` | Promociones con más de 60 días |
| `social_90d` | Notificaciones sociales con más de 90 días |
| `updates_90d` | Actualizaciones automáticas con más de 90 días |
| `forums_90d` | Foros y listas de correo con más de 90 días |
| `unread_180d` | No leídos por más de 6 meses sin estrella ni importancia |

### Opción 3 — Estadísticas

Muestra el estado del sistema sin conectarse a Gmail:

- **Modelos de aprendizaje** — cuántos remitentes y dominios tiene en memoria
- **Métricas de calidad** — total procesados, conservados, enviados, falsos positivos, precisión por regla
- **Categorías Gmail** — conteos observados por categoría (Promociones, Social, etc.)
- **Audit log (acumulado)** — conteo global de decisiones TRASH / KEEP / SKIP

### Opción 4 — Audit log

Historial de las últimas N decisiones del sistema. Puedes filtrar por tipo:

- `TRASH` — correos enviados a papelera
- `KEEP` — correos conservados por score de aprendizaje
- `SKIP` — correos ignorados por protección dura

Cada entrada muestra: timestamp, decisión, remitente, score, regla aplicada y modo (DRY/LIVE).

### Opción 5 — Feedback

Corrige una decisión del sistema para que aprenda:

```
¿El correo fue eliminado por error?
  → Feedback "incorrecto" → aumenta el score del remitente/dominio
  
¿La eliminación fue correcta?
  → Feedback "correcto" → reduce el score (menos protección en el futuro)
```

El sistema aplica un **filtro de confianza** antes de aceptar el feedback:
- Feedback **manual** (desde el menú): siempre aceptado
- Feedback **automático**: requiere confianza >= 0.60 o 2 repeticiones

Puedes ver el resultado: `ACEPTADO`, `EN ESPERA` (necesita repetición) o `BLOQUEADO` (entidad crítica protegida).

### Opción 6 — Configuración

Gestiona las reglas del sistema:

- **Ver / agregar / eliminar contactos protegidos** — modifica `rules.py` automáticamente y recarga la configuración en vivo
- **Ver reglas de dominio** — qué dominios están clasificados y cómo
- **Ver keywords de spam** — palabras que activan clasificación automática
- **Abrir rules.py en editor** — edición directa (Notepad en Windows)

### Opción 7 — Debug mode

Ejecuta el cleanup en **DRY RUN forzado** mostrando la traza completa del pipeline por cada correo:

```
┌─ PIPELINE  18f3a2b1c4d5
│  EMAIL   : Ofertas Newsletter <promo@spam.com>
│  SUBJECT : Descuentos exclusivos solo hoy
│  LABELS  : CATEGORY_PROMOTIONS INBOX
│  RULE    : promotions_60d
│  RULES   : hard_protection=None
│  SCORE   : -10.0  (floor=15.0)
│  FACTORES: -10 categoría Promociones
│  APRENDIZ: No
└─ DECISION: TRASH  (score < floor)
```

Útil para entender por qué el sistema toma cada decisión antes de ejecutar en LIVE.

---

## DRY RUN vs LIVE

| | DRY RUN (default) | LIVE |
|---|---|---|
| Clasifica correos | Sí | Sí |
| Aplica etiquetas | No | Sí |
| Mueve a papelera | No | Sí |
| Guarda aprendizaje | No | Solo con `--learning` |
| Riesgo | Ninguno | Mueve correos a papelera |

**El sistema siempre comienza en DRY RUN.** Para ejecutar en LIVE el menú pide **doble confirmación**.

---

## Flujo recomendado de uso

### Primera vez

```
1. Instalar y configurar credenciales (ver Instalación)
2. Abrir el menú: python procesar_correos.py
3. Opción 6 → Agregar tus contactos importantes
4. Opción 7 → Debug mode para ver qué haría el sistema
5. Opción 2 → Cleanup en DRY RUN para revisar el output
6. Revisar la lista, confirmar que nada importante aparece como TRASH
7. Opción 2 → Cleanup en LIVE cuando estés conforme
```

### Uso regular

```
1. Opción 2 → Cleanup seguro (revisar output en DRY, luego LIVE)
2. Si algo fue eliminado por error → Opción 5 → Feedback "incorrecto"
3. Opción 3 → Revisar estadísticas periódicamente
4. Opción 4 → Audit log si quieres ver decisiones recientes
```

---

## Sistema de aprendizaje

El sistema mantiene tres modelos independientes en `learning_state.json`:

| Modelo | Qué aprende | Vida media |
|---|---|---|
| `sender_model` | Por dirección de email | ~173 días |
| `domain_model` | Por dominio (@empresa.com) | ~346 días |
| `category_model` | Por categoría Gmail | Solo observación |

### Cómo funciona el score

Cada correo recibe un score basado en señales estáticas + aprendizaje:

| Señal | Score |
|---|---|
| Contacto protegido | +50 |
| Etiqueta IMPORTANT | +40 |
| Estrella (STARRED) | +30 |
| Dominio financiero / gobierno | +35 |
| Dominio de servicios | -5 |
| Categoría Foros | -20 |
| Categoría Social | -15 |
| Categoría Promociones | -10 |
| Categoría Actualizaciones | -8 |

Un score >= **15.0** → el correo se conserva (KEEP).  
Un score < **15.0** → el correo va a papelera (TRASH).

El feedback del usuario ajusta el score con **decay temporal** (los ajustes se debilitan con el tiempo) y **control de deriva** (máximo ±10 unidades por día por entidad).

---

## Interpretación del audit log

Cada entrada en el audit log representa una decisión:

```
TIMESTAMP            DEC    SENDER                            SCORE   REGLA
─────────────────────────────────────────────────────────────────────────────
2026-06-09T14:23:01  TRASH  promo@newsletter.com              -10.0  promotions_60d  LIVE
2026-06-09T14:23:02  SKIP   banco@banamex.com                  +0.0  promotions_60d  LIVE
2026-06-09T14:23:03  KEEP   info@empresa.com                  +20.0  promotions_60d  LIVE
```

- `TRASH` — enviado a papelera
- `SKIP` — ignorado por protección dura (contacto, dominio seguro, estrella, importante)
- `KEEP` — conservado porque el score aprendido supera el umbral
- `DRY` / `LIVE` — modo en que se ejecutó

---

## Advertencias sobre cleanup

> El cleanup **mueve correos a la papelera de Gmail**, no los elimina permanentemente. Los correos permanecen en la papelera 30 días y pueden recuperarse desde Gmail antes de ese plazo.

- **Nunca ejecutes en LIVE sin revisar primero en DRY RUN**
- Si un correo importante fue movido por error → recupéralo desde la papelera de Gmail → luego usa Opción 5 (Feedback "incorrecto") para que el sistema aprenda
- El cap por defecto es **200 correos por target** — ajústalo en `CLEANUP_RULES["max_per_query"]` en `rules.py`
- Los contactos en `CONTACT_RULES` son **inmunes** al cleanup y al feedback negativo

---

## Modo script (CLI directo)

Si prefieres no usar el menú interactivo:

```bash
# Solo clasificar (DRY RUN)
python procesar_correos.py --cleanup

# Cleanup real
python procesar_correos.py --cleanup --live

# Cleanup + guardar aprendizaje
python procesar_correos.py --cleanup --live --learning

# Traza debug
python procesar_correos.py --cleanup --debug

# Query personalizada
python procesar_correos.py --query "from:newsletter@spam.com older_than:30d"

# Feedback por CLI
python procesar_correos.py feedback promo@spam.com correct
python procesar_correos.py feedback papa@gmail.com incorrect --rule promotions_60d

# Estadísticas
python procesar_correos.py stats
python procesar_correos.py stats --section metrics

# Audit log
python procesar_correos.py audit --last 50 --decision TRASH
```

---

## Personalización de reglas

Edita `gmail_processor/rules.py` para ajustar el comportamiento:

**Agregar un contacto protegido:**
```python
CONTACT_RULES = {
    "papa@gmail.com":  {"label": "FAMILIA", "mark_important": False},
    "jefe@empresa.com": {"label": "TRABAJO", "mark_important": True},
}
```

**Agregar un dominio de confianza:**
```python
DOMAIN_RULES = [
    {
        "domains": ["mibanco.com"],
        "label": "FINANZAS",
        "action": "mark_important",   # nunca tocado por cleanup
    },
]
```

**Ajustar thresholds de cleanup:**
```python
CLEANUP_RULES = {
    "targets": [
        {"query": "category:promotions older_than:30d",   # 30 días en lugar de 60
         "reason": "Promoción con más de 30 días",
         "rule": "promotions_30d"},
    ],
    "max_per_query": 100,  # límite de seguridad
}
```

---

## Estructura del proyecto

```
asistente-personal/
├── procesar_correos.py          # Entry point principal
├── requirements.txt
├── config/
│   └── README.md                # Instrucciones para credentials.json (no incluido)
├── gmail_processor/
│   ├── __init__.py
│   ├── auth.py                  # OAuth con Gmail API
│   ├── rules.py                 # Reglas editables (contactos, dominios, keywords)
│   ├── classifier.py            # Clasificador por reglas
│   ├── actions.py               # Acciones sobre Gmail (label, trash, archive)
│   ├── cleanup_storage.py       # Módulo de limpieza con pipeline de decisiones
│   ├── learning_engine.py       # Motor de aprendizaje adaptativo (v3)
│   ├── audit_log.py             # Log estructurado JSONL por decisión
│   ├── processor.py             # Orquestador principal
│   └── cli_menu.py              # Menú interactivo CLI
└── limpiar_correos.py           # Script legacy (referencia)
```

### Archivos generados localmente (no en el repo)

| Archivo | Descripción |
|---|---|
| `token.json` | Token OAuth — generado en la primera ejecución |
| `config/credentials.json` | Credenciales de Google Cloud — cada usuario descarga el suyo |
| `learning_state.json` | Estado del motor de aprendizaje — crece con el uso |
| `audit_log.jsonl` | Historial de decisiones — crece con el uso |
| `gmail_processor.log` | Log de ejecuciones |

---

## Seguridad

- `token.json` y `config/credentials.json` están en `.gitignore` y **nunca se suben al repositorio**
- El sistema usa OAuth 2.0 — tus credenciales nunca se transmiten a terceros
- El token se refresca automáticamente y se guarda solo en tu máquina
- Si compartes el repositorio, cada colaborador debe generar sus propias credenciales y token

---

## Solución de problemas

**"credentials.json not found"**  
→ Descarga el archivo desde Google Cloud Console y guárdalo en `config/credentials.json`

**"Token has been expired or revoked"**  
→ Elimina `token.json` y vuelve a ejecutar. Se pedirá autorización en el navegador.

**Error 403 al llamar la API**  
→ La cuota diaria de Gmail API se resetea cada 24h. El sistema reintenta con backoff automático.

**Cleanup eliminó un correo importante**  
→ Recupéralo desde la Papelera en Gmail (tienes 30 días). Luego usa Opción 5 → Feedback "incorrecto" para que el sistema aprenda.

**El menú muestra caracteres extraños**  
→ Asegúrate de que tu terminal use UTF-8. En Windows, ejecuta `chcp 65001` antes de iniciar.

---

## Licencia

Uso personal libre.
