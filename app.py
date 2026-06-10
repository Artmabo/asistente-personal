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
        for _si, _sndr in enumerate(_senders):
            _se_email   = _sndr["email"]
            _se_name    = _sndr.get("name", "")
            _se_count   = _sndr["count"]
            _se_label   = f"{_se_name} <{_se_email}>" if _se_name else _se_email
            _confirm_sk = f"confirm_trash_sender_{_si}"
            _result_sk  = f"result_trash_sender_{_si}"
            st.session_state.setdefault(_confirm_sk, False)
            st.session_state.setdefault(_result_sk,  None)

            _s_c1, _s_c2, _s_c3 = st.columns([6, 1, 2])
            with _s_c1:
                st.markdown(f"**{_se_label}**")
            with _s_c2:
                st.caption(f"{_se_count}")
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
                    st.warning(f"¿Mover todos los correos de **{_se_email}** a la papelera?")
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

            if st.session_state.get(_result_sk):
                _ts_res = st.session_state[_result_sk]
                _ts_mov = _ts_res.get("exitos",     0)
                _ts_tot = _ts_res.get("procesados", 0)
                if _ts_tot == 0:
                    st.info(f"No se encontraron correos de {_se_email}.")
                else:
                    st.success(f"✓ {_ts_mov} de {_ts_tot} correos de {_se_email} movidos a la papelera.")
            st.markdown("---")

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
