"""
Gmail Cleanup — Interfaz web para usuarios no técnicos.
Ejecutar con:  streamlit run app.py
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Configuración de página ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mi Correo",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Session state ───────────────────────────────────────────────────────────────
_CATS_KEYS = ["spam", "promociones", "social", "actualizaciones"]
_ALL_KEYS  = _CATS_KEYS + ["todo"]

st.session_state.setdefault("service",            None)
st.session_state.setdefault("current_page",       "inicio")
for _k in _ALL_KEYS:
    st.session_state.setdefault(f"confirm_{_k}",  False)
    st.session_state.setdefault(f"result_{_k}",   None)

st.session_state.setdefault("confirm_proc",       False)
st.session_state.setdefault("proc_result",        None)
st.session_state.setdefault("senders_data",       None)
st.session_state.setdefault("stats_data",         None)
st.session_state.setdefault("audit_data",         None)
st.session_state.setdefault("feedback_result",    None)
st.session_state.setdefault("smart_setup_result", None)
st.session_state.setdefault("debug_result",       None)
st.session_state.setdefault("ca_batch_result",    None)
st.session_state.setdefault("ca_apply_result",    None)
st.session_state.setdefault("ca_decisions",       {})
st.session_state.setdefault("ca_running",         False)
st.session_state.setdefault("storage_data",       None)
st.session_state.setdefault("cleanup_size_data",  None)
st.session_state.setdefault("schedule_saved",     False)
st.session_state.setdefault("profiler_result",    None)
st.session_state.setdefault("chat_messages",      [])
st.session_state.setdefault("chat_open",          False)
st.session_state.setdefault("chat_input_counter", 0)

# ── Constantes ──────────────────────────────────────────────────────────────────
CATS = [
    dict(
        key="spam", icon="🚫", nombre="Spam",
        desc="Correos no deseados detectados automáticamente por Gmail: publicidad agresiva, intentos de estafa o mensajes sospechosos.",
        aviso="Moverá a la papelera **todos los mensajes de tu carpeta Spam**. Podrás revisarlos y recuperarlos desde la Papelera de Gmail durante 30 días.",
    ),
    dict(
        key="promociones", icon="📢", nombre="Promociones",
        desc="Correos de tiendas y servicios: ofertas, descuentos, newsletters y publicidad. Suelen acumular cientos o miles de mensajes.",
        aviso="Moverá a la papelera **todos los correos de Promociones** (ofertas, descuentos, newsletters). Podrás revisarlos durante 30 días.",
    ),
    dict(
        key="social", icon="👥", nombre="Social",
        desc="Notificaciones de redes sociales: Facebook, Instagram, LinkedIn, Twitter/X, YouTube, TikTok, etc.",
        aviso="Moverá a la papelera **todos los correos de Social** (notificaciones de redes sociales). Podrás revisarlos durante 30 días.",
    ),
    dict(
        key="actualizaciones", icon="🔔", nombre="Actualizaciones",
        desc="Mensajes automáticos: confirmaciones de compra, recibos, alertas de apps y notificaciones de servicios.",
        aviso="Moverá a la papelera **todos los correos de Actualizaciones** (confirmaciones, recibos, alertas). Podrás revisarlos durante 30 días.",
    ),
]

_TODO_NOMBRE = {
    "spam": "Spam", "promociones": "Promociones", "social": "Social",
    "actualizaciones": "Actualizaciones", "foros": "Foros",
}

_ANALYZE_RANGES = {
    "Últimos 3 meses":   90,
    "Últimos 6 meses":   180,
    "Último año":        365,
    "Últimos 2 años":    730,
    "Todo el historial": None,
}

_CAT_OPTIONS = {
    "spam":            "🚫 Spam",
    "promociones":     "📢 Promociones",
    "social":          "👥 Social",
    "actualizaciones": "🔔 Actualizaciones",
    "foros":           "💬 Foros",
}

_RELATION_ICONS = {
    "familiar": "👨‍👩‍👧",
    "trabajo":  "💼",
    "servicio": "🏢",
    "gobierno": "🏛️",
    "otro":     "👤",
}

_RELATION_BADGE_COLORS = {
    "familiar": ("#fef3c7", "#92400e"),
    "trabajo":  ("#dbeafe", "#1e40af"),
    "servicio": ("#d1fae5", "#065f46"),
    "gobierno": ("#ede9fe", "#5b21b6"),
    "otro":     ("#f1f5f9", "#475569"),
}

_MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]
_DAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# ── Helpers: conexión y limpieza ───────────────────────────────────────────────

def _init_service() -> bool:
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
            st.warning(f"No se pudieron mover {errores} correos. Puedes intentarlo de nuevo más tarde.")


# ── Helpers: organizar correos ─────────────────────────────────────────────────

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
        counts: Counter      = Counter()
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
    import re
    if not re.match(r"^[^@\s\"'\\]+@[^@\s\"'\\]+\.[^@\s\"'\\]+$", email):
        return {"error": f"Dirección de correo no válida: {email}"}

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

        # Use repr() so quotes, backslashes and special chars are safely escaped
        new_line = f"    {repr(email)}: {{\"label\": {repr(label)}, \"mark_important\": True}},"
        lines.insert(insert_at, new_line)

        with open(rules_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        importlib.reload(rules_mod)
        return {"success": True, "email": email, "label": label}
    except Exception as exc:
        return {"error": str(exc)}


# ── Helpers: panel avanzado ────────────────────────────────────────────────────

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
    try:
        from gmail_processor.smart_setup import SmartSetup

        _counters = {"sent": 0, "inbox": 0}

        def _cb(scanned: int, phase: str, page: int = 0):
            _counters[phase] = scanned
            if phase == "sent":
                status_ph.info(f"📤 Indexando mensajes enviados… **{scanned:,}** mensajes  |  página {page}")
            else:
                status_ph.info(f"📥 Analizando inbox… **{scanned:,}** mensajes procesados  |  página {page}")

        status_ph.info("Preparando análisis…")
        setup             = SmartSetup(st.session_state.service)
        contacts, domains = setup.analyze(scan_days=scan_days, progress_cb=_cb)
        status_ph.success(
            f"Análisis completado — "
            f"{_counters['sent']:,} enviados + {_counters['inbox']:,} recibidos procesados."
        )
        return {
            "contacts": [
                {"email": c.email, "name": c.name, "domain_type": c.domain_type,
                 "score": c.score, "count": c.count, "replied": c.replied}
                for c in contacts
            ],
            "domains": [
                {"domain": d.domain, "label": d.label, "action": d.action,
                 "total_msgs": d.total_msgs, "domain_type": d.domain_type}
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


# ── Helpers: analizador de contactos ──────────────────────────────────────────

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
                status_ph.info(f"📤 Indexando enviados… **{scanned:,}** mensajes | página {page}")
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
    stats   = analyzer.get_stats()
    pending = analyzer.get_pending()
    return {
        "stats":          stats,
        "pending_count":  len(pending),
        "pending_list":   pending,
        "last_date":      analyzer.state.get("last_processed_date"),
        "reviewed_count": len(analyzer.state.get("reviewed", {})),
    }


def _ca_reset():
    from gmail_processor.contact_analyzer import ContactAnalyzer
    ContactAnalyzer(st.session_state.service).reset()


def _ca_learning_summary() -> dict:
    from gmail_processor.contact_analyzer import ContactAnalyzer
    a = ContactAnalyzer(st.session_state.service)
    return a.get_learning_stats()


# ── Helpers: almacenamiento ────────────────────────────────────────────────────

def _cargar_storage_summary() -> dict:
    try:
        from gmail_processor.storage_analyzer import StorageAnalyzer
        return StorageAnalyzer(st.session_state.service).get_storage_summary()
    except Exception as exc:
        return {"error": str(exc)}


def _cargar_cleanup_estimate(categories: list[str] | None = None) -> dict:
    try:
        from gmail_processor.storage_analyzer import StorageAnalyzer
        return StorageAnalyzer(st.session_state.service).estimate_cleanup_size(categories)
    except Exception as exc:
        return {"error": str(exc)}


# ── Helpers: scheduler ────────────────────────────────────────────────────────

@st.cache_resource
def _get_scheduler():
    from gmail_processor.scheduler import CleanupScheduler
    return CleanupScheduler()


def _schedule_status() -> dict:
    try:
        return _get_scheduler().get_status()
    except Exception:
        return {}


def _time_ago(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        d    = datetime.strptime(date_str, "%Y-%m-%d")
        days = (datetime.now() - d).days
        if days == 0:
            return "hoy"
        elif days == 1:
            return "ayer"
        elif days < 7:
            return f"hace {days} días"
        elif days < 30:
            w = days // 7
            return f"hace {w} semana{'s' if w > 1 else ''}"
        elif days < 365:
            m = days // 30
            return f"hace {m} mes{'es' if m > 1 else ''}"
        else:
            y = days // 365
            return f"hace {y} año{'s' if y > 1 else ''}"
    except Exception:
        return date_str


# ── Helpers: perfiles y chat ───────────────────────────────────────────────────

def _check_api_key() -> bool:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _get_morning_brief() -> dict:
    try:
        from gmail_processor.morning_brief import MorningBrief
        return MorningBrief().generate()
    except Exception:
        return {}


@st.cache_resource
def _get_chat():
    from gmail_processor.assistant_chat import AssistantChat
    return AssistantChat()


def _get_important_contacts() -> list[str]:
    try:
        from gmail_processor.contact_analyzer import STATE_PATH
        if not STATE_PATH.exists():
            return []
        _state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return [
            _e for _e, _v in _state.get("reviewed", {}).items()
            if _v.get("decision") == "personal"
        ]
    except Exception:
        return []


def _load_profiles() -> dict:
    try:
        from gmail_processor.contact_profiler import ContactProfiler, PROFILES_PATH
        if not PROFILES_PATH.exists():
            return {}
        return ContactProfiler().get_profiles()
    except Exception:
        return {}


def _run_build_profiles(important_contacts: list[str], status_ph) -> dict:
    try:
        from gmail_processor.contact_profiler import ContactProfiler

        def _cb(current, total, contact_name):
            status_ph.info(f"Analizando contacto **{current}** de {total}: {contact_name}…")

        profiler = ContactProfiler()
        return profiler.build_profiles(
            service=st.session_state.service,
            important_contacts=important_contacts,
            progress_cb=_cb,
        )
    except Exception as exc:
        return {"error": str(exc)}


# ── Helpers: nuevos ────────────────────────────────────────────────────────────

def _nav_to(page: str):
    st.session_state["current_page"] = page


def _get_quick_metrics() -> dict:
    state = {}
    try:
        p = Path("analysis_state.json")
        if p.exists():
            state = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    stats   = state.get("stats", {})
    pending = len(state.get("pending", []))
    sd      = st.session_state.get("storage_data") or {}
    return {
        "personal":       stats.get("personal", 0),
        "spam_count":     stats.get("spam", 0),
        "pending":        pending,
        "used_gb":        sd.get("used_gb"),
        "total_gb":       sd.get("total_gb"),
        "messages_total": sd.get("messages_total"),
        "percent_used":   sd.get("percent_used"),
    }


def _render_contact_detail(pdata: dict):
    summary  = pdata.get("summary", "")
    timeline = pdata.get("timeline", [])
    atts     = pdata.get("attachments", [])
    alerts   = pdata.get("alerts", [])
    tone     = pdata.get("tone", "")
    lang     = pdata.get("language", "")

    if summary:
        st.markdown(summary)

    if timeline:
        st.markdown("---")
        st.markdown("**Historial por año:**")
        for tl in timeline:
            st.markdown(f"- **{tl.get('year', '')}**: {tl.get('summary', '')}")

    if atts:
        st.markdown("---")
        st.markdown("**Documentos recibidos:**")
        _ATT_ICONS = {"factura": "🧾", "pdf": "📄", "imagen": "🖼️", "hoja de cálculo": "📊", "documento word": "📝"}
        for att in atts[:10]:
            _ic = _ATT_ICONS.get((att.get("type") or "").lower(), "📎")
            st.markdown(f"- {_ic} {att.get('name', '')} — {att.get('date', '')}")

    if alerts:
        st.markdown("---")
        st.markdown("**Avisos:**")
        for al in alerts:
            st.warning(al)

    if tone or lang:
        st.caption(f"Tono: {tone}  ·  Idioma: {lang}")


# ── Dialog de detalle de contacto ─────────────────────────────────────────────

_HAS_DIALOG = False
_contact_dialog = None

try:
    @st.dialog("Detalles del contacto")
    def _contact_dialog(addr: str, pdata: dict):
        pname = pdata.get("name", addr) or addr
        rel   = pdata.get("relation_type", "otro")
        icon  = _RELATION_ICONS.get(rel, "👤")
        total = pdata.get("total_emails", 0)
        last  = pdata.get("last_contact", "")
        bidir = pdata.get("bidirectional", False)
        _bg, _fg = _RELATION_BADGE_COLORS.get(rel, ("#f1f5f9", "#475569"))
        _rel_names = {"familiar": "Familiar", "trabajo": "Trabajo",
                      "servicio": "Servicio", "gobierno": "Gobierno", "otro": "Otro"}

        c1, c2 = st.columns([1, 4])
        with c1:
            st.markdown(f"<div style='font-size:3rem;text-align:center'>{icon}</div>",
                        unsafe_allow_html=True)
        with c2:
            st.markdown(f"### {pname}")
            st.caption(addr)
            st.markdown(
                f'<span style="background:{_bg};color:{_fg};padding:3px 12px;'
                f'border-radius:999px;font-size:0.8rem;font-weight:500">'
                f'{_rel_names.get(rel, rel)}</span>',
                unsafe_allow_html=True,
            )

        st.markdown("")
        m1, m2, m3 = st.columns(3)
        m1.metric("Correos", total)
        m2.metric("Último contacto", _time_ago(last) if last else "—")
        m3.metric("Comunicación", "↔ Mutua" if bidir else "→ Solo recibo")

        st.markdown("---")
        _render_contact_detail(pdata)

    _HAS_DIALOG = True
except AttributeError:
    pass


# ── Helpers de chat ───────────────────────────────────────────────────────────

def _send_chat_message(msg_text: str, chat_msgs: list):
    """Envía un mensaje al asistente y actualiza el historial en session_state."""
    chat_msgs.append({"role": "user", "content": msg_text})
    st.session_state["chat_messages"] = chat_msgs
    with st.spinner("Pensando…"):
        try:
            _chat_obj = _get_chat()
            _chat_obj.refresh_context()
            _api_hist = [{"role": m["role"], "content": m["content"]} for m in chat_msgs[:-1]]
            _resp = _chat_obj.send_message(msg_text, _api_hist)
        except Exception as _ce:
            _resp = f"Hubo un problema: {_ce}"
    chat_msgs.append({"role": "assistant", "content": _resp})
    st.session_state["chat_messages"]      = chat_msgs
    st.session_state["chat_input_counter"] = st.session_state.get("chat_input_counter", 0) + 1
    st.rerun()


def _render_chat_panel():
    """Contenido del panel de chat (reutilizable en dialog y panel inline)."""
    if not _check_api_key():
        st.warning(
            "Para activar el asistente configura tu clave de API. "
            "Consulta **config/README.md**."
        )
        return

    _chat_msgs = st.session_state.get("chat_messages", [])

    if not _chat_msgs:
        st.caption("Puedes preguntarme, por ejemplo:")
        _sq1 = st.button("¿Quién me ha escrito hoy?",            key="sq1", use_container_width=True)
        _sq2 = st.button("¿Cuánto espacio puedo liberar?",       key="sq2", use_container_width=True)
        _sq3 = st.button("¿Tengo correos importantes sin leer?", key="sq3", use_container_width=True)
        _sq_text = None
        if _sq1:   _sq_text = "¿Quién me ha escrito hoy?"
        elif _sq2: _sq_text = "¿Cuánto espacio puedo liberar?"
        elif _sq3: _sq_text = "¿Tengo correos importantes sin leer?"
        if _sq_text:
            _send_chat_message(_sq_text, _chat_msgs)
    else:
        for _cm in (_chat_msgs[-10:] if len(_chat_msgs) > 10 else _chat_msgs):
            with st.chat_message(_cm["role"]):
                st.markdown(_cm["content"])

    _chat_key  = f"chat_input_{st.session_state.get('chat_input_counter', 0)}"
    _chat_text = st.text_input(
        "Mensaje", placeholder="Escríbeme lo que necesitas…",
        key=_chat_key, label_visibility="collapsed",
    )
    _sc1, _sc2 = st.columns([3, 1])
    with _sc1:
        _chat_send = st.button("Enviar →", key="btn_chat_send", type="primary", use_container_width=True)
    with _sc2:
        if st.button("🗑️", key="btn_chat_clear", help="Limpiar historial"):
            st.session_state["chat_messages"] = []
            st.rerun()

    if _chat_send and _chat_text.strip():
        _send_chat_message(_chat_text.strip(), _chat_msgs)


# Dialog de chat (disponible en Streamlit ≥ 1.36)
_HAS_CHAT_DIALOG = False
_chat_dialog_fn  = None

try:
    @st.dialog("💬 Asistente de correo")
    def _open_chat_dialog():
        _render_chat_panel()
    _HAS_CHAT_DIALOG = True
    _chat_dialog_fn  = _open_chat_dialog
except AttributeError:
    try:
        @st.experimental_dialog("💬 Asistente de correo")
        def _open_chat_dialog():
            _render_chat_panel()
        _HAS_CHAT_DIALOG = True
        _chat_dialog_fn  = _open_chat_dialog
    except AttributeError:
        pass


# ── Auto-conexión y scheduler ──────────────────────────────────────────────────

if st.session_state.service is None and os.path.exists("token.json"):
    _init_service()

if os.path.exists("cleanup_schedule.json"):
    try:
        _sch_auto = _get_scheduler()
        if _sch_auto.config.get("enabled") and _sch_auto._job is None:
            _sch_auto.start()
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════════════════
# CSS GLOBAL
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
/* ── Fuente ── */
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ── Ocultar chrome de Streamlit ── */
#MainMenu  {visibility: hidden;}
footer     {visibility: hidden;}
header[data-testid="stHeader"] {display: none;}

/* ── Layout: sin max-width para que ocupe el espacio disponible ── */
.main .block-container {
    padding-top: 2rem;
    padding-bottom: 4rem;
    padding-left: 2.5rem;
    padding-right: 2.5rem;
}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    border-right: 2px solid #2d3250;
}
section[data-testid="stSidebar"] > div {
    padding-top: 1.5rem;
}

/* Ocultar botón de colapsar sidebar - múltiples selectores para cubrir todas las versiones de Streamlit */
[data-testid="collapsedControl"] { display: none !important; }
.st-emotion-cache-1egp75f { display: none !important; }
.st-emotion-cache-czk5ss { display: none !important; }
button[aria-label="Close sidebar"] { display: none !important; }
button[aria-label="Collapse sidebar"] { display: none !important; }
section[data-testid="stSidebarCollapsedControl"] { display: none !important; }

/* Forzar sidebar siempre expandido */
[data-testid="stSidebar"] {
    display: block !important;
    visibility: visible !important;
    transform: none !important;
    min-width: 280px !important;
}

/* ── Botones: radio redondeado y colores ── */
button[data-testid="baseButton-primary"] {
    border-radius: 8px !important;
    background-color: #4f6ef7 !important;
    border: none !important;
    font-weight: 500 !important;
    color: #ffffff !important;
    transition: background 0.15s ease !important;
}
button[data-testid="baseButton-primary"]:hover {
    background-color: #6b85f9 !important;
}
button[data-testid="baseButton-secondary"] {
    border-radius: 8px !important;
    border: 1px solid #2d3250 !important;
    transition: background 0.15s ease !important;
}

/* Botón activo del sidebar — azul translúcido */
section[data-testid="stSidebar"] button[data-testid="baseButton-primary"] {
    background-color: #262940 !important;
    color: #4f6ef7 !important;
    border: 1px solid #4f6ef7 !important;
    font-weight: 600 !important;
}

/* ── Tarjetas con borde (st.container border=True) ── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #1a1d2e !important;
    border: 1px solid #2d3250 !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4) !important;
}

/* ── Expanders ── */
div[data-testid="stExpander"] {
    background-color: #1a1d2e !important;
    border: 1px solid #2d3250 !important;
    border-radius: 14px !important;
}
div[data-testid="stExpander"] summary {
    color: #e2e8f0 !important;
}

/* ── Métricas ── */
div[data-testid="metric-container"] {
    background-color: #1a1d2e !important;
    border: 1px solid #2d3250 !important;
    border-radius: 14px !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.35) !important;
    padding: 1.1rem 1.4rem !important;
}
div[data-testid="stMetricValue"] {
    font-size: 2rem !important;
    font-weight: 700 !important;
    color: #e2e8f0 !important;
}
div[data-testid="stMetricLabel"] {
    color: #8892a4 !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}

/* ── Barras de progreso ── */
div[data-testid="stProgress"] > div > div {
    background-color: #4f6ef7 !important;
    border-radius: 999px !important;
}
div[data-testid="stProgress"] > div {
    border-radius: 999px !important;
    background-color: #262940 !important;
}

/* ── Tags inline (HTML personalizado) ── */
span.tag {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 500;
    background: #262940;
    color: #8892a4;
    margin: 2px;
    border: 1px solid #2d3250;
}
span.tag-blue  { background: #1e2d5e; color: #7da5f7; border-color: #4f6ef7; }
span.tag-green { background: #0f2e1a; color: #4ade80; border-color: #22c55e; }
span.tag-amber { background: #2e1f08; color: #fbbf24; border-color: #f59e0b; }
span.tag-red   { background: #2e0f0f; color: #f87171; border-color: #ef4444; }

/* ── Tarjeta de buenos días ── */
.brief-card {
    background: linear-gradient(135deg, #1a1d2e 0%, #262940 100%);
    border: 1px solid #4f6ef7;
    border-radius: 16px;
    padding: 1.5rem 2rem;
    margin-bottom: 1rem;
}

/* ── Tabs ── */
div[data-testid="stTabs"] button[role="tab"] {
    border-radius: 8px 8px 0 0 !important;
}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #4f6ef7 !important;
    border-bottom-color: #4f6ef7 !important;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

connected     = st.session_state.service is not None
_current_page = st.session_state.get("current_page", "inicio")

_NAV_ITEMS = [
    ("Inicio",              "📊", "inicio"),
    ("Mis contactos",       "👤", "contactos"),
    ("Analizar correos",    "🔬", "analizar"),
    ("Limpiar correos",     "🧹", "limpiar"),
    ("Limpieza automática", "⏰", "automatica"),
    ("Opciones avanzadas",  "⚙️", "avanzadas"),
]

with st.sidebar:
    st.markdown(
        "<div style='font-size:1.3rem;font-weight:700;color:#e2e8f0;padding:0.25rem 0 0.75rem 0'>"
        "📧 Mi Correo</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<hr style='margin:0 0 0.75rem 0;border:none;border-top:1px solid #2d3250'>",
        unsafe_allow_html=True,
    )

    for _n, _i, _k in _NAV_ITEMS:
        _is_active = (_current_page == _k)
        if st.button(
            f"{_i}  {_n}",
            key=f"nav_{_k}",
            use_container_width=True,
            type="primary" if _is_active else "secondary",
        ):
            _nav_to(_k)
            st.rerun()

    st.markdown(
        "<hr style='margin:0.75rem 0;border:none;border-top:1px solid #2d3250'>",
        unsafe_allow_html=True,
    )

    # Botón del asistente de chat
    if st.button("💬  Asistente", key="sidebar_chat_btn", use_container_width=True):
        if _HAS_CHAT_DIALOG and _chat_dialog_fn is not None:
            _chat_dialog_fn()
        else:
            st.session_state["chat_open"] = not st.session_state.get("chat_open", False)
            st.rerun()

    st.markdown(
        "<hr style='margin:0.75rem 0;border:none;border-top:1px solid #2d3250'>",
        unsafe_allow_html=True,
    )

    # Estado de conexión
    if connected:
        st.markdown(
            "<span style='color:#22c55e;font-size:0.9rem'>● Conectado a Gmail</span>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span style='color:#ef4444;font-size:0.9rem'>● Sin conexión</span>",
            unsafe_allow_html=True,
        )
        if st.button("Conectar Gmail", key="sidebar_connect", use_container_width=True, type="primary"):
            with st.spinner("Conectando…"):
                _ok = _init_service()
            if _ok:
                st.rerun()

    # Mini barra de almacenamiento
    _sd_side = st.session_state.get("storage_data") or {}
    if _sd_side and not _sd_side.get("error") and _sd_side.get("percent_used") is not None:
        _pct = (_sd_side["percent_used"] or 0) / 100
        st.progress(_pct, text=f"{_sd_side.get('used_gb', 0)} GB usados")
    elif connected:
        st.caption("💾 Almacenamiento: —")

    st.markdown("")
    st.caption("v2.0")

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA: INICIO
# ══════════════════════════════════════════════════════════════════════════════

if _current_page == "inicio":
    _now  = datetime.now()
    _hour = _now.hour
    _greet_word = "Buenos días" if _hour < 12 else "Buenas tardes" if _hour < 19 else "Buenas noches"
    _today_str = f"{_DAYS_ES[_now.weekday()]}, {_now.day} de {_MONTHS_ES[_now.month - 1]} de {_now.year}"

    st.markdown(f"## {_greet_word} 👋")
    st.caption(_today_str.capitalize())

    if not connected:
        st.markdown("")
        with st.container(border=True):
            st.markdown("### Bienvenido a Mi Correo")
            st.markdown(
                "Esta aplicación te ayuda a organizar y limpiar tu correo de Gmail "
                "de manera sencilla. Conecta tu cuenta para comenzar."
            )
            st.markdown("")
            if st.button("🔑 Conectar mi cuenta de Gmail", type="primary", use_container_width=True, key="inicio_connect"):
                with st.spinner("Abriendo ventana de autorización de Gmail…"):
                    _ok = _init_service()
                if _ok:
                    st.rerun()
    else:
        # ── Tarjeta de buenos días ──────────────────────────────────────────
        _brief = _get_morning_brief()
        if _brief:
            _bsummary = _brief.get("summary_text", "Todo está en orden.")
            st.markdown(
                f'<div class="brief-card">'
                f'<p style="margin:0;font-size:1.05rem;color:#1e40af;font-weight:500">'
                f'{_bsummary}</p></div>',
                unsafe_allow_html=True,
            )

            _bnif    = _brief.get("new_from_important", [])
            _bpend   = _brief.get("pending_decisions",  0)
            _balerts = _brief.get("alerts",             [])

            if _bnif or _bpend > 0 or _balerts:
                with st.container(border=True):
                    if _bnif:
                        st.markdown("**Novedades de tus contactos importantes:**")
                        for _bm in _bnif[:5]:
                            st.markdown(
                                f"&nbsp;&nbsp;📧 **{_bm.get('name', '')}** "
                                f"· {_time_ago(_bm.get('date', ''))}",
                                unsafe_allow_html=True,
                            )
                        st.markdown("")
                    if _bpend > 0:
                        _pend_label = f"{'s' if _bpend > 1 else ''}"
                        if st.button(
                            f"📋 Ver {_bpend} contacto{_pend_label} pendiente{_pend_label} de clasificar",
                            key="inicio_btn_analizar",
                            type="primary",
                        ):
                            _nav_to("analizar")
                            st.rerun()
                    for _ba in _balerts[:3]:
                        st.warning(_ba)
            else:
                st.success("✅ Todo en orden · No hay novedades hoy")

        # ── Métricas rápidas ─────────────────────────────────────────────────
        st.markdown("### Resumen")
        _qm = _get_quick_metrics()
        _mc1, _mc2, _mc3, _mc4 = st.columns(4)

        with _mc1:
            _msgs = _qm.get("messages_total")
            st.metric("📨 Correos totales", f"{_msgs:,}" if _msgs else "—")
        with _mc2:
            st.metric("👤 Contactos importantes", _qm.get("personal", 0))
        with _mc3:
            st.metric("⏳ Pendientes de clasificar", _qm.get("pending", 0))
        with _mc4:
            _ug  = _qm.get("used_gb")
            _tg  = _qm.get("total_gb")
            _stor_val = f"{_ug} GB" if _ug is not None else "—"
            _stor_delta = f"de {_tg:.0f} GB" if _tg else None
            st.metric("💾 Espacio usado", _stor_val, delta=_stor_delta, delta_color="off")

        if _qm.get("used_gb") is None:
            if st.button("📊 Ver almacenamiento", key="inicio_storage", use_container_width=False):
                with st.spinner("Consultando…"):
                    st.session_state["storage_data"] = _cargar_storage_summary()
                st.rerun()

        # ── Acciones rápidas ──────────────────────────────────────────────────
        st.markdown("### Acciones rápidas")
        _qa1, _qa2 = st.columns(2)
        with _qa1:
            if st.button("🧹 Limpiar correos acumulados", use_container_width=True, key="qa_limpiar"):
                _nav_to("limpiar")
                st.rerun()
            if st.button("🔬 Analizar mi correo", use_container_width=True, key="qa_analizar"):
                _nav_to("analizar")
                st.rerun()
        with _qa2:
            if st.button("👤 Ver mis contactos", use_container_width=True, key="qa_contactos"):
                _nav_to("contactos")
                st.rerun()
            if st.button("💬 Preguntarle al asistente", use_container_width=True, key="qa_chat"):
                st.session_state["chat_open"] = True
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA: MIS CONTACTOS
# ══════════════════════════════════════════════════════════════════════════════

elif _current_page == "contactos":
    _cph1, _cph2 = st.columns([5, 1])
    with _cph1:
        st.markdown("## 👤 Mis contactos importantes")
        st.caption("Personas y organizaciones que te escriben con frecuencia")
    with _cph2:
        if connected and st.button("🔄 Actualizar", key="btn_contacts_rebuild", use_container_width=True):
            _imp = _get_important_contacts()
            if _imp:
                _bp_status = st.empty()
                _bp_r = _run_build_profiles(_imp, _bp_status)
                st.session_state["profiler_result"] = _bp_r
                st.rerun()
            else:
                st.warning("Primero analiza tus correos para identificar contactos.")

    if not _check_api_key():
        st.info(
            "Para activar el asistente inteligente necesitas configurar tu clave de API. "
            "Consulta el archivo **config/README.md** para instrucciones."
        )
    else:
        _profiles         = _load_profiles()
        _important_emails = _get_important_contacts()

        # Resultado de construir perfiles (si viene de esta página)
        _prof_r = st.session_state.get("profiler_result")
        if _prof_r:
            if _prof_r.get("error") == "no_api_key":
                st.warning("No se encontró la clave de API. Verifica tu archivo .env.")
            elif _prof_r.get("error"):
                st.error(f"Error al construir perfiles: {_prof_r['error']}")
            elif "built" in _prof_r:
                st.success(
                    f"✓ {_prof_r['built']} de {_prof_r['total']} perfiles construidos."
                )
                _profiles = _load_profiles()

        if not _important_emails and not _profiles:
            with st.container(border=True):
                st.markdown("### Aún no hay contactos analizados")
                st.markdown(
                    "Primero analiza tus correos para identificar quién te escribe con frecuencia."
                )
                if st.button("🔬 Ir a Analizar correos", type="primary", key="contacts_go_analyze"):
                    _nav_to("analizar")
                    st.rerun()
        elif not _profiles and _important_emails:
            with st.container(border=True):
                st.markdown(
                    f"Hay **{len(_important_emails)}** contactos importantes identificados. "
                    "Construye sus perfiles para ver información detallada."
                )
                if connected and st.button("✨ Construir perfiles con IA", type="primary", key="contacts_build"):
                    _bp_status = st.empty()
                    _bp_r      = _run_build_profiles(_important_emails, _bp_status)
                    st.session_state["profiler_result"] = _bp_r
                    st.rerun()
        else:
            # Barra de búsqueda y filtros
            _sf1, _sf2 = st.columns([3, 2])
            with _sf1:
                _search = st.text_input(
                    "🔍 Buscar",
                    placeholder="Nombre o email…",
                    key="contacts_search",
                    label_visibility="collapsed",
                )
            with _sf2:
                _filter_map = {
                    "Todos": None, "Familiar": "familiar", "Trabajo": "trabajo",
                    "Servicio": "servicio", "Gobierno": "gobierno",
                }
                _filter_label = st.radio(
                    "Tipo",
                    options=list(_filter_map.keys()),
                    horizontal=True,
                    key="contacts_filter",
                    label_visibility="collapsed",
                )
                _filter_type = _filter_map[_filter_label]

            # Filtrar perfiles
            _filtered = {
                addr: pd for addr, pd in _profiles.items()
                if (not _search or
                    _search.lower() in (pd.get("name") or "").lower() or
                    _search.lower() in addr.lower())
                and (_filter_type is None or pd.get("relation_type") == _filter_type)
            }

            if not _filtered:
                st.info("No hay contactos que coincidan con el filtro.")
            else:
                st.caption(f"Mostrando {len(_filtered)} de {len(_profiles)} contactos")
                st.markdown("")

                _items = list(_filtered.items())
                for _ci in range(0, len(_items), 3):
                    _gcols = st.columns(3)
                    for _cj, _gcol in enumerate(_gcols):
                        if _ci + _cj >= len(_items):
                            break
                        _caddr, _cpdata = _items[_ci + _cj]
                        _cpname  = _cpdata.get("name", _caddr) or _caddr
                        _cprel   = _cpdata.get("relation_type", "otro")
                        _cpicon  = _RELATION_ICONS.get(_cprel, "👤")
                        _cptotal = _cpdata.get("total_emails", 0)
                        _cplast  = _cpdata.get("last_contact", "")
                        _cpbidir = _cpdata.get("bidirectional", False)
                        _cptopics = _cpdata.get("key_topics", [])
                        _cpbg, _cpfg = _RELATION_BADGE_COLORS.get(_cprel, ("#f1f5f9", "#475569"))
                        _rel_names = {"familiar": "Familiar", "trabajo": "Trabajo",
                                      "servicio": "Servicio", "gobierno": "Gobierno", "otro": "Otro"}

                        with _gcol:
                            with st.container(border=True):
                                st.markdown(
                                    f"<div style='font-size:2.2rem;margin-bottom:4px'>{_cpicon}</div>",
                                    unsafe_allow_html=True,
                                )
                                st.markdown(f"**{_cpname}**")
                                st.caption(_caddr)
                                st.markdown(
                                    f'<span style="background:{_cpbg};color:{_cpfg};padding:2px 10px;'
                                    f'border-radius:999px;font-size:0.78rem;font-weight:500">'
                                    f'{_rel_names.get(_cprel, _cprel)}</span>',
                                    unsafe_allow_html=True,
                                )
                                st.markdown("")
                                _last_txt = _time_ago(_cplast) if _cplast else "—"
                                st.caption(f"📧 {_cptotal} correos · Último: {_last_txt}")
                                if _cpbidir:
                                    st.markdown(
                                        '<span class="tag tag-blue">↔ Conversación mutua</span>',
                                        unsafe_allow_html=True,
                                    )
                                if _cptopics:
                                    _tags_html = " ".join(
                                        f'<span class="tag">{t}</span>' for t in _cptopics[:3]
                                    )
                                    st.markdown(_tags_html, unsafe_allow_html=True)
                                st.markdown("")

                                if _HAS_DIALOG and _contact_dialog is not None:
                                    if st.button("Ver detalles →", key=f"detail_{_caddr}", use_container_width=True):
                                        _contact_dialog(_caddr, _cpdata)
                                else:
                                    with st.expander("Ver detalles →"):
                                        _render_contact_detail(_cpdata)

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA: ANALIZAR CORREOS
# ══════════════════════════════════════════════════════════════════════════════

elif _current_page == "analizar":
    st.markdown("## 🔬 Analizar correos")
    st.caption("Revisa quién te escribe y decide qué hacer con cada remitente")

    if not connected:
        st.warning("Conecta tu cuenta de Gmail para analizar correos.")
        if st.button("🔑 Conectar Gmail", type="primary", key="analizar_connect"):
            _nav_to("inicio")
            st.rerun()
    else:
        # Cargar estado previo
        try:
            _ca_prev = _ca_state_summary()
        except Exception:
            _ca_prev = None

        # ── Tarjeta de estado ─────────────────────────────────────────────────
        with st.container(border=True):
            if _ca_prev:
                _cp_stats = _ca_prev["stats"]
                _cp_date  = (_ca_prev["last_date"] or "")[:19].replace("T", " ")
                st.markdown(f"**Último análisis:** {_cp_date or 'desconocido'}")
                _sm1, _sm2, _sm3, _sm4 = st.columns(4)
                _sm1.metric("Analizados", _ca_prev["reviewed_count"])
                _sm2.metric("👤 Personales", _cp_stats.get("personal", 0))
                _sm3.metric("🚫 Spam", _cp_stats.get("spam", 0))
                _sm4.metric("⏳ Pendientes", _ca_prev["pending_count"])

                # Aprendizaje
                try:
                    _learn = _ca_learning_summary()
                    _l_dec = _learn.get("decisions_count", 0)
                    _l_dom = _learn.get("auto_domains", 0)
                    if _l_dec > 0:
                        st.caption(
                            f"🧠 El sistema aprendió de **{_l_dec}** decisiones tuyas · "
                            f"**{_l_dom}** dominios con clasificación automática"
                        )
                except Exception:
                    pass
            else:
                st.markdown("No hay análisis previo. Ejecuta tu primer análisis con la configuración de abajo.")

        # ── Pendientes — sección más prominente ───────────────────────────────
        _ca_batch   = st.session_state.get("ca_batch_result")
        _pend_list  = []

        if _ca_batch and "pending_list" in _ca_batch:
            _pend_list = _ca_batch["pending_list"]
        elif _ca_prev:
            _pend_list = _ca_prev["pending_list"]

        if _pend_list:
            _n_pend = len(_pend_list)
            st.markdown("")
            st.markdown(
                f"### ⚠️ Tienes {_n_pend} "
                f"contacto{'s' if _n_pend > 1 else ''} esperando tu decisión"
            )
            st.caption("Decide qué hacer con cada remitente. Los que omitas quedarán para después.")

            from gmail_processor.contact_analyzer import SIGNAL_LABELS as _SL

            _decisions = st.session_state["ca_decisions"]

            for _pi, _ps in enumerate(_pend_list):
                _pa     = _ps["email"]
                _pn     = _ps.get("name", "")
                _psc    = _ps.get("score", 0)
                _psi    = _ps.get("signals", [])
                _psubj  = _ps.get("sample_subjects", [])
                _pfirst = _ps.get("first_seen", "")
                _plast  = _ps.get("last_seen",  "")
                _pcount = _ps.get("count", 0)
                _lbl    = f"{_pn} <{_pa}>" if _pn else _pa
                _dec    = _decisions.get(_pa)

                with st.container(border=True):
                    _pc1, _pc2 = st.columns([7, 1])
                    with _pc1:
                        st.markdown(f"**{_lbl}**")
                        _ctx = []
                        if _pcount:
                            _ctx.append(f"📧 {_pcount} correos en este período")
                        if _plast:
                            _ctx.append(f"📅 Último contacto: {_time_ago(_plast)}")
                        if _pfirst and _pfirst != _plast:
                            _ctx.append(f"Primera vez: {_time_ago(_pfirst)}")
                        if _ctx:
                            st.caption("  ·  ".join(_ctx))
                    with _pc2:
                        _sc_icon = "🟢" if _psc >= 60 else "🟡" if _psc >= 40 else "🔴"
                        st.markdown(f"<div style='text-align:center;font-size:1.5rem'>{_sc_icon}</div>",
                                    unsafe_allow_html=True)
                        st.caption(f"{_psc}/100")

                    if _psubj:
                        st.caption("Asuntos: " + "  ·  ".join(f'"{s[:50]}"' for s in _psubj[:2]))

                    if _psi:
                        _sig_parts = []
                        for _s in _psi:
                            _slabel, _spos = _SL.get(_s, (_s, True))
                            _cls = "tag-green" if _spos else "tag-amber"
                            _ico = "✓" if _spos else "✗"
                            _sig_parts.append(f'<span class="tag {_cls}">{_ico} {_slabel}</span>')
                        st.markdown(" ".join(_sig_parts), unsafe_allow_html=True)

                    st.markdown("")
                    _pb1, _pb2, _pb3 = st.columns(3)
                    with _pb1:
                        if st.button(
                            f"🛡️ Es importante{'  ✓' if _dec == 'personal' else ''}",
                            key=f"ca_personal_{_pi}",
                            type="primary" if _dec == "personal" else "secondary",
                            use_container_width=True,
                        ):
                            _decisions[_pa] = "personal"
                            st.session_state["ca_decisions"] = _decisions
                            st.rerun()
                    with _pb2:
                        if st.button(
                            f"🗑️ Es spam{'  ✓' if _dec == 'spam' else ''}",
                            key=f"ca_spam_{_pi}",
                            type="primary" if _dec == "spam" else "secondary",
                            use_container_width=True,
                        ):
                            _decisions[_pa] = "spam"
                            st.session_state["ca_decisions"] = _decisions
                            st.rerun()
                    with _pb3:
                        if st.button(
                            f"⏭️ No sé ahora{'  ✓' if _dec == 'skip' else ''}",
                            key=f"ca_skip_{_pi}",
                            use_container_width=True,
                        ):
                            _decisions[_pa] = "skip"
                            st.session_state["ca_decisions"] = _decisions
                            st.rerun()

            # Aplicar decisiones
            _decided = len(_decisions)
            if _decided > 0:
                st.markdown("")
                st.info(
                    f"**{_decided} de {len(_pend_list)}** remitentes con decisión. "
                    f"({len(_pend_list) - _decided} sin decidir — quedarán pendientes)"
                )
                if st.button(
                    f"✅ Aplicar {_decided} decisiones",
                    key="btn_ca_apply",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner("Aplicando decisiones…"):
                        _apply_r = _ca_apply(_decisions)
                    st.session_state["ca_apply_result"] = _apply_r
                    st.session_state["ca_decisions"]    = {}
                    try:
                        _new_prev = _ca_state_summary()
                        if _new_prev and _ca_batch:
                            st.session_state["ca_batch_result"]["pending_list"] = _new_prev["pending_list"]
                            st.session_state["ca_batch_result"]["stats"]        = _new_prev["stats"]
                    except Exception:
                        pass
                    st.rerun()

        # Resultado de aplicar
        _ca_apply_r = st.session_state["ca_apply_result"]
        if _ca_apply_r:
            if "error" in _ca_apply_r:
                st.error(f"Error al aplicar: {_ca_apply_r['error']}")
            else:
                _apr_p  = _ca_apply_r.get("protected",      0)
                _apr_ts = _ca_apply_r.get("trashed_senders", 0)
                _apr_tm = _ca_apply_r.get("trashed_msgs",    0)
                _apr_e  = _ca_apply_r.get("errors",          [])
                st.success(
                    f"✓ **{_apr_p}** contactos protegidos · "
                    f"**{_apr_ts}** remitentes de spam eliminados ({_apr_tm} correos a la papelera)"
                )
                if _apr_e:
                    with st.expander(f"⚠️ {len(_apr_e)} errores"):
                        for _e in _apr_e:
                            st.caption(_e)

        # ── Configuración del análisis ────────────────────────────────────────
        st.markdown("")
        with st.expander("⚙️ Configurar nuevo análisis"):
            _ca_c1, _ca_c2 = st.columns([3, 1])
            with _ca_c1:
                _ca_range_label = st.selectbox(
                    "Rango de tiempo",
                    options=list(_ANALYZE_RANGES.keys()),
                    index=1,
                    key="ca_range",
                )
            with _ca_c2:
                _ca_batch_size = st.number_input(
                    "Correos por lote",
                    min_value=50, max_value=500, value=200, step=50,
                    key="ca_batch_size",
                )
            _ca_days = _ANALYZE_RANGES[_ca_range_label]

            if _ca_prev:
                _btn1, _btn2, _btn3 = st.columns(3)
                with _btn1:
                    _ca_btn_continue = st.button(
                        "▶ Continuar análisis", key="btn_ca_continue", use_container_width=True, type="primary"
                    )
                with _btn2:
                    _ca_btn_new = st.button(
                        "🔄 Nuevo análisis", key="btn_ca_new", use_container_width=True
                    )
                with _btn3:
                    _ca_btn_review = st.button(
                        f"📋 Solo revisar pendientes ({_ca_prev['pending_count']})",
                        key="btn_ca_review",
                        disabled=_ca_prev["pending_count"] == 0,
                        use_container_width=True,
                    )

                if _ca_btn_new:
                    _ca_reset()
                    st.session_state["ca_batch_result"] = None
                    st.session_state["ca_apply_result"] = None
                    st.session_state["ca_decisions"]    = {}
                    st.rerun()
                if _ca_btn_review:
                    st.session_state["ca_batch_result"] = {
                        "auto_personal": 0, "auto_spam": 0,
                        "pending":       _ca_prev["pending_count"],
                        "already_reviewed": _ca_prev["reviewed_count"],
                        "scanned":       0,
                        "pending_list":  _ca_prev["pending_list"],
                        "stats":         _ca_prev["stats"],
                        "review_only":   True,
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
                    "🔍 Iniciar análisis",
                    key="btn_ca_start",
                    type="primary",
                    use_container_width=True,
                ):
                    _ca_status = st.empty()
                    _ca_r = _ca_run_batch(_ca_days, int(_ca_batch_size), _ca_status)
                    st.session_state["ca_batch_result"] = _ca_r
                    st.session_state["ca_decisions"]    = {}
                    st.rerun()

        # Resultado del lote
        if _ca_batch and not _ca_batch.get("review_only"):
            if "error" in _ca_batch:
                st.error(f"Error en el análisis: {_ca_batch['error']}")
            elif _ca_batch.get("scanned", 0) > 0:
                _cb_sc = _ca_batch.get("scanned", 0)
                _cb_ap = _ca_batch.get("auto_personal", 0)
                _cb_as = _ca_batch.get("auto_spam", 0)
                _cb_pd = _ca_batch.get("pending", 0)
                st.success(
                    f"**Lote completado**: {_cb_sc:,} correos escaneados — "
                    f"{_cb_ap + _cb_as} clasificados automáticamente · "
                    f"**{_cb_pd} para revisar**"
                )

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA: LIMPIAR CORREOS
# ══════════════════════════════════════════════════════════════════════════════

elif _current_page == "limpiar":
    st.markdown("## 🧹 Limpiar correos")
    st.markdown(
        "Mueve correos innecesarios a la papelera para liberar espacio. "
        "Los correos van a la **Papelera de Gmail** y permanecen allí **30 días** "
        "— puedes recuperar cualquiera si te equivocas."
    )

    if not connected:
        st.warning("Conecta tu cuenta de Gmail para limpiar correos.")
        if st.button("🔑 Conectar Gmail", type="primary", key="limpiar_connect"):
            _nav_to("inicio")
            st.rerun()
    else:
        # ── Resumen de almacenamiento ─────────────────────────────────────────
        _sd = st.session_state.get("storage_data")
        _lc1, _lc2 = st.columns([5, 2])
        with _lc1:
            if _sd and not _sd.get("error"):
                _s_used  = _sd.get("used_gb")
                _s_total = _sd.get("total_gb")
                _s_pct   = _sd.get("percent_used")
                _s_msgs  = _sd.get("messages_total", 0)
                if _s_used is not None and _s_total:
                    st.progress(
                        (_s_pct or 0) / 100,
                        text=f"Usando **{_s_used} GB** de {_s_total:.0f} GB ({_s_pct}%) · {_s_msgs:,} mensajes",
                    )
                else:
                    st.caption(f"**{_s_msgs:,}** mensajes en tu cuenta.")
            else:
                st.caption("Consulta cuánto espacio usas en Gmail.")
        with _lc2:
            if st.button("📊 Ver almacenamiento", key="limpiar_storage", use_container_width=True):
                with st.spinner("Consultando…"):
                    st.session_state["storage_data"] = _cargar_storage_summary()
                st.rerun()

        # Estimación de espacio liberado
        if _sd and not _sd.get("error"):
            _ce = st.session_state.get("cleanup_size_data")
            if not _ce:
                if st.button("📊 ¿Cuánto espacio puedo liberar?", key="btn_estimate"):
                    with st.spinner("Estimando (puede tardar ~1 min)…"):
                        st.session_state["cleanup_size_data"] = _cargar_cleanup_estimate()
                    st.rerun()
            if _ce and not _ce.get("error") and "total_mb" in _ce:
                st.info(f"Podrías liberar hasta **{_ce.get('total_gb', 0):.2f} GB** limpiando las categorías.")

        st.markdown("")
        st.markdown("### Limpiar por categoría")

        # ── Grid 2 columnas ───────────────────────────────────────────────────
        for _ci in range(0, len(CATS), 2):
            _crow = st.columns(2)
            for _cj, _ccol in enumerate(_crow):
                if _ci + _cj >= len(CATS):
                    break
                cat = CATS[_ci + _cj]
                k   = cat["key"]
                confirm_key = f"confirm_{k}"
                result_key  = f"result_{k}"

                with _ccol:
                    with st.container(border=True):
                        st.markdown(f"### {cat['icon']} {cat['nombre']}")
                        st.caption(cat["desc"])
                        st.markdown("")

                        # Estimado si disponible
                        _ce_all = st.session_state.get("cleanup_size_data") or {}
                        _cat_ce = _ce_all.get(k)
                        if _cat_ce:
                            st.caption(
                                f"📊 Estimado: **{_cat_ce.get('size_mb', 0):,} MB** · "
                                f"{_cat_ce.get('count', 0):,} correos"
                            )

                        if not st.session_state[confirm_key]:
                            st.button(
                                f"🗑️ Limpiar {cat['nombre']}",
                                key=f"btn_{k}",
                                use_container_width=True,
                                on_click=lambda key=k: st.session_state.update({f"confirm_{key}": True}),
                            )
                        else:
                            st.warning(f"👉 {cat['aviso']}")
                            _cc1, _cc2 = st.columns(2)
                            with _cc1:
                                if st.button(
                                    f"✓ Sí, limpiar",
                                    key=f"exec_{k}",
                                    type="primary",
                                    use_container_width=True,
                                ):
                                    with st.spinner(f"Limpiando {cat['nombre']}…"):
                                        _r = _ejecutar_limpieza([k])
                                    st.session_state[result_key]  = _r
                                    st.session_state[confirm_key] = False
                                    st.rerun()
                            with _cc2:
                                if st.button("✗ Cancelar", key=f"cancel_{k}", use_container_width=True):
                                    st.session_state[confirm_key] = False
                                    st.rerun()

                        _mostrar_resultado_cat(st.session_state[result_key], cat["nombre"])

        # ── Limpiar todo ──────────────────────────────────────────────────────
        st.markdown("")
        with st.expander("🧹 Limpiar todas las categorías de una vez"):
            st.markdown(
                "Limpia **Spam, Promociones, Social, Actualizaciones y Foros** en una sola operación. "
                "Puede tardar varios minutos."
            )
            st.caption(
                "⚠️ Se moverán a la papelera todos los correos de todas las categorías al mismo tiempo. "
                "Tienes 30 días para recuperar cualquier correo desde la Papelera de Gmail."
            )
            if not st.session_state["confirm_todo"]:
                st.button(
                    "🧹 Limpiar todo",
                    key="btn_todo",
                    disabled=not connected,
                    use_container_width=True,
                    on_click=lambda: st.session_state.update({"confirm_todo": True}),
                )
            else:
                st.warning("¿Confirmas limpiar **todas las categorías** a la vez?")
                _tc1, _tc2 = st.columns(2)
                with _tc1:
                    if st.button("✓ Sí, limpiar todo", key="exec_todo", type="primary", use_container_width=True):
                        _ORDEN = ["spam", "promociones", "social", "actualizaciones", "foros"]
                        _prog  = st.progress(0, text="Iniciando…")
                        _resultados = {}
                        for _ti, _tk in enumerate(_ORDEN):
                            _prog.progress(_ti / len(_ORDEN), text=f"Limpiando {_TODO_NOMBRE[_tk]}…")
                            _tr = _ejecutar_limpieza([_tk])
                            if _tr:
                                _resultados[_tk] = _tr
                        _prog.progress(1.0, text="¡Completado!")
                        st.session_state["result_todo"]  = _resultados
                        st.session_state["confirm_todo"] = False
                        st.rerun()
                with _tc2:
                    if st.button("✗ Cancelar", key="cancel_todo", use_container_width=True):
                        st.session_state["confirm_todo"] = False
                        st.rerun()

            if st.session_state["result_todo"] is not None:
                _rtodo = st.session_state["result_todo"]
                _rt_enc = sum(r.get("procesados", 0) for r in _rtodo.values())
                _rt_mov = sum(r.get("exitos",     0) for r in _rtodo.values())
                if _rt_enc == 0:
                    st.info("No se encontraron correos. Tu bandeja ya estaba limpia.")
                else:
                    st.success(f"✓ **{_rt_mov} de {_rt_enc}** correos movidos a la papelera.")

        # ── Remitentes frecuentes ──────────────────────────────────────────────
        st.markdown("")
        with st.expander("📊 Limpiar por remitente"):
            st.caption(
                "Muestra los 15 remitentes con más correos en tu bandeja (últimos 150 mensajes). "
                "Puedes limpiar o proteger a cada remitente individualmente."
            )
            if st.button("🔍 Cargar remitentes", key="btn_load_senders_limpiar"):
                with st.spinner("Analizando…"):
                    st.session_state["senders_data"] = _cargar_remitentes_frecuentes()
                st.rerun()

            _senders = st.session_state["senders_data"]
            if _senders is None:
                st.info("Haz clic en 'Cargar remitentes' para ver quién te escribe más.")
            elif not _senders:
                st.info("No se encontraron remitentes en la bandeja de entrada.")
            else:
                for _si, _sndr in enumerate(_senders):
                    _se_email   = _sndr["email"]
                    _se_name    = _sndr.get("name", "")
                    _se_count   = _sndr["count"]
                    _se_label   = f"{_se_name} <{_se_email}>" if _se_name else _se_email
                    _csk  = f"confirm_trash_sender_{_si}"
                    _rsk  = f"result_trash_sender_{_si}"
                    _cpsk = f"confirm_protect_sender_{_si}"
                    _rpsk = f"result_protect_sender_{_si}"
                    st.session_state.setdefault(_csk,  False)
                    st.session_state.setdefault(_rsk,  None)
                    st.session_state.setdefault(_cpsk, False)
                    st.session_state.setdefault(_rpsk, None)

                    _s_c1, _s_c2, _s_c3, _s_c4 = st.columns([6, 1, 2, 2])
                    with _s_c1:
                        st.markdown(f"**{_se_label}**")
                    with _s_c2:
                        st.caption(f"{_se_count}")
                    with _s_c3:
                        if not st.session_state[_csk]:
                            st.button(
                                "🗑️ Limpiar", key=f"btn_ts_{_si}", use_container_width=True,
                                on_click=lambda k=_csk: st.session_state.update({k: True}),
                            )
                        else:
                            st.warning(f"¿Mover todos los correos de {_se_email}?")
                            _tc1b, _tc2b = st.columns(2)
                            with _tc1b:
                                if st.button("✓ Sí", key=f"exec_ts_{_si}", type="primary", use_container_width=True):
                                    with st.spinner(f"Limpiando…"):
                                        _ts_r = _limpiar_remitente(_se_email)
                                    st.session_state[_rsk]  = _ts_r
                                    st.session_state[_csk]  = False
                                    st.rerun()
                            with _tc2b:
                                if st.button("✗ No", key=f"cancel_ts_{_si}", use_container_width=True):
                                    st.session_state[_csk] = False
                                    st.rerun()
                    with _s_c4:
                        if not st.session_state[_cpsk]:
                            st.button(
                                "🛡️ Proteger", key=f"btn_ps_{_si}", use_container_width=True,
                                on_click=lambda k=_cpsk: st.session_state.update({k: True}),
                            )
                        else:
                            st.info(f"¿Proteger {_se_email}?")
                            _pc1b, _pc2b = st.columns(2)
                            with _pc1b:
                                if st.button("✓ Sí", key=f"exec_ps_{_si}", type="primary", use_container_width=True):
                                    _ps_r = _proteger_remitente(_se_email, _se_name)
                                    st.session_state[_rpsk]  = _ps_r
                                    st.session_state[_cpsk]  = False
                                    st.rerun()
                            with _pc2b:
                                if st.button("✗ No", key=f"cancel_ps_{_si}", use_container_width=True):
                                    st.session_state[_cpsk] = False
                                    st.rerun()

                    if st.session_state.get(_rsk):
                        _ts_res = st.session_state[_rsk]
                        _ts_mov = _ts_res.get("exitos", 0)
                        _ts_tot = _ts_res.get("procesados", 0)
                        if _ts_tot == 0:
                            st.info(f"No se encontraron correos de {_se_email}.")
                        else:
                            st.success(f"✓ {_ts_mov} de {_ts_tot} correos de {_se_email} movidos.")
                    if st.session_state.get(_rpsk):
                        _ps_res = st.session_state[_rpsk]
                        if _ps_res.get("already_protected"):
                            st.info(f"{_se_email} ya estaba protegido.")
                        elif _ps_res.get("success"):
                            st.success(f"🛡️ **{_se_email}** protegido con etiqueta **{_ps_res['label']}**.")
                        elif _ps_res.get("error"):
                            st.error(f"Error: {_ps_res['error']}")
                    st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA: LIMPIEZA AUTOMÁTICA
# ══════════════════════════════════════════════════════════════════════════════

elif _current_page == "automatica":
    st.markdown("## ⏰ Limpieza automática")
    st.caption(
        "Programa una limpieza periódica. Solo mueve correos a la papelera — "
        "nunca borra permanentemente. Tienes 30 días para recuperar cualquier correo."
    )

    _sch_obj    = _get_scheduler()
    _sch_status = _schedule_status()
    _sch_avail  = _sch_status.get("scheduler_available", False)

    if not _sch_avail:
        st.warning("Para activar limpiezas automáticas instala APScheduler: `pip install APScheduler>=3.10`")
    elif not connected:
        st.warning("Conecta tu cuenta de Gmail para activar la limpieza automática.")
    else:
        # ── Toggle principal ──────────────────────────────────────────────────
        with st.container(border=True):
            _sched_enabled = st.toggle(
                "Mantener mi correo limpio automáticamente",
                value=bool(_sch_status.get("enabled", False)),
                key="sched_toggle",
            )

            if _sched_enabled:
                st.markdown("")
                _sf1, _sf2, _sf3 = st.columns(3)
                with _sf1:
                    _sched_freq = st.selectbox(
                        "Frecuencia",
                        options=["daily", "weekly", "monthly"],
                        index=["daily", "weekly", "monthly"].index(
                            _sch_status.get("frequency", "weekly")
                        ),
                        format_func=lambda x: {"daily": "Diaria", "weekly": "Semanal", "monthly": "Mensual"}[x],
                        key="sched_freq",
                    )
                with _sf2:
                    _sched_dow = st.selectbox(
                        "Día de la semana",
                        options=["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                        index=["monday","tuesday","wednesday","thursday","friday","saturday","sunday"].index(
                            _sch_status.get("day_of_week", "sunday")
                        ),
                        format_func=lambda x: {
                            "monday": "Lunes", "tuesday": "Martes", "wednesday": "Miércoles",
                            "thursday": "Jueves", "friday": "Viernes",
                            "saturday": "Sábado", "sunday": "Domingo",
                        }[x],
                        key="sched_dow",
                        disabled=_sched_freq != "weekly",
                    )
                with _sf3:
                    _sched_hour = st.number_input(
                        "Hora (0-23)",
                        min_value=0, max_value=23,
                        value=int(_sch_status.get("hour", 3)),
                        key="sched_hour",
                    )

                _sched_cats = st.multiselect(
                    "Categorías a limpiar",
                    options=list(_CAT_OPTIONS.keys()),
                    default=_sch_status.get("categories", ["spam", "promociones"]),
                    format_func=lambda x: _CAT_OPTIONS.get(x, x),
                    key="sched_cats",
                )

                if st.button("💾 Guardar configuración", key="btn_save_sched", type="primary"):
                    _sch_obj.configure(
                        frequency=_sched_freq,
                        categories=_sched_cats or ["spam"],
                        hour=int(_sched_hour),
                        day_of_week=_sched_dow,
                        enabled=True,
                    )
                    _sch_obj.start()
                    st.session_state["schedule_saved"] = True
                    st.rerun()

                if st.session_state.get("schedule_saved"):
                    st.success("Limpieza automática configurada y activada.")
                    st.session_state["schedule_saved"] = False

            else:
                if _sch_status.get("enabled"):
                    _sch_obj.stop()
                st.caption("La limpieza automática está desactivada.")

        # ── Próxima limpieza ──────────────────────────────────────────────────
        if _sched_enabled:
            _sch_live = _schedule_status()
            _next_str = _sch_live.get("next_run")
            if _next_str:
                from gmail_processor.scheduler import format_next_run
                with st.container(border=True):
                    st.markdown("### 📅 Próxima limpieza programada")
                    st.markdown(f"## {format_next_run(_next_str)}")

            # ── Historial ─────────────────────────────────────────────────────
            _last_run = _sch_live.get("last_run")
            _last_res = _sch_live.get("last_run_result")
            if _last_run:
                st.markdown("### Último resultado")
                _lrd = _last_run[:19].replace("T", " ")
                with st.container(border=True):
                    st.caption(f"Ejecutada el {_lrd}")
                    if isinstance(_last_res, dict) and "error" in _last_res:
                        st.warning(f"Error: {_last_res['error']}")
                    elif isinstance(_last_res, dict):
                        _lr_proc = _last_res.get("procesados", 0)
                        _lr_ok   = _last_res.get("exitos",     0)
                        st.success(f"✓ **{_lr_ok}** de {_lr_proc} correos movidos a la papelera.")
                    else:
                        st.caption("Sin información del resultado.")

# ══════════════════════════════════════════════════════════════════════════════
# PÁGINA: OPCIONES AVANZADAS
# ══════════════════════════════════════════════════════════════════════════════

elif _current_page == "avanzadas":
    st.markdown("## ⚙️ Opciones avanzadas")
    st.caption("Herramientas técnicas, estadísticas del sistema y configuración inicial")

    _adv_tabs = st.tabs([
        "📈 Estadísticas", "📋 Audit log", "💬 Feedback",
        "🔧 Config. inicial", "🔄 Procesar inbox", "🐛 Debug",
    ])

    # ── Estadísticas ──────────────────────────────────────────────────────────
    with _adv_tabs[0]:
        st.markdown("Métricas del motor de aprendizaje, calidad de las reglas y resumen del audit log.")
        if st.button("🔄 Actualizar estadísticas", key="btn_load_stats"):
            with st.spinner("Cargando…"):
                st.session_state["stats_data"] = _cargar_stats()
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
                        "Precisión":   f"{(1 - s.get('false_positives', 0)/s['trashed']):.1%}"
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
                    st.session_state["audit_data"] = _cargar_audit(int(_al_last), _dec_filter)
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
            "Registra feedback sobre una decisión del procesador para mejorar el aprendizaje. "
            "Úsalo si un correo importante fue mandado a la papelera, o para reforzar una decisión correcta."
        )
        with st.form("feedback_form"):
            _fb_sender = st.text_input(
                "Dirección del remitente",
                placeholder="ejemplo@dominio.com",
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
            _fb_rule   = st.text_input("Nombre de la regla (opcional)", placeholder="ej: promotions_60d")
            _fb_submit = st.form_submit_button("Enviar feedback", type="primary", use_container_width=True)

        if _fb_submit:
            if not _fb_sender.strip():
                st.error("Ingresa la dirección de correo del remitente.")
            else:
                with st.spinner("Registrando feedback…"):
                    _fb_r = _enviar_feedback(_fb_sender.strip(), _fb_outcome, _fb_rule.strip())
                st.session_state["feedback_result"] = _fb_r
                st.rerun()

        _fb_res = st.session_state["feedback_result"]
        if _fb_res is not None:
            if _fb_res.get("accepted"):
                st.success(f"✓ Feedback aceptado — confianza: {_fb_res['confidence']:.2f} | impacto: {_fb_res['impact']}")
            elif _fb_res.get("pending_count", 0) > 0:
                st.info(f"Feedback en espera — se necesitan {_fb_res['pending_count']}/2 repeticiones.")
            else:
                st.warning(f"Feedback bloqueado — razón: {_fb_res.get('gate_reason', 'desconocida')}")
            if _fb_res.get("drift_capped"):
                st.caption("El delta fue reducido por el límite diario de drift.")

    # ── Config. inicial ───────────────────────────────────────────────────────
    with _adv_tabs[3]:
        st.markdown(
            "Analiza tu historial de Gmail para detectar contactos importantes y dominios de confianza "
            "(bancos, gobierno, empresa). Distingue contactos reales de newsletters usando tus respuestas, "
            "estrellas y frecuencia de contacto."
        )
        _RANGE_OPTIONS = {
            "Últimos 6 meses  (rápido, ~1-2 min)":      180,
            "Últimos 12 meses (recomendado, ~2-4 min)":  365,
            "Últimos 2 años   (~5-10 min)":              730,
            "Todo el historial (puede tardar >10 min)":  None,
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
                "Analizar todo el historial puede tardar mucho en cuentas antiguas. "
                "Si tarda demasiado, cierra y elige un rango más corto."
            )
        if st.button("🔍 Iniciar análisis", key="btn_smart_setup", type="primary",
                     disabled=not connected, use_container_width=True):
            _ss_status = st.empty()
            st.session_state["smart_setup_result"] = _ejecutar_smart_setup(_scan_days, _ss_status)
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
                    f"Análisis completado — **{_ss_sent_tot:,}** enviados + **{_ss_inbox_tot:,}** recibidos. "
                    f"**{len(_ss_contacts)}** contactos, **{len(_ss_domains)}** dominios detectados."
                )
                if _ss_contacts:
                    st.subheader("Contactos importantes detectados")
                    st.dataframe([
                        {
                            "Nombre / Email": f"{c['name']} <{c['email']}>" if c["name"] else c["email"],
                            "Tipo":       c["domain_type"],
                            "Correos":    c["count"],
                            "Respondidos":c["replied"],
                            "Puntuación": c["score"],
                        }
                        for c in _ss_contacts
                    ], use_container_width=True, hide_index=True)
                if _ss_domains:
                    st.subheader("Dominios de confianza detectados")
                    _icon_map = {"financial": "🏦", "government": "🏛️", "educational": "🎓"}
                    for d in _ss_domains:
                        _ic = _icon_map.get(d["domain_type"], "🌐")
                        st.markdown(
                            f"- {_ic} **{d['domain']}** — etiqueta `{d['label']}`, "
                            f"acción `{d['action']}` ({d['total_msgs']} mensajes)"
                        )

    # ── Procesar inbox ─────────────────────────────────────────────────────────
    with _adv_tabs[4]:
        st.markdown(
            "Clasifica tu bandeja de entrada con reglas inteligentes y aplica etiquetas automáticamente. "
            "Identifica contactos importantes, publicidad y mensajes candidatos a la papelera."
        )
        _dry = st.toggle(
            "Modo simulación — ver decisiones sin aplicar cambios reales",
            value=True,
            key="proc_dry_run",
            disabled=not connected,
        )
        if not st.session_state["confirm_proc"]:
            st.button(
                "🔍 Simular procesamiento" if _dry else "🔄 Procesar inbox (cambios reales)",
                key="btn_proc",
                type="secondary" if _dry else "primary",
                disabled=not connected,
                use_container_width=True,
                on_click=lambda: st.session_state.update({"confirm_proc": True}),
            )
        else:
            _mode_txt = "simulación (sin cambios)" if _dry else "REAL — se etiquetarán y moverán correos"
            st.warning(f"¿Confirmas procesar el inbox en modo **{_mode_txt}**?")
            _pcc1, _pcc2 = st.columns(2)
            with _pcc1:
                if st.button("✓ Sí, procesar", key="exec_proc", type="primary", use_container_width=True):
                    with st.spinner("Procesando correos…"):
                        _pr = _ejecutar_procesador(dry_run=_dry)
                    st.session_state["proc_result"]  = _pr
                    st.session_state["confirm_proc"] = False
                    st.rerun()
            with _pcc2:
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
                    st.info("No se encontraron correos para procesar.")
                else:
                    st.success(f"✓ Se analizaron **{_n}** correos.")
                    _m1, _m2, _m3, _m4, _m5 = st.columns(5)
                    _m1.metric("Etiquetados", _proc_r.get("labeled",   0))
                    _m2.metric("Importantes", _proc_r.get("important", 0))
                    _m3.metric("Archivados",  _proc_r.get("archived",  0))
                    _m4.metric("Papelera",    _proc_r.get("trashed",   0))
                    _m5.metric("Omitidos",    _proc_r.get("skipped",   0))

    # ── Debug ──────────────────────────────────────────────────────────────────
    with _adv_tabs[5]:
        st.markdown(
            "Ejecuta el procesador con nivel de log **DEBUG** para ver la traza completa "
            "de cada correo: qué reglas se evaluaron, qué puntuación obtuvieron, y por qué "
            "se tomó cada decisión. Siempre corre en **modo simulación** — no modifica Gmail."
        )
        if st.button("🐛 Ejecutar con DEBUG", key="btn_debug",
                     disabled=not connected, use_container_width=True):
            with st.spinner("Ejecutando en modo DEBUG… puede tardar varios minutos."):
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
                st.success(f"✓ {_dbg_s.get('processed', 0)} correos procesados (simulación).")
                _d1, _d2, _d3, _d4 = st.columns(4)
                _d1.metric("Etiquetados", _dbg_s.get("labeled",  0))
                _d2.metric("Papelera",    _dbg_s.get("trashed",  0))
                _d3.metric("Archivados",  _dbg_s.get("archived", 0))
                _d4.metric("Omitidos",    _dbg_s.get("skipped",  0))
            if _dbg_l:
                st.text_area("Log DEBUG", value=_dbg_l, height=450, key="debug_log_area")

# ══════════════════════════════════════════════════════════════════════════════
# PANEL DE CHAT INLINE (fallback cuando @st.dialog no está disponible)
# ══════════════════════════════════════════════════════════════════════════════

if not _HAS_CHAT_DIALOG and st.session_state.get("chat_open", False):
    st.markdown(
        "<hr style='margin:2rem 0 1rem 0;border:none;border-top:1px solid #2d3250'>",
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        _ch1, _ch2 = st.columns([5, 1])
        with _ch1:
            st.markdown(
                "<div style='background:linear-gradient(90deg,#4f6ef7,#6b85f9);"
                "color:white;padding:10px 16px;border-radius:10px;"
                "font-weight:600;font-size:1.05rem'>💬 Asistente de correo</div>",
                unsafe_allow_html=True,
            )
        with _ch2:
            if st.button("✕ Cerrar", key="btn_chat_close"):
                st.session_state["chat_open"] = False
                st.rerun()
        st.markdown("")
        _render_chat_panel()
