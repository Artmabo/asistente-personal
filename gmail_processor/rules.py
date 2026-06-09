"""
Reglas editables del procesador de correos.
Modifica este archivo para personalizar el comportamiento del sistema.
"""

# ── Contactos protegidos ──────────────────────────────────────────────────────
# Estos remitentes NUNCA serán eliminados ni archivados. Solo se etiquetan.
# Formato: "email@dominio.com": {"label": "NOMBRE_LABEL", "mark_important": bool}
CONTACT_RULES: dict[str, dict] = {
    # "papa@gmail.com": {"label": "FAMILIA", "mark_important": False},
    # "mama@gmail.com": {"label": "FAMILIA", "mark_important": False},
    # "jefe@empresa.com": {"label": "TRABAJO", "mark_important": True},
}

# ── Reglas por dominio del remitente ─────────────────────────────────────────
# Se aplican cuando el dominio del remitente está en la lista.
# Acciones válidas: "mark_important", "archive", "label_only"
DOMAIN_RULES: list[dict] = [
    {
        "domains": ["banamex.com", "bbva.com", "bancomer.com", "hsbc.com",
                    "santander.com.mx", "banorte.com", "scotiabank.com.mx"],
        "label": "FINANZAS",
        "action": "mark_important",
    },
    {
        "domains": ["netflix.com", "spotify.com", "amazon.com.mx", "amazon.com",
                    "mercadolibre.com", "mercadopago.com"],
        "label": "SERVICIOS",
        "action": "archive",
    },
    {
        "domains": ["sat.gob.mx", "imss.gob.mx", "issste.gob.mx"],
        "label": "GOBIERNO",
        "action": "mark_important",
    },
]

# ── Reglas por palabras clave (en asunto + remitente) ─────────────────────────
# Las keywords se buscan en: asunto + dirección del remitente (case-insensitive por default).
# Acciones válidas: "mark_important", "archive", "trash", "label_only"
KEYWORD_RULES: list[dict] = [
    {
        "keywords": ["factura", "invoice", "comprobante fiscal", "cfdi",
                     "recibo", "estado de cuenta", "receipt", "billing statement"],
        "label": "FACTURAS",
        "action": "mark_important",
        "case_sensitive": False,
    },
    {
        "keywords": ["reunión", "meeting", "tarea", "entrega", "deadline",
                     "proyecto", "junta", "asignación", "calificación", "horario"],
        "label": "TRABAJO_ESCUELA",
        "action": "mark_important",
        "case_sensitive": False,
    },
    {
        "keywords": ["unsubscribe", "opt-out", "darse de baja", "oferta exclusiva",
                     "ganaste", "has ganado", "premio", "free gift", "click aquí",
                     "click here", "limited time offer", "50% off", "100% gratis"],
        "label": "SPAM",
        "action": "trash",
        "case_sensitive": False,
    },
]

# ── Reglas por categoría automática de Gmail ──────────────────────────────────
# Gmail clasifica correos en estas categorías automáticamente.
# Acciones válidas: "archive", "label_only", "trash"
CATEGORY_RULES: dict[str, dict] = {
    "CATEGORY_PROMOTIONS": {"action": "archive", "label": "PROMOCIONES"},
    "CATEGORY_SOCIAL":     {"action": "archive", "label": "SOCIAL"},
    "CATEGORY_UPDATES":    {"action": "archive", "label": "ACTUALIZACIONES"},
    "CATEGORY_FORUMS":     {"action": "archive", "label": "FOROS"},
}

# ── Limpieza de almacenamiento ────────────────────────────────────────────────
# Cada "target" define una query Gmail + la razón + un nombre de regla identificable.
# Los correos que coincidan serán enviados a papelera SI no están protegidos.
# Protecciones automáticas: CONTACT_RULES, dominios mark_important, IMPORTANT, STARRED.
CLEANUP_RULES: dict = {
    "targets": [
        {
            "query": "category:promotions older_than:60d",
            "reason": "Promoción con más de 60 días",
            "rule": "promotions_60d",
        },
        {
            "query": "category:social older_than:90d",
            "reason": "Red social / notificación con más de 90 días",
            "rule": "social_90d",
        },
        {
            "query": "category:updates older_than:90d",
            "reason": "Actualización automática con más de 90 días",
            "rule": "updates_90d",
        },
        {
            "query": "category:forums older_than:90d",
            "reason": "Foro o lista de correo con más de 90 días",
            "rule": "forums_90d",
        },
        {
            "query": "is:unread older_than:180d -is:important -is:starred",
            "reason": "No leído por más de 6 meses sin interacción",
            "rule": "unread_180d",
        },
    ],
    # Dominios adicionales a proteger (además de los mark_important en DOMAIN_RULES)
    "safe_domains": [],
    # Tope de seguridad: nunca procesar más de N correos por query
    "max_per_query": 200,
}

# ── Configuración general ─────────────────────────────────────────────────────
MAX_RESULTS_PER_PAGE = 100   # Correos por página al listar (máx 500)
QUERY_FILTER = "is:inbox"    # Query Gmail para filtrar qué correos procesar
DRY_RUN = True               # True = solo simula acciones (no hace cambios reales)
                             # Cambia a False cuando quieras ejecutar en producción
