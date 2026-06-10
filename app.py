"""
Gmail Cleanup — Interfaz web para usuarios no técnicos.
Ejecutar con:  streamlit run app.py
"""
import os
import sys
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Configuración de página (debe ser la primera llamada a Streamlit) ──────────
st.set_page_config(
    page_title="Limpieza de Gmail",
    page_icon="📧",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Inicializar session state ──────────────────────────────────────────────────
_CATS_KEYS = ["spam", "promociones", "social", "actualizaciones"]
_ALL_KEYS  = _CATS_KEYS + ["todo"]

st.session_state.setdefault("service", None)
for _k in _ALL_KEYS:
    st.session_state.setdefault(f"confirm_{_k}", False)
    st.session_state.setdefault(f"result_{_k}",  None)

# Organizar correos
st.session_state.setdefault("confirm_proc",    False)
st.session_state.setdefault("proc_result",     None)
st.session_state.setdefault("senders_data",    None)
# Panel avanzado
st.session_state.setdefault("stats_data",          None)
st.session_state.setdefault("audit_data",          None)
st.session_state.setdefault("feedback_result",     None)
st.session_state.setdefault("smart_setup_result",  None)
st.session_state.setdefault("debug_result",        None)
# Análisis de contactos
st.session_state.setdefault("ca_batch_result",     None)
st.session_state.setdefault("ca_apply_result",     None)
st.session_state.setdefault("ca_decisions",        {})
st.session_state.setdefault("ca_running",          False)

# ── Definición de categorías ───────────────────────────────────────────────────
CATS = [
    dict(
        key="spam",
        icon="🚫",
        nombre="Spam",
        desc=(
            "Son correos que Gmail identificó automáticamente como no deseados: "
            "publicidad agresiva, intentos de estafa o mensajes sospechosos."
        ),
        aviso=(
            "Moverá a la papelera **todos los mensajes de tu carpeta Spam**. "
            "Podrás revisarlos y recuperarlos desde la Papelera de Gmail durante 30 días."
        ),
    ),
    dict(
        key="promociones",
        icon="📢",
        nombre="Promociones",
        desc=(
            "Correos de tiendas y servicios: ofertas, descuentos, newsletters y publicidad. "
            "Suelen acumular cientos o miles de mensajes con el tiempo."
        ),
        aviso=(
            "Moverá a la papelera **todos los correos de la categoría Promociones** "
            "(ofertas, descuentos, newsletters, publicidad). "
            "Podrás revisarlos y recuperarlos desde la Papelera de Gmail durante 30 días."
        ),
    ),
    dict(
        key="social",
        icon="👥",
        nombre="Social",
        desc=(
            "Notificaciones de redes sociales: Facebook, Instagram, LinkedIn, "
            "Twitter/X, YouTube, TikTok, etc."
        ),
        aviso=(
            "Moverá a la papelera **todos los correos de la categoría Social** "
            "(notificaciones de redes sociales). "
            "Podrás revisarlos y recuperarlos desde la Papelera de Gmail durante 30 días."
        ),
    ),
    dict(
        key="actualizaciones",
        icon="🔔",
        nombre="Actualizaciones",
        desc=(
            "Mensajes automáticos: confirmaciones de compra, recibos, alertas de apps "
            "y notificaciones de servicios. "
            "Revisa que no queden recibos importantes antes de limpiar."
        ),
        aviso=(
            "Moverá a la papelera **todos los correos de la categoría Actualizaciones** "
            "(confirmaciones, recibos, alertas automáticas). "
            "Podrás revisarlos y recuperarlos desde la Papelera de Gmail durante 30 días."
        ),
    ),
]

_TODO_NOMBRE = {
    "spam": "Spam", "promociones": "Promociones", "social": "Social",
    "actualizaciones": "Actualizaciones", "foros": "Foros",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _init_service() -> bool:
    """Intenta obtener el servicio de Gmail. Devuelve True si tiene éxito."""
    if st.session_state.service is not None:
        return True
    try:
        from limpiar_correos import obtener_servicio
        st.session_state.service = obtener_servicio()
        return True
    except FileNotFoundError:
        st.error(
            "No se encontró el archivo de credenciales. "
            "Necesitas el archivo `config/credentials.json` descargado desde Google Cloud Console. "
            "Consulta el archivo `config/README.md` para instrucciones."
        )
        return False
    except Exception as exc:
        st.error(f"No se pudo conectar con Gmail: {exc}")
        return False


def _ejecutar_limpieza(categorias: list[str]) -> dict | None:
    """Llama a limpiar_bandeja con manejo de errores."""
    try:
        from limpiar_correos import limpiar_bandeja
        return limpiar_bandeja(st.session_state.service, categorias=categorias)
    except Exception as exc:
        st.error(f"Error durante la limpieza: {exc}")
        return None


def _mostrar_resultado_cat(r: dict | None, nombre: str):
    if r is None:
        return
    movidos     = r.get("exitos",     0)
    encontrados = r.get("procesados", 0)
    errores     = r.get("errores",    0)
    if encontrados == 0:
        st.info(f"No se encontraron correos en **{nombre}**. La categoría ya estaba vacía.")
    else:
        st.success(
            f"✓ Se movieron a la papelera **{movidos} de {encontrados}** correos de {nombre}."
        )
        if errores:
            st.warning(
                f"No se pudieron mover {errores} correos. "
                "Puedes intentarlo de nuevo más tarde."
            )


# ── Helpers: organizar correos ────────────────────────────────────────────────

def _ejecutar_procesador(dry_run: bool) -> dict:
    try:
        import logging
        import gmail_processor.rules as cfg
        from gmail_processor import GmailProcessor, setup_logging
        cfg.DRY_RUN = dry_run
        setup_logging(level=logging.INFO)
        processor = GmailProcessor(service=st.session_state.service)
        return processor.run()
    except Exception as exc:
        return {"error": str(exc)}


def _cargar_remitentes_frecuentes() -> list[dict]:
    try:
        from collections import Counter
        svc    = st.session_state.service
        result = svc.users().messages().list(
            userId="me", q="in:inbox", maxResults=500,
        ).execute()
        stubs  = result.get("messages", [])[:150]
        counts: Counter     = Counter()
        names:  dict[str, str] = {}
        for stub in stubs:
            try:
                msg = svc.users().messages().get(
                    userId="me", id=stub["id"],
                    format="metadata", metadataHeaders=["From"],
                ).execute()
                raw = next(
                    (h["value"] for h in msg.get("payload", {}).get("headers", [])
                     if h["name"].lower() == "from"),
                    "",
                )
                if "<" in raw:
                    email = raw.split("<")[1].rstrip(">").strip().lower()
                    name  = raw.split("<")[0].strip().strip('"').strip("'")
                else:
                    email = raw.strip().lower()
                    name  = ""
                if email:
                    counts[email] += 1
                    if email not in names and name:
                        names[email] = name
            except Exception:
                continue
        return [
            {"email": e, "name": names.get(e, ""), "count": c}
            for e, c in counts.most_common(15)
        ]
    except Exception as exc:
        st.error(f"Error al cargar remitentes: {exc}")
        return []


def _limpiar_remitente(email: str) -> dict | None:
    try:
        from limpiar_correos import limpiar_bandeja
        return limpiar_bandeja(
            st.session_state.service,
            query_custom=f"from:{email}",
        )
    except Exception as exc:
        st.error(f"Error: {exc}")
        return None


_FREE_EMAIL_PROVIDERS = frozenset([
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.mx",
    "live.com", "live.com.mx", "icloud.com", "protonmail.com", "proton.me",
    "me.com", "aol.com", "msn.com",
])


def _derivar_label(email: str, name: str) -> str:
    """Derive a short uppercase label from display name or domain.
    For free email providers uses the local part (e.g. papa@gmail.com → PAPA)."""
    if name:
        word  = name.strip().split()[0]
        clean = "".join(c for c in word if c.isalpha())[:10]
        if clean:
            return clean.upper()
    domain = email.split("@")[-1] if "@" in email else ""
    local  = email.split("@")[0]  if "@" in email else email
    if domain in _FREE_EMAIL_PROVIDERS:
        clean = "".join(c for c in local if c.isalpha())[:10]
        if clean:
            return clean.upper()
    if domain:
        part  = domain.split(".")[0]
        clean = "".join(c for c in part if c.isalpha())[:8]
        if clean:
            return clean.upper()
    return "CONTACTO"


def _proteger_remitente(email: str, name: str) -> dict:
    """
    Adds email to CONTACT_RULES in gmail_processor/rules.py, then reloads the module.
    Returns {"success": True, "label": str} | {"already_protected": True} | {"error": str}.
    """
    try:
        import importlib
        import gmail_processor.rules as rules_mod

        if email in rules_mod.CONTACT_RULES:
            return {"already_protected": True}

        label      = _derivar_label(email, name)
        rules_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "gmail_processor", "rules.py",
        )

        content = open(rules_path, encoding="utf-8").read()
        lines   = content.split("\n")

        # Find the closing } of CONTACT_RULES by tracking brace depth
        in_cr     = False
        depth     = 0
        insert_at = -1
        for i, line in enumerate(lines):
            if not in_cr:
                if "CONTACT_RULES" in line and "=" in line and "{" in line:
                    in_cr = True
                    depth = line.count("{") - line.count("}")
            else:
                depth += line.count("{") - line.count("}")
                if depth <= 0:
                    insert_at = i
                    break

        if insert_at == -1:
            return {"error": "No se encontró CONTACT_RULES en rules.py"}

        new_line = f'    "{email}": {{"label": "{label}", "mark_important": True}},'
        lines.insert(insert_at, new_line)

        with open(rules_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        importlib.reload(rules_mod)
        return {"success": True, "email": email, "label": label}
    except Exception as exc:
        return {"error": str(exc)}


# ── Helpers: panel avanzado ───────────────────────────────────────────────────

def _cargar_stats() -> dict:
    try:
        from gmail_processor.learning_engine import LearningEngine
        from gmail_processor.audit_log import AuditLogger
        engine = LearningEngine()
        return {
            "summary":      engine.summary(),
            "metrics":      engine.metrics.summary(),
            "cat_model":    engine.state.get("category_model", {}),
            "audit_counts": AuditLogger().stats_summary(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def _cargar_audit(last: int, decision: str | None) -> list[dict]:
    try:
        from gmail_processor.audit_log import AuditLogger
        entries = AuditLogger().recent(max(last * 3, 200))
        if decision:
            entries = [e for e in entries if e.get("decision") == decision]
        return entries[-last:]
    except Exception as exc:
        st.error(f"Error al cargar audit log: {exc}")
        return []


def _enviar_feedback(sender: str, outcome: str, rule: str) -> dict | None:
    try:
        import logging
        from gmail_processor import setup_logging
        from gmail_processor.learning_engine import LearningEngine, FeedbackEvent
        setup_logging(level=logging.WARNING)
        domain = sender.split("@")[-1] if "@" in sender else sender
        engine = LearningEngine()
        event  = FeedbackEvent(
            outcome=outcome, source="manual",
            rule_name=rule, time_to_action=None,
        )
        result = engine.update_from_feedback(sender=sender, domain=domain, event=event)
        engine.persist()
        return {
            "accepted":      result.accepted,
            "confidence":    result.confidence,
            "status":        (
                "ACEPTADO" if result.accepted
                else "EN ESPERA" if result.pending_count > 0
                else "BLOQUEADO"
            ),
            "gate_reason":   result.gate_reason,
            "impact":        result.impact,
            "pending_count": result.pending_count,
            "drift_capped":  result.drift_capped,
        }
    except Exception as exc:
        st.error(f"Error al enviar feedback: {exc}")
        return None


def _ejecutar_smart_setup(scan_days: int | None, status_ph) -> dict:
    """
    Runs SmartSetup.analyze() and updates `status_ph` (an st.empty placeholder)
    in real-time with running message counts.
    scan_days=None means all-time (no date filter).
    """
    try:
        from gmail_processor.smart_setup import SmartSetup

        _counters = {"sent": 0, "inbox": 0}

        def _cb(scanned: int, phase: str, page: int = 0):
            _counters[phase] = scanned
            if phase == "sent":
                status_ph.info(
                    f"📤 Indexando mensajes enviados… "
                    f"**{scanned:,}** mensajes  |  página {page}"
                )
            else:
                status_ph.info(
                    f"📥 Analizando inbox… "
                    f"**{scanned:,}** mensajes procesados  |  página {page}"
                )

        status_ph.info("Preparando análisis…")
        setup             = SmartSetup(st.session_state.service)
        contacts, domains = setup.analyze(scan_days=scan_days, progress_cb=_cb)
        status_ph.success(
            f"Análisis completado — "
            f"{_counters['sent']:,} enviados + {_counters['inbox']:,} recibidos procesados."
        )
        return {
            "contacts": [
                {
                    "email":       c.email,
                    "name":        c.name,
                    "domain_type": c.domain_type,
                    "score":       c.score,
                    "count":       c.count,
                    "replied":     c.replied,
                }
                for c in contacts
            ],
            "domains": [
                {
                    "domain":      d.domain,
                    "label":       d.label,
                    "action":      d.action,
                    "total_msgs":  d.total_msgs,
                    "domain_type": d.domain_type,
                }
                for d in domains
            ],
            "sent_total":  _counters["sent"],
            "inbox_total": _counters["inbox"],
        }
    except Exception as exc:
        return {"error": str(exc)}


def _ejecutar_debug() -> tuple[dict, str]:
    import logging
    import gmail_processor.rules as cfg
    from gmail_processor import GmailProcessor

    cfg.DRY_RUN   = True
    log_lines: list[str] = []

    class _BufHandler(logging.Handler):
        def emit(self, record):
            log_lines.append(self.format(record))

    handler = _BufHandler(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s"))
    root       = logging.getLogger("gmail_processor")
    prev_level = root.level
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)
    try:
        processor = GmailProcessor(service=st.session_state.service)
        stats     = processor.run()
        return stats, "\n".join(log_lines)
    except Exception as exc:
        return {"error": str(exc)}, "\n".join(log_lines)
    finally:
        root.removeHandler(handler)
        root.setLevel(prev_level)


# ── Helpers: analizador de contactos ─────────────────────────────────────────

def _ca_get_analyzer():
    from gmail_processor.contact_analyzer import ContactAnalyzer
    return ContactAnalyzer(st.session_state.service)


def _ca_run_batch(days_range: int | None, batch_size: int, status_ph) -> dict:
    try:
        analyzer  = _ca_get_analyzer()
        _counters = {"scanned": 0, "auto": 0, "pending": 0}

        def _cb(scanned, total_estimated, new_pending, new_auto, phase="inbox", page=0):
            _counters["scanned"]  = scanned
            _counters["auto"]    += new_auto
            _counters["pending"] += new_pending
            if phase == "sent":
                status_ph.info(
                    f"📤 Indexando enviados… **{scanned:,}** mensajes | página {page}"
                )
            else:
                status_ph.info(
                    f"📥 Escaneando inbox… **{scanned:,}** correos procesados | "
                    f"auto: {_counters['auto']} | para revisar: {_counters['pending']}"
                )

        result = analyzer.analyze_batch(
            days_range=days_range,
            batch_size=batch_size,
            progress_cb=_cb,
        )
        result["pending_list"] = analyzer.get_pending()
        result["stats"]        = analyzer.get_stats()
        return result
    except Exception as exc:
        return {"error": str(exc)}


def _ca_apply(decisions: dict) -> dict:
    try:
        analyzer = _ca_get_analyzer()
        result   = analyzer.apply_decisions(decisions)
        result["stats"] = analyzer.get_stats()
        return result
    except Exception as exc:
        return {"error": str(exc)}


def _ca_state_summary() -> dict | None:
    from gmail_processor.contact_analyzer import ContactAnalyzer
    analyzer = ContactAnalyzer(st.session_state.service)
    if not analyzer.has_previous_state():
        return None
    stats = analyzer.get_stats()
    pending = analyzer.get_pending()
    return {
        "stats":           stats,
        "pending_count":   len(pending),
        "pending_list":    pending,
        "last_date":       analyzer.state.get("last_processed_date"),
        "reviewed_count":  len(analyzer.state.get("reviewed", {})),
    }


def _ca_reset():
    from gmail_processor.contact_analyzer import ContactAnalyzer
    ContactAnalyzer(st.session_state.service).reset()


# ── Intentar conectar automáticamente si ya hay token guardado ─────────────────
if st.session_state.service is None and os.path.exists("token.json"):
    _init_service()

# ══════════════════════════════════════════════════════════════════════════════
# CONTENIDO DE LA PÁGINA
# ══════════════════════════════════════════════════════════════════════════════

st.title("📧 Limpieza de Gmail")
st.markdown(
    """
    Mueve correos innecesarios a la papelera para liberar espacio y ordenar tu bandeja.

    > **¿Se borran para siempre?** No. Los correos van a la **Papelera de Gmail** y
    > permanecen allí **30 días**. Durante ese tiempo puedes entrar a Gmail, abrir la
    > Papelera y recuperar cualquier correo que quieras conservar.
    """
)

# ── Tutorial ───────────────────────────────────────────────────────────────────
with st.expander("📖 ¿Cómo usar esta página? — Haz clic para ver la guía"):
    st.markdown(
        """
        ### ¿Qué es cada categoría de correos?

        | Categoría | Qué contiene |
        |---|---|
        | 🚫 **Spam** | Correos no deseados detectados automáticamente por Gmail |
        | 📢 **Promociones** | Ofertas, descuentos, newsletters de tiendas y servicios |
        | 👥 **Social** | Notificaciones de Facebook, Instagram, LinkedIn, YouTube… |
        | 🔔 **Actualizaciones** | Recibos de compra, confirmaciones, alertas de apps |
        | 💬 **Foros** | Listas de correo, grupos de discusión, boletines de comunidades |

        ---

        ### ¿Mover a la papelera es lo mismo que borrar?

        **No.** Hay una diferencia importante:

        - **Mover a la papelera** (lo que hace esta herramienta): el correo sigue
          existiendo en Gmail. Puedes abrirlo y recuperarlo en cualquier momento durante 30 días.
        - **Borrar definitivamente**: ocurre solo si Gmail vacía la papelera automáticamente
          pasados 30 días, o si tú haces clic en "Vaciar papelera" manualmente.

        ---

        ### ¿En qué orden conviene limpiar?

        1. **Spam** primero — ya están marcados como no deseados, es lo más seguro.
        2. **Promociones** — es la categoría que más correos acumula normalmente.
        3. **Social** si no necesitas las notificaciones de redes sociales.
        4. **Actualizaciones** con más cuidado — revisa antes de limpiar si hay
           recibos importantes que necesites.
        5. ¿Quieres hacerlo todo de una vez? Usa **Limpiar todo** al final de la página.

        ---

        ### ¿Cómo recuperar un correo si me equivoqué?

        1. Abre [Gmail](https://mail.google.com) en tu navegador.
        2. En el menú izquierdo, haz clic en **Más** y luego en **Papelera**.
        3. Encuentra el correo que quieres conservar.
        4. Ábrelo y selecciona **Mover a la bandeja de entrada**.

        Tienes **30 días** para recuperarlo desde que fue movido.
        """
    )

st.divider()

# ── Estado de conexión ─────────────────────────────────────────────────────────
if st.session_state.service is not None:
    st.success("✅ Conectado con Gmail — listo para limpiar")
else:
    st.warning(
        "Para usar esta herramienta necesitas conectar tu cuenta de Gmail. "
        "Al hacer clic se abrirá una ventana en el navegador para que autorices el acceso. "
        "Esta aplicación no almacena ni comparte tu contraseña."
    )
    if st.button("🔑 Conectar con Gmail", type="primary", use_container_width=True):
        with st.spinner("Abriendo ventana de autorización de Gmail…"):
            ok = _init_service()
        if ok:
            st.rerun()

connected = st.session_state.service is not None

st.divider()

# ── Categorías individuales ────────────────────────────────────────────────────
st.header("Limpiar por categoría")
st.caption(
    "Elige la categoría que quieres limpiar. "
    "Siempre se te pedirá confirmación antes de mover nada."
)
st.write("")

for cat in CATS:
    k = cat["key"]

    with st.container(border=True):
        left, right = st.columns([1, 11])
        with left:
            st.markdown(f"### {cat['icon']}")
        with right:
            st.subheader(cat["nombre"], divider=False)

        st.markdown(cat["desc"])

        confirm_key = f"confirm_{k}"
        result_key  = f"result_{k}"

        if not st.session_state[confirm_key]:
            st.button(
                f"🗑️ Limpiar {cat['nombre']}",
                key=f"btn_{k}",
                disabled=not connected,
                use_container_width=True,
                on_click=lambda key=k: st.session_state.update({f"confirm_{key}": True}),
            )
        else:
            st.warning(f"👉 {cat['aviso']}")
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    f"✓ Sí, limpiar {cat['nombre']}",
                    key=f"exec_{k}",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner(
                        f"Procesando correos de {cat['nombre']}… "
                        "esto puede tardar unos minutos."
                    ):
                        r = _ejecutar_limpieza([k])
                    st.session_state[result_key]  = r
                    st.session_state[confirm_key] = False
                    st.rerun()
            with c2:
                if st.button(
                    "✗ Cancelar",
                    key=f"cancel_{k}",
                    use_container_width=True,
                ):
                    st.session_state[confirm_key] = False
                    st.rerun()

        _mostrar_resultado_cat(st.session_state[result_key], cat["nombre"])

st.divider()

# ── Limpiar todo ───────────────────────────────────────────────────────────────
st.header("🧹 Limpiar todo de una vez")
st.markdown(
    """
    Limpia **todas las categorías** en una sola operación:
    Spam, Promociones, Social, Actualizaciones y Foros.

    Ideal para hacer una limpieza completa de correos acumulados.
    Puede tardar varios minutos dependiendo de cuántos correos tengas.
    """
)
st.error(
    "⚠️ **Aviso importante:** esta opción moverá a la papelera TODOS los correos "
    "de Spam, Promociones, Social, Actualizaciones y Foros **al mismo tiempo**. "
    "Podrás revisarlos y recuperarlos desde la Papelera de Gmail durante 30 días."
)

if not st.session_state["confirm_todo"]:
    st.button(
        "🧹 Limpiar todo",
        key="btn_todo",
        type="primary",
        disabled=not connected,
        use_container_width=True,
        on_click=lambda: st.session_state.update({"confirm_todo": True}),
    )
else:
    st.warning(
        "¿Confirmas que quieres limpiar **todas las categorías** a la vez? "
        "Esta operación moverá a la papelera todos los correos de Spam, Promociones, "
        "Social, Actualizaciones y Foros."
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "✓ Sí, limpiar todo",
            key="exec_todo",
            type="primary",
            use_container_width=True,
        ):
            _ORDEN = ["spam", "promociones", "social", "actualizaciones", "foros"]
            resultados = {}
            progress = st.progress(0, text="Iniciando limpieza…")
            for i, cat_key in enumerate(_ORDEN):
                nombre_cat = _TODO_NOMBRE[cat_key]
                progress.progress(
                    i / len(_ORDEN),
                    text=f"Limpiando {nombre_cat}… ({i + 1} de {len(_ORDEN)})",
                )
                r = _ejecutar_limpieza([cat_key])
                if r is not None:
                    resultados[cat_key] = r
            progress.progress(1.0, text="¡Limpieza completada!")
            st.session_state["result_todo"]  = resultados
            st.session_state["confirm_todo"] = False
            st.rerun()
    with c2:
        if st.button("✗ Cancelar", key="cancel_todo", use_container_width=True):
            st.session_state["confirm_todo"] = False
            st.rerun()

# Resultados de "limpiar todo"
if st.session_state["result_todo"] is not None:
    resultados = st.session_state["result_todo"]
    total_encontrados = sum(r.get("procesados", 0) for r in resultados.values())
    total_movidos     = sum(r.get("exitos",     0) for r in resultados.values())

    if total_encontrados == 0:
        st.info("No se encontraron correos en ninguna categoría. Tu bandeja ya estaba limpia.")
    else:
        st.success(
            f"✓ Limpieza completa: **{total_movidos} de {total_encontrados}** "
            "correos movidos a la papelera."
        )
        with st.expander("Ver desglose por categoría"):
            for cat_key, r in resultados.items():
                movidos_cat     = r.get("exitos",     0)
                encontrados_cat = r.get("procesados", 0)
                st.markdown(
                    f"- **{_TODO_NOMBRE.get(cat_key, cat_key)}**: "
                    f"{movidos_cat} de {encontrados_cat} movidos"
                )

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# ORGANIZAR CORREOS
# ══════════════════════════════════════════════════════════════════════════════

st.header("📬 Organizar correos")
st.caption(
    "Clasifica tu bandeja de entrada con reglas inteligentes "
    "y descubre los remitentes que más correos te envían."
)

_org_tab1, _org_tab2 = st.tabs(["🔄 Procesar inbox", "📊 Remitentes frecuentes"])

with _org_tab1:
    st.markdown(
        """
        Analiza los correos de tu bandeja de entrada y aplica etiquetas automáticamente
        según las reglas configuradas. Identifica contactos importantes, publicidad,
        y mensajes candidatos a mover a la papelera.
        """
    )
    _dry = st.toggle(
        "Modo simulación — ver decisiones sin aplicar cambios reales",
        value=True,
        key="proc_dry_run",
        disabled=not connected,
        help="Con esto activo el procesador solo muestra qué haría, sin modificar tu Gmail.",
    )
    if not st.session_state["confirm_proc"]:
        st.button(
            "🔍 Simular procesamiento del inbox" if _dry else "🔄 Procesar inbox (cambios reales)",
            key="btn_proc",
            type="secondary" if _dry else "primary",
            disabled=not connected,
            use_container_width=True,
            on_click=lambda: st.session_state.update({"confirm_proc": True}),
        )
    else:
        _mode_txt = "simulación (sin cambios)" if _dry else "REAL — se etiquetarán y moverán correos"
        st.warning(f"¿Confirmas procesar el inbox en modo **{_mode_txt}**?")
        _pc1, _pc2 = st.columns(2)
        with _pc1:
            if st.button("✓ Sí, procesar", key="exec_proc", type="primary", use_container_width=True):
                with st.spinner("Procesando correos… esto puede tardar unos minutos."):
                    _pr = _ejecutar_procesador(dry_run=_dry)
                st.session_state["proc_result"]  = _pr
                st.session_state["confirm_proc"] = False
                st.rerun()
        with _pc2:
            if st.button("✗ Cancelar", key="cancel_proc", use_container_width=True):
                st.session_state["confirm_proc"] = False
                st.rerun()

    _proc_r = st.session_state["proc_result"]
    if _proc_r is not None:
        if "error" in _proc_r:
            st.error(f"Error: {_proc_r['error']}")
        else:
            _n = _proc_r.get("processed", 0)
            if _n == 0:
                st.info("No se encontraron correos para procesar. La bandeja ya estaba vacía o el filtro no dio resultados.")
            else:
                st.success(f"✓ Se analizaron **{_n}** correos.")
                _m1, _m2, _m3, _m4, _m5 = st.columns(5)
                _m1.metric("Etiquetados", _proc_r.get("labeled",   0))
                _m2.metric("Importantes", _proc_r.get("important", 0))
                _m3.metric("Archivados",  _proc_r.get("archived",  0))
                _m4.metric("Papelera",    _proc_r.get("trashed",   0))
                _m5.metric("Omitidos",    _proc_r.get("skipped",   0))
                if _proc_r.get("errors", 0):
                    st.warning(f"No se pudieron procesar {_proc_r['errors']} correos por errores de API.")

with _org_tab2:
    st.markdown(
        "Muestra los 15 remitentes con más correos en tu bandeja de entrada "
        "(análisis de los últimos 150 mensajes). "
        "Puedes mover todos los correos de un remitente a la papelera desde aquí."
    )
    if st.button("🔍 Cargar remitentes", key="btn_load_senders", disabled=not connected):
        with st.spinner("Analizando los últimos 150 correos del inbox…"):
            _sd = _cargar_remitentes_frecuentes()
        st.session_state["senders_data"] = _sd
        st.rerun()

    _senders = st.session_state["senders_data"]
    if _senders is None:
        st.info("Haz clic en 'Cargar remitentes' para ver los remitentes con más correos.")
    elif not _senders:
        st.info("No se encontraron remitentes en la bandeja de entrada.")
    else:
        st.caption(
            "🛡️ **Contactos protegidos**: al proteger un remitente, sus correos nunca serán "
            "eliminados por ninguna operación de limpieza, aunque Gmail los clasifique como "
            "promociones o tengan muchos mensajes acumulados."
        )
        st.write("")
        for _si, _sndr in enumerate(_senders):
            _se_email    = _sndr["email"]
            _se_name     = _sndr.get("name", "")
            _se_count    = _sndr["count"]
            _se_label    = f"{_se_name} <{_se_email}>" if _se_name else _se_email
            _confirm_sk  = f"confirm_trash_sender_{_si}"
            _result_sk   = f"result_trash_sender_{_si}"
            _confirm_psk = f"confirm_protect_sender_{_si}"
            _result_psk  = f"result_protect_sender_{_si}"
            st.session_state.setdefault(_confirm_sk,  False)
            st.session_state.setdefault(_result_sk,   None)
            st.session_state.setdefault(_confirm_psk, False)
            st.session_state.setdefault(_result_psk,  None)

            _s_c1, _s_c2, _s_c3, _s_c4 = st.columns([6, 1, 2, 2])
            with _s_c1:
                st.markdown(f"**{_se_label}**")
            with _s_c2:
                st.caption(f"{_se_count}")

            # ── Botón Limpiar ──────────────────────────────────────────────────
            with _s_c3:
                if not st.session_state[_confirm_sk]:
                    st.button(
                        "🗑️ Limpiar",
                        key=f"btn_ts_{_si}",
                        use_container_width=True,
                        disabled=not connected,
                        on_click=lambda k=_confirm_sk: st.session_state.update({k: True}),
                    )
                else:
                    st.warning(f"¿Mover **todos** los correos de **{_se_email}** a la papelera?")
                    _ts_c1, _ts_c2 = st.columns(2)
                    with _ts_c1:
                        if st.button("✓ Sí", key=f"exec_ts_{_si}", type="primary", use_container_width=True):
                            with st.spinner(f"Limpiando correos de {_se_email}…"):
                                _ts_r = _limpiar_remitente(_se_email)
                            st.session_state[_result_sk]  = _ts_r
                            st.session_state[_confirm_sk] = False
                            st.rerun()
                    with _ts_c2:
                        if st.button("✗ No", key=f"cancel_ts_{_si}", use_container_width=True):
                            st.session_state[_confirm_sk] = False
                            st.rerun()

            # ── Botón Proteger ─────────────────────────────────────────────────
            with _s_c4:
                if not st.session_state[_confirm_psk]:
                    st.button(
                        "🛡️ Proteger",
                        key=f"btn_ps_{_si}",
                        use_container_width=True,
                        disabled=not connected,
                        on_click=lambda k=_confirm_psk: st.session_state.update({k: True}),
                    )
                else:
                    st.info(f"¿Agregar **{_se_email}** a los contactos protegidos?")
                    _ps_c1, _ps_c2 = st.columns(2)
                    with _ps_c1:
                        if st.button("✓ Sí", key=f"exec_ps_{_si}", type="primary", use_container_width=True):
                            _ps_r = _proteger_remitente(_se_email, _se_name)
                            st.session_state[_result_psk]  = _ps_r
                            st.session_state[_confirm_psk] = False
                            st.rerun()
                    with _ps_c2:
                        if st.button("✗ No", key=f"cancel_ps_{_si}", use_container_width=True):
                            st.session_state[_confirm_psk] = False
                            st.rerun()

            # ── Resultados ────────────────────────────────────────────────────
            if st.session_state.get(_result_sk):
                _ts_res = st.session_state[_result_sk]
                _ts_mov = _ts_res.get("exitos",     0)
                _ts_tot = _ts_res.get("procesados", 0)
                if _ts_tot == 0:
                    st.info(f"No se encontraron correos de {_se_email}.")
                else:
                    st.success(f"✓ {_ts_mov} de {_ts_tot} correos de {_se_email} movidos a la papelera.")

            if st.session_state.get(_result_psk):
                _ps_res = st.session_state[_result_psk]
                if _ps_res.get("already_protected"):
                    st.info(f"{_se_email} ya estaba en la lista de contactos protegidos.")
                elif _ps_res.get("success"):
                    st.success(
                        f"🛡️ **{_se_email}** agregado a contactos protegidos "
                        f"con etiqueta **{_ps_res['label']}**. "
                        "Sus correos nunca serán eliminados."
                    )
                elif _ps_res.get("error"):
                    st.error(f"Error al proteger: {_ps_res['error']}")

            st.markdown("---")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# ANALIZAR CORREOS
# ══════════════════════════════════════════════════════════════════════════════

st.header("🔬 Analizar correos")
st.caption(
    "Revisa quién te escribe y decide qué hacer con cada remitente: "
    "protegerlo, mandarlo a la papelera, u omitirlo."
)

_ANALYZE_RANGES = {
    "Últimos 3 meses":   90,
    "Últimos 6 meses":   180,
    "Último año":        365,
    "Últimos 2 años":    730,
    "Todo el historial": None,
}

_ca_col1, _ca_col2 = st.columns([3, 1])
with _ca_col1:
    _ca_range_label = st.selectbox(
        "Rango de análisis",
        options=list(_ANALYZE_RANGES.keys()),
        index=1,
        key="ca_range",
        disabled=not connected,
    )
with _ca_col2:
    _ca_batch_size = st.number_input(
        "Correos por lote",
        min_value=50, max_value=500, value=200, step=50,
        key="ca_batch_size",
        disabled=not connected,
    )

_ca_days = _ANALYZE_RANGES[_ca_range_label]

# Estado previo
if connected:
    try:
        _ca_prev = _ca_state_summary()
    except Exception:
        _ca_prev = None
else:
    _ca_prev = None

if _ca_prev:
    _cp_stats   = _ca_prev["stats"]
    _cp_rev     = _ca_prev["reviewed_count"]
    _cp_pend    = _ca_prev["pending_count"]
    _cp_date    = (_ca_prev["last_date"] or "")[:19].replace("T", " ")
    st.info(
        f"**Análisis anterior** ({_cp_date}): "
        f"**{_cp_rev}** remitentes revisados — "
        f"{_cp_stats.get('personal', 0)} personales, "
        f"{_cp_stats.get('spam', 0)} spam. "
        f"**{_cp_pend}** pendientes por revisar."
    )
    _ca_btn_col1, _ca_btn_col2, _ca_btn_col3 = st.columns(3)
    with _ca_btn_col1:
        _ca_btn_continue = st.button(
            "▶ Continuar análisis",
            key="btn_ca_continue",
            disabled=not connected,
            use_container_width=True,
        )
    with _ca_btn_col2:
        _ca_btn_new = st.button(
            "🔄 Nuevo análisis",
            key="btn_ca_new",
            disabled=not connected,
            use_container_width=True,
        )
    with _ca_btn_col3:
        _ca_btn_review = st.button(
            f"📋 Solo revisar pendientes ({_cp_pend})",
            key="btn_ca_review",
            disabled=not connected or _cp_pend == 0,
            use_container_width=True,
        )

    if _ca_btn_new:
        _ca_reset()
        st.session_state["ca_batch_result"] = None
        st.session_state["ca_apply_result"] = None
        st.session_state["ca_decisions"]    = {}
        st.rerun()

    if _ca_btn_review:
        # Load existing pending without scanning
        st.session_state["ca_batch_result"] = {
            "auto_personal":    0,
            "auto_spam":        0,
            "pending":          _cp_pend,
            "already_reviewed": _cp_rev,
            "scanned":          0,
            "pending_list":     _ca_prev["pending_list"],
            "stats":            _cp_stats,
            "review_only":      True,
        }
        st.rerun()

    if _ca_btn_continue:
        _ca_status = st.empty()
        _ca_r = _ca_run_batch(_ca_days, int(_ca_batch_size), _ca_status)
        st.session_state["ca_batch_result"] = _ca_r
        st.session_state["ca_decisions"]    = {}
        st.rerun()

else:
    if st.button(
        "🔍 Analizar siguiente lote",
        key="btn_ca_start",
        type="primary",
        disabled=not connected,
        use_container_width=True,
    ):
        _ca_status = st.empty()
        _ca_r = _ca_run_batch(_ca_days, int(_ca_batch_size), _ca_status)
        st.session_state["ca_batch_result"] = _ca_r
        st.session_state["ca_decisions"]    = {}
        st.rerun()

# ── Resultados del lote ───────────────────────────────────────────────────────
_ca_batch = st.session_state["ca_batch_result"]
if _ca_batch is not None:
    if "error" in _ca_batch:
        st.error(f"Error en el análisis: {_ca_batch['error']}")
    else:
        _cb_auto_p  = _ca_batch.get("auto_personal",    0)
        _cb_auto_s  = _ca_batch.get("auto_spam",        0)
        _cb_pend    = _ca_batch.get("pending",           0)
        _cb_already = _ca_batch.get("already_reviewed",  0)
        _cb_scanned = _ca_batch.get("scanned",           0)
        _cb_review_only = _ca_batch.get("review_only",  False)

        if not _cb_review_only and _cb_scanned > 0:
            st.success(
                f"**Lote completado**: {_cb_scanned:,} correos escaneados — "
                f"{_cb_already} ya revisados, "
                f"{_cb_auto_p + _cb_auto_s} clasificados automáticamente "
                f"({_cb_auto_p} personales + {_cb_auto_s} spam), "
                f"**{_cb_pend} para revisar**."
            )

        # ── Tabla de pendientes ───────────────────────────────────────────────
        _pend_list = _ca_batch.get("pending_list", [])
        if not _pend_list:
            st.info("No hay remitentes pendientes de revisión. Todo fue clasificado automáticamente.")
        else:
            st.subheader(f"📋 Revisión de pendientes ({len(_pend_list)} remitentes)")
            st.caption(
                "Decide qué hacer con cada remitente. "
                "Los contactos ya revisados no volverán a aparecer."
            )

            _decisions = st.session_state["ca_decisions"]

            # Header row
            _ph1, _ph2, _ph3, _ph4, _ph5 = st.columns([4, 2, 1, 3, 3])
            _ph1.markdown("**Remitente**")
            _ph2.markdown("**Señales**")
            _ph3.markdown("**Score**")
            _ph4.markdown("")
            _ph5.markdown("")

            st.markdown("---")

            for _pi, _ps in enumerate(_pend_list):
                _pa  = _ps["email"]
                _pn  = _ps.get("name", "")
                _psc = _ps.get("score", 0)
                _psi = _ps.get("signals", [])
                _lbl = f"{_pn} <{_pa}>" if _pn else _pa
                _dec = _decisions.get(_pa)

                _pc1, _pc2, _pc3, _pc4, _pc5 = st.columns([4, 2, 1, 3, 3])
                with _pc1:
                    st.markdown(f"**{_lbl}**")
                    if _psi:
                        st.caption(" · ".join(_psi[:2]))
                with _pc2:
                    if len(_psi) > 2:
                        with st.expander("ver señales"):
                            for _sig in _psi:
                                st.caption(_sig)
                    else:
                        st.write("")
                with _pc3:
                    _score_color = "🟢" if _psc >= 55 else "🟡" if _psc >= 40 else "🔴"
                    st.markdown(f"{_score_color} **{_psc}**")

                with _pc4:
                    _btn_label_p = "🛡️ Personal ✓" if _dec == "personal" else "🛡️ Personal"
                    if st.button(
                        _btn_label_p,
                        key=f"ca_personal_{_pi}",
                        type="primary" if _dec == "personal" else "secondary",
                        use_container_width=True,
                    ):
                        _decisions[_pa] = "personal"
                        st.session_state["ca_decisions"] = _decisions
                        st.rerun()

                with _pc5:
                    _btn_col_a, _btn_col_b = st.columns(2)
                    with _btn_col_a:
                        _btn_label_s = "🗑️ Spam ✓" if _dec == "spam" else "🗑️ Spam"
                        if st.button(
                            _btn_label_s,
                            key=f"ca_spam_{_pi}",
                            type="primary" if _dec == "spam" else "secondary",
                            use_container_width=True,
                        ):
                            _decisions[_pa] = "spam"
                            st.session_state["ca_decisions"] = _decisions
                            st.rerun()
                    with _btn_col_b:
                        _btn_label_o = "⏭️ Omitir ✓" if _dec == "skip" else "⏭️ Omitir"
                        if st.button(
                            _btn_label_o,
                            key=f"ca_skip_{_pi}",
                            use_container_width=True,
                        ):
                            _decisions[_pa] = "skip"
                            st.session_state["ca_decisions"] = _decisions
                            st.rerun()

                st.markdown("---")

            # ── Aplicar decisiones ────────────────────────────────────────────
            _decided_count = len(_decisions)
            _total_pend    = len(_pend_list)
            if _decided_count > 0:
                st.info(
                    f"**{_decided_count} de {_total_pend}** remitentes con decisión asignada. "
                    f"({_total_pend - _decided_count} sin decidir — quedarán pendientes)"
                )
                if st.button(
                    f"✅ Aplicar {_decided_count} decisiones",
                    key="btn_ca_apply",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner("Aplicando decisiones…"):
                        _apply_r = _ca_apply(_decisions)
                    st.session_state["ca_apply_result"] = _apply_r
                    st.session_state["ca_decisions"]    = {}
                    # Refresh pending list
                    try:
                        _new_prev = _ca_state_summary()
                        if _new_prev:
                            st.session_state["ca_batch_result"]["pending_list"] = (
                                _new_prev["pending_list"]
                            )
                            st.session_state["ca_batch_result"]["stats"] = (
                                _new_prev["stats"]
                            )
                    except Exception:
                        pass
                    st.rerun()

# ── Resultado de aplicar decisiones ──────────────────────────────────────────
_ca_apply_r = st.session_state["ca_apply_result"]
if _ca_apply_r is not None:
    if "error" in _ca_apply_r:
        st.error(f"Error al aplicar: {_ca_apply_r['error']}")
    else:
        _apr_p  = _ca_apply_r.get("protected",       0)
        _apr_ts = _ca_apply_r.get("trashed_senders",  0)
        _apr_tm = _ca_apply_r.get("trashed_msgs",     0)
        _apr_e  = _ca_apply_r.get("errors",           [])
        _apr_st = _ca_apply_r.get("stats",            {})

        st.success(
            f"✓ Decisiones aplicadas — "
            f"**{_apr_p}** contactos protegidos · "
            f"**{_apr_ts}** remitentes de spam eliminados "
            f"({_apr_tm} correos movidos a la papelera)."
        )
        if _apr_e:
            with st.expander(f"⚠️ {len(_apr_e)} errores al aplicar"):
                for _e in _apr_e:
                    st.caption(_e)

        if _apr_st:
            _as1, _as2, _as3 = st.columns(3)
            _as1.metric("Personales (total)", _apr_st.get("personal",   0))
            _as2.metric("Spam (total)",        _apr_st.get("spam",       0))
            _as3.metric("Escaneados (total)",  _apr_st.get("total_scanned", 0))

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# OPCIONES AVANZADAS
# ══════════════════════════════════════════════════════════════════════════════

with st.expander("⚙️ Opciones avanzadas"):
    _adv_tabs = st.tabs(
        ["📈 Estadísticas", "📋 Audit log", "💬 Feedback", "🔧 Config. inicial", "🐛 Debug"]
    )

    # ── Estadísticas ──────────────────────────────────────────────────────────
    with _adv_tabs[0]:
        st.markdown("Métricas del motor de aprendizaje, calidad de las reglas y resumen del audit log.")
        if st.button("🔄 Actualizar estadísticas", key="btn_load_stats"):
            with st.spinner("Cargando estadísticas…"):
                _stats = _cargar_stats()
            st.session_state["stats_data"] = _stats
            st.rerun()

        _stats_d = st.session_state["stats_data"]
        if _stats_d is None:
            st.info("Haz clic en 'Actualizar estadísticas' para ver las métricas.")
        elif "error" in _stats_d:
            st.error(f"Error: {_stats_d['error']}")
        else:
            st.subheader("Estado de aprendizaje")
            st.code(_stats_d.get("summary", "—"), language=None)

            st.subheader("Métricas de calidad")
            st.code(_stats_d.get("metrics", "—"), language=None)

            st.subheader("Audit log (acumulado)")
            _ac = _stats_d.get("audit_counts", {})
            _ac1, _ac2, _ac3 = st.columns(3)
            _ac1.metric("TRASH", _ac.get("TRASH", 0))
            _ac2.metric("KEEP",  _ac.get("KEEP",  0))
            _ac3.metric("SKIP",  _ac.get("SKIP",  0))

            _cm = _stats_d.get("cat_model", {})
            if _cm:
                st.subheader("Modelo de categorías Gmail")
                _cm_rows = [
                    {
                        "Categoría":   cat,
                        "Papelera":    s.get("trashed", 0),
                        "Conservados": s.get("kept",    0),
                        "Total":       s.get("trashed", 0) + s.get("kept", 0),
                        "Precisión":   f"{(1 - s.get('false_positives',0)/s['trashed']):.1%}"
                                       if s.get("trashed") else "n/a",
                    }
                    for cat, s in _cm.items()
                ]
                st.dataframe(_cm_rows, use_container_width=True)

    # ── Audit log ─────────────────────────────────────────────────────────────
    with _adv_tabs[1]:
        st.markdown("Registro de decisiones tomadas por el procesador en ejecuciones anteriores.")
        _al_c1, _al_c2, _al_c3 = st.columns([2, 2, 1])
        with _al_c1:
            _al_decision = st.selectbox(
                "Filtrar por decisión",
                options=["Todas", "TRASH", "KEEP", "SKIP"],
                key="audit_decision_filter",
            )
        with _al_c2:
            _al_last = st.number_input(
                "Últimas N entradas",
                min_value=5, max_value=500, value=20, step=5,
                key="audit_last_n",
            )
        with _al_c3:
            st.write("")
            st.write("")
            if st.button("🔍 Cargar", key="btn_load_audit"):
                _dec_filter = None if _al_decision == "Todas" else _al_decision
                with st.spinner("Cargando audit log…"):
                    _ae = _cargar_audit(int(_al_last), _dec_filter)
                st.session_state["audit_data"] = _ae
                st.rerun()

        _audit_d = st.session_state["audit_data"]
        if _audit_d is None:
            st.info("Haz clic en 'Cargar' para ver el audit log.")
        elif not _audit_d:
            st.info("No hay entradas para el filtro seleccionado.")
        else:
            _audit_rows = [
                {
                    "Hora":       e.get("ts", "")[:19].replace("T", " "),
                    "Decisión":   e.get("decision", ""),
                    "Remitente":  e.get("sender",   "")[:45],
                    "Puntuación": e.get("score",    0),
                    "Regla":      e.get("rule",     ""),
                    "Modo":       "DRY" if e.get("dry_run") else "LIVE",
                }
                for e in _audit_d
            ]
            st.dataframe(_audit_rows, use_container_width=True, hide_index=True)

    # ── Feedback ──────────────────────────────────────────────────────────────
    with _adv_tabs[2]:
        st.markdown(
            """
            Registra feedback sobre una decisión del procesador para mejorar el aprendizaje.
            Úsalo si un correo importante fue mandado a la papelera (incorrecto) o si quieres
            reforzar una decisión correcta.
            """
        )
        with st.form("feedback_form"):
            _fb_sender = st.text_input(
                "Dirección del remitente",
                placeholder="ejemplo@dominio.com",
                help="El email del remitente sobre el que das feedback.",
            )
            _fb_outcome = st.radio(
                "¿La decisión fue...?",
                options=["correct", "incorrect"],
                format_func=lambda x: (
                    "✓ Correcta — el procesador actuó bien"
                    if x == "correct"
                    else "✗ Incorrecta — debería haber actuado diferente"
                ),
                horizontal=True,
            )
            _fb_rule = st.text_input(
                "Nombre de la regla (opcional)",
                placeholder="ej: promotions_60d",
                help="Si sabes qué regla activó la decisión puedes incluirla aquí.",
            )
            _fb_submit = st.form_submit_button(
                "Enviar feedback", type="primary", use_container_width=True
            )

        if _fb_submit:
            if not _fb_sender.strip():
                st.error("Ingresa la dirección de correo del remitente.")
            else:
                with st.spinner("Registrando feedback…"):
                    _fb_r = _enviar_feedback(
                        _fb_sender.strip(), _fb_outcome, _fb_rule.strip()
                    )
                st.session_state["feedback_result"] = _fb_r
                st.rerun()

        _fb_res = st.session_state["feedback_result"]
        if _fb_res is not None:
            if _fb_res.get("accepted"):
                st.success(
                    f"✓ Feedback aceptado — "
                    f"confianza: {_fb_res['confidence']:.2f} | impacto: {_fb_res['impact']}"
                )
            elif _fb_res.get("pending_count", 0) > 0:
                st.info(
                    f"Feedback en espera — "
                    f"se necesitan {_fb_res['pending_count']}/2 repeticiones "
                    f"o confianza ≥ 0.60 para aplicar el ajuste."
                )
            else:
                st.warning(
                    f"Feedback bloqueado — razón: {_fb_res.get('gate_reason', 'desconocida')}"
                )
            if _fb_res.get("drift_capped"):
                st.caption("El delta fue reducido por el límite diario de drift.")

    # ── Config. inicial ───────────────────────────────────────────────────────
    with _adv_tabs[3]:
        st.markdown(
            """
            Analiza tu historial de Gmail para detectar contactos importantes y dominios
            de confianza (bancos, gobierno, empresa). Distingue contactos reales de newsletters
            usando tus respuestas, estrellas y frecuencia de contacto.

            Pagina todos los mensajes del rango elegido sin límite fijo — cuanto más amplio
            el rango, más completo el análisis pero más tiempo tarda.
            """
        )

        _RANGE_OPTIONS = {
            "Últimos 6 meses  (rápido, ~1-2 min)":   180,
            "Últimos 12 meses (recomendado, ~2-4 min)": 365,
            "Últimos 2 años   (~5-10 min)":           730,
            "Todo el historial (puede tardar >10 min)": None,
        }
        _range_label = st.selectbox(
            "Rango de tiempo a analizar",
            options=list(_RANGE_OPTIONS.keys()),
            index=1,
            key="smart_setup_range",
            disabled=not connected,
        )
        _scan_days = _RANGE_OPTIONS[_range_label]
        if _scan_days is None:
            st.warning(
                "Analizar todo el historial puede tardar mucho en cuentas antiguas o con "
                "muchos correos. Si ves que tarda demasiado, cierra la ventana y elige "
                "un rango más corto."
            )

        if st.button(
            "🔍 Iniciar análisis",
            key="btn_smart_setup",
            type="primary",
            disabled=not connected,
            use_container_width=True,
        ):
            _ss_status = st.empty()
            _ss_r = _ejecutar_smart_setup(_scan_days, _ss_status)
            st.session_state["smart_setup_result"] = _ss_r
            st.rerun()

        _ss_res = st.session_state["smart_setup_result"]
        if _ss_res is not None:
            if "error" in _ss_res:
                st.error(f"Error: {_ss_res['error']}")
            else:
                _ss_contacts  = _ss_res.get("contacts",    [])
                _ss_domains   = _ss_res.get("domains",     [])
                _ss_sent_tot  = _ss_res.get("sent_total",  0)
                _ss_inbox_tot = _ss_res.get("inbox_total", 0)
                st.success(
                    f"Análisis completado — "
                    f"**{_ss_sent_tot:,}** mensajes enviados + "
                    f"**{_ss_inbox_tot:,}** recibidos procesados. "
                    f"Resultado: **{len(_ss_contacts)}** contactos sugeridos, "
                    f"**{len(_ss_domains)}** dominios detectados."
                )
                if _ss_contacts:
                    st.subheader("Contactos importantes detectados")
                    st.caption("Ordenados por puntuación. La señal más fuerte es haberles respondido.")
                    _ss_rows = [
                        {
                            "Nombre / Email": f"{c['name']} <{c['email']}>" if c["name"] else c["email"],
                            "Tipo":           c["domain_type"],
                            "Correos":        c["count"],
                            "Respondidos":    c["replied"],
                            "Puntuación":     c["score"],
                        }
                        for c in _ss_contacts
                    ]
                    st.dataframe(_ss_rows, use_container_width=True, hide_index=True)
                else:
                    st.info("No se detectaron contactos por encima del umbral mínimo.")

                if _ss_domains:
                    st.subheader("Dominios de confianza detectados")
                    _icon_map = {"financial": "🏦", "government": "🏛️", "educational": "🎓"}
                    for d in _ss_domains:
                        _ic = _icon_map.get(d["domain_type"], "🌐")
                        st.markdown(
                            f"- {_ic} **{d['domain']}** — "
                            f"etiqueta `{d['label']}`, acción `{d['action']}` "
                            f"({d['total_msgs']} mensajes)"
                        )

    # ── Debug ─────────────────────────────────────────────────────────────────
    with _adv_tabs[4]:
        st.markdown(
            """
            Ejecuta el procesador con nivel de log **DEBUG** para ver la traza completa
            de cada correo: qué reglas se evaluaron, qué puntuación obtuvieron, y por qué
            se tomó cada decisión.

            Siempre corre en **modo simulación** — no modifica tu Gmail.
            """
        )
        if st.button(
            "🐛 Ejecutar con DEBUG",
            key="btn_debug",
            disabled=not connected,
            use_container_width=True,
        ):
            with st.spinner("Ejecutando procesador en modo DEBUG… puede tardar varios minutos."):
                _dbg_stats, _dbg_log = _ejecutar_debug()
            st.session_state["debug_result"] = {"stats": _dbg_stats, "log": _dbg_log}
            st.rerun()

        _dbg_res = st.session_state["debug_result"]
        if _dbg_res is not None:
            _dbg_s = _dbg_res.get("stats", {})
            _dbg_l = _dbg_res.get("log",   "")
            if "error" in _dbg_s:
                st.error(f"Error: {_dbg_s['error']}")
            else:
                _n_dbg = _dbg_s.get("processed", 0)
                st.success(f"✓ Ejecución completada — {_n_dbg} correos procesados (simulación).")
                _d1, _d2, _d3, _d4 = st.columns(4)
                _d1.metric("Etiquetados", _dbg_s.get("labeled",   0))
                _d2.metric("Papelera",    _dbg_s.get("trashed",   0))
                _d3.metric("Archivados",  _dbg_s.get("archived",  0))
                _d4.metric("Omitidos",    _dbg_s.get("skipped",   0))
            if _dbg_l:
                st.subheader("Traza de log completa")
                st.text_area("Log DEBUG", value=_dbg_l, height=450, key="debug_log_area")
