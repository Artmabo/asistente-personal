"""
Interactive CLI menu for Gmail Intelligence.

Entry point: run_menu()
  Launched automatically when procesar_correos.py is run with no arguments.
  All destructive operations default to DRY RUN with explicit LIVE confirmation.
"""
import os
import sys
import logging
import importlib
from pathlib import Path
from typing import Callable, Optional

_W    = 54
_SEP  = "─" * _W
_SEP2 = "═" * _W


# ── Entry point ───────────────────────────────────────────────────────────────

def run_menu():
    """Launch the interactive CLI menu. Ctrl+C at any submenu returns here."""
    _set_utf8()
    _service: list = [None]   # mutable box for lazy init

    def _get_service() -> Optional[object]:
        if _service[0] is None:
            print("\n  Conectando con Gmail...", end="", flush=True)
            try:
                from .auth import get_service
                _service[0] = get_service()
                print(" listo.")
            except Exception as exc:
                print(f"\n  ERROR al conectar: {exc}")
                _pause()
                return None
        return _service[0]

    while True:
        try:
            _clear()
            _print_header()
            choice = _main_menu()
        except (KeyboardInterrupt, EOFError):
            print("\n\nHasta luego.\n")
            return

        try:
            if   choice == "0": print("\nHasta luego.\n"); return
            elif choice == "1": _menu_inbox(_get_service)
            elif choice == "2": _menu_cleanup(_get_service)
            elif choice == "3": _menu_stats()
            elif choice == "4": _menu_audit()
            elif choice == "5": _menu_feedback()
            elif choice == "6": _menu_config()
            elif choice == "7": _menu_debug(_get_service)
            else:
                print("  Opción no válida.")
                _pause()
        except (KeyboardInterrupt, EOFError):
            pass   # Ctrl+C at any submenu returns to main menu


# ── Menu rendering ────────────────────────────────────────────────────────────

def _print_header():
    print(_SEP2)
    print(f"  Gmail Intelligence — Asistente Personal")
    print(_SEP2)

def _main_menu() -> str:
    items = [
        ("1", "Procesar inbox      clasificar y etiquetar"),
        ("2", "Cleanup seguro      limpiar almacenamiento"),
        ("3", "Estadísticas        métricas y aprendizaje"),
        ("4", "Audit log           historial de decisiones"),
        ("5", "Feedback            corregir una decisión"),
        ("6", "Configuración       reglas y contactos"),
        ("7", "Debug mode          traza completa del pipeline"),
        ("0", "Salir"),
    ]
    for key, label in items:
        print(f"  {key}.  {label}")
    print(_SEP)
    return input("  Opción: ").strip()

def _section(title: str):
    print(f"\n{_SEP}")
    print(f"  {title}")
    print(_SEP)

def _pause():
    try:
        input("\n  [Enter para continuar]")
    except (KeyboardInterrupt, EOFError):
        pass

def _ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        raw = input(f"  {prompt}{hint}: ").strip()
        return raw or default
    except (KeyboardInterrupt, EOFError):
        raise

def _confirm(msg: str) -> bool:
    try:
        ans = input(f"  {msg} [s/N]: ").strip().lower()
        return ans in ("s", "si", "sí", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


# ── 1. Procesar inbox ─────────────────────────────────────────────────────────

def _menu_inbox(get_svc: Callable):
    _section("PROCESAR INBOX")
    from . import rules as cfg

    print(f"  Query actual : {cfg.QUERY_FILTER}")
    print(f"  Modo actual  : {'DRY RUN' if cfg.DRY_RUN else 'LIVE'}")
    print()

    query = _ask("Query Gmail (Enter = usar la actual)", cfg.QUERY_FILTER)

    live = False
    if _confirm("¿Ejecutar en modo LIVE (aplicar cambios reales)?"):
        if _confirm("  Confirmar: ejecutar en LIVE (esto modifica tu bandeja)"):
            live = True
    mode_label = "LIVE" if live else "DRY RUN"
    print(f"\n  Modo: {mode_label}\n")

    svc = get_svc()
    if svc is None:
        return

    from .processor import GmailProcessor, setup_logging
    setup_logging(level=logging.INFO)
    cfg.DRY_RUN = not live
    proc = GmailProcessor(service=svc)
    proc.run(query=query)
    _pause()


# ── 2. Cleanup seguro ─────────────────────────────────────────────────────────

def _menu_cleanup(get_svc: Callable):
    _section("CLEANUP SEGURO")
    from . import rules as cfg

    targets = cfg.CLEANUP_RULES.get("targets", [])
    cap     = cfg.CLEANUP_RULES.get("max_per_query", 200)

    print(f"  Targets configurados : {len(targets)}")
    print(f"  Cap por target       : {cap} correos")
    print()
    for t in targets:
        print(f"    • {t['rule']:<20} {t['query']}")

    print()
    live = False
    if _confirm("¿Ejecutar en modo LIVE (mover a papelera de verdad)?"):
        if _confirm("  Confirmar: cleanup LIVE (correos irán a papelera)"):
            live = True

    learning = False
    if live:
        learning = _confirm("¿Activar aprendizaje? (guarda cambios en learning_state.json)")

    mode_label = "LIVE" if live else "DRY RUN"
    print(f"\n  Modo: {mode_label}  |  Aprendizaje: {'Sí' if learning else 'No'}\n")

    svc = get_svc()
    if svc is None:
        return

    from .processor import GmailProcessor, setup_logging
    setup_logging(level=logging.INFO)
    cfg.DRY_RUN = not live
    proc = GmailProcessor(service=svc)
    proc.run(cleanup=True, learning=learning)
    _pause()


# ── 3. Estadísticas ───────────────────────────────────────────────────────────

def _menu_stats():
    _section("ESTADÍSTICAS")

    sections = [
        ("1", "Todo (resumen completo)"),
        ("2", "Modelos de aprendizaje"),
        ("3", "Métricas de calidad"),
        ("4", "Categorías Gmail"),
        ("0", "Volver"),
    ]
    for key, label in sections:
        print(f"  {key}.  {label}")
    print()

    choice = _ask("Sección", "1")

    from .processor import setup_logging
    setup_logging(level=logging.WARNING)
    from .learning_engine import LearningEngine
    engine = LearningEngine()

    section_map = {"1": "all", "2": "learning", "3": "metrics", "4": "categories"}
    section = section_map.get(choice)
    if section is None:
        return

    print()
    if section in ("learning", "all"):
        print(engine.summary())

    if section in ("metrics", "all"):
        print(f"\n{_SEP}")
        print("  Métricas de calidad")
        print(_SEP)
        print(engine.metrics.summary())

    if section in ("categories", "all"):
        cat_model = engine.state.get("category_model", {})
        print(f"\n{_SEP}")
        print("  Categorías Gmail")
        print(_SEP)
        if cat_model:
            for cat, s in cat_model.items():
                total = s.get("trashed", 0) + s.get("kept", 0)
                fp    = s.get("false_positives", 0)
                acc   = f"{1 - fp/s['trashed']:.1%}" if s.get("trashed") else "n/a"
                print(f"  {cat}")
                print(f"    papelera={s.get('trashed',0)}  conservados={s.get('kept',0)}"
                      f"  total={total}  precisión={acc}")
        else:
            print("  (sin datos aún — ejecuta cleanup primero)")

    if section == "all":
        from .audit_log import AuditLogger
        stats = AuditLogger().stats_summary()
        print(f"\n{_SEP}")
        print("  Audit log (acumulado)")
        print(_SEP)
        for decision, count in stats.items():
            if decision:
                print(f"  {decision:<6}: {count}")

    _pause()


# ── 4. Audit log ──────────────────────────────────────────────────────────────

def _menu_audit():
    _section("AUDIT LOG")

    n_str = _ask("Cuántas entradas mostrar", "20")
    try:
        n = int(n_str)
    except ValueError:
        n = 20

    print("  Filtrar por: 1=TRASH  2=KEEP  3=SKIP  0=Todos")
    decision_choice = _ask("Filtro", "0")
    decision_map = {"1": "TRASH", "2": "KEEP", "3": "SKIP"}
    decision_filter = decision_map.get(decision_choice)

    from .processor import setup_logging
    setup_logging(level=logging.WARNING)
    from .audit_log import AuditLogger
    audit   = AuditLogger()
    entries = audit.recent(max(n * 3, 200))

    if decision_filter:
        entries = [e for e in entries if e.get("decision") == decision_filter]

    entries = entries[-n:]

    print()
    if not entries:
        print("  Sin entradas para el filtro seleccionado.")
        _pause()
        return

    header = f"{'TIMESTAMP':<20} {'DEC':<6} {'SENDER':<32} {'SCORE':>7}  {'REGLA'}"
    print(f"  {header}")
    print(f"  {'─'*78}")
    for e in entries:
        mode = "DRY" if e.get("dry_run") else "LIVE"
        ts   = e.get("ts", "")[:19]
        dec  = e.get("decision", "")
        sndr = (e.get("sender", "") or "")[:31]
        sc   = e.get("score", 0)
        rule = e.get("rule", "")
        print(f"  {ts:<20} {dec:<6} {sndr:<32} {sc:>+7.1f}  {rule}  {mode}")

    _pause()


# ── 5. Feedback ───────────────────────────────────────────────────────────────

def _menu_feedback():
    _section("FEEDBACK MANUAL")

    print("  Usa esto para corregir una decisión del sistema.")
    print("  'correcto' = la papelera estuvo bien")
    print("  'incorrecto' = el correo NO debió eliminarse")
    print()

    sender = _ask("Email del remitente")
    if not sender:
        return

    print("  1. correcto    (la decisión fue acertada)")
    print("  2. incorrecto  (el correo fue eliminado por error)")
    oc_choice = _ask("Resultado", "2")
    outcome = "correct" if oc_choice == "1" else "incorrect"

    rule   = _ask("Nombre de la regla (opcional, Enter para omitir)", "")
    source = _ask("Fuente: manual / recovery / automatic", "manual")
    if source not in ("manual", "recovery", "automatic"):
        source = "manual"

    domain = sender.split("@")[-1] if "@" in sender else sender

    from .processor import setup_logging
    setup_logging(level=logging.INFO)
    from .learning_engine import LearningEngine, FeedbackEvent
    engine = LearningEngine()
    event  = FeedbackEvent(outcome=outcome, source=source, rule_name=rule)
    result = engine.update_from_feedback(sender=sender, domain=domain, event=event)
    engine.persist()

    print()
    print(f"  Remitente : {sender}")
    print(f"  Resultado : {outcome}")
    print(f"  Confianza : {result.confidence:.2f}")

    if result.accepted:
        print(f"  Estado    : ACEPTADO")
        print(f"  Razón     : {result.gate_reason}")
        print(f"  Impacto   : {result.impact}")
        if result.drift_capped:
            print("  Drift     : delta reducido por límite diario")
    else:
        status = "EN ESPERA" if result.pending_count > 0 else "BLOQUEADO"
        print(f"  Estado    : {status}")
        print(f"  Razón     : {result.gate_reason}")
        if result.pending_count > 0:
            print(f"  Pendiente : {result.pending_count}/2 (necesita repetición o confianza >= 0.60)")

    _pause()


# ── 6. Configuración ──────────────────────────────────────────────────────────

def _menu_config():
    from . import rules as cfg

    while True:
        _section("CONFIGURACIÓN")

        n_contacts = len(cfg.CONTACT_RULES)
        n_domains  = sum(len(r["domains"]) for r in cfg.DOMAIN_RULES)
        n_keywords = sum(len(r["keywords"]) for r in cfg.KEYWORD_RULES)
        n_targets  = len(cfg.CLEANUP_RULES.get("targets", []))
        mode       = "DRY RUN" if cfg.DRY_RUN else "LIVE"

        print(f"  Modo actual       : {mode}")
        print(f"  Contactos prot.   : {n_contacts}")
        print(f"  Dominios          : {n_domains} en {len(cfg.DOMAIN_RULES)} reglas")
        print(f"  Keywords          : {n_keywords} en {len(cfg.KEYWORD_RULES)} reglas")
        print(f"  Targets cleanup   : {n_targets}")
        print()
        print("  1.  Ver contactos protegidos")
        print("  2.  Agregar contacto protegido")
        print("  3.  Eliminar contacto protegido")
        print("  4.  Ver reglas de dominio")
        print("  5.  Ver keywords de spam")
        print("  6.  Abrir rules.py en editor")
        print("  0.  Volver")
        print()

        choice = _ask("Opción", "0")

        if choice == "0":
            return
        elif choice == "1":
            _show_contacts(cfg)
        elif choice == "2":
            _add_contact_interactive(cfg)
        elif choice == "3":
            _remove_contact_interactive(cfg)
        elif choice == "4":
            _show_domain_rules(cfg)
        elif choice == "5":
            _show_keyword_rules(cfg)
        elif choice == "6":
            _open_rules_file()
        else:
            print("  Opción no válida.")
        _pause()


def _show_contacts(cfg):
    print()
    if not cfg.CONTACT_RULES:
        print("  (sin contactos protegidos configurados)")
        return
    print(f"  {'EMAIL':<35} {'LABEL':<15} {'IMPORTANTE'}")
    print(f"  {'─'*60}")
    for email, rule in cfg.CONTACT_RULES.items():
        important = "Sí" if rule.get("mark_important") else "No"
        print(f"  {email:<35} {rule.get('label',''):<15} {important}")


def _show_domain_rules(cfg):
    print()
    for rule in cfg.DOMAIN_RULES:
        print(f"  [{rule['action'].upper()}] label={rule.get('label','')}:")
        for d in rule["domains"]:
            print(f"    • {d}")


def _show_keyword_rules(cfg):
    print()
    for rule in cfg.KEYWORD_RULES:
        print(f"  [{rule['action'].upper()}] label={rule.get('label','')}:")
        for kw in rule["keywords"]:
            print(f"    • {kw}")


def _add_contact_interactive(cfg):
    print()
    email = _ask("Email del contacto (ej: papa@gmail.com)")
    if not email or "@" not in email:
        print("  Email no válido.")
        return

    if email in cfg.CONTACT_RULES:
        print(f"  {email} ya está en los contactos protegidos.")
        return

    label     = _ask("Etiqueta Gmail", "FAMILIA")
    important = _confirm("¿Marcar como importante?")

    ok = _patch_rules_add_contact(email, label, important)
    if ok:
        importlib.reload(cfg)
        print(f"\n  Contacto agregado: {email}  label={label}  importante={'Sí' if important else 'No'}")
    else:
        print("  No se pudo modificar rules.py automáticamente.")
        print(f"  Agrega manualmente en gmail_processor/rules.py:")
        important_str = "True" if important else "False"
        print(f'    "{email}": {{"label": "{label}", "mark_important": {important_str}}},')


def _remove_contact_interactive(cfg):
    print()
    if not cfg.CONTACT_RULES:
        print("  (no hay contactos configurados)")
        return
    _show_contacts(cfg)
    print()
    email = _ask("Email a eliminar")
    if not email:
        return
    if email not in cfg.CONTACT_RULES:
        print(f"  {email} no está en la lista.")
        return
    if not _confirm(f"¿Eliminar protección para {email}?"):
        return
    ok = _patch_rules_remove_contact(email)
    if ok:
        importlib.reload(cfg)
        print(f"  {email} eliminado de contactos protegidos.")
    else:
        print("  No se pudo modificar rules.py automáticamente.")
        print(f"  Elimina manualmente la línea con '{email}' en gmail_processor/rules.py")


def _open_rules_file():
    rules_path = Path(__file__).parent / "rules.py"
    print(f"\n  Archivo: {rules_path}")
    if os.name == "nt":
        if _confirm("¿Abrir en Notepad?"):
            os.startfile(str(rules_path))
    else:
        editor = os.environ.get("EDITOR", "nano")
        print(f"  Abre con: {editor} {rules_path}")


# ── 7. Debug mode ─────────────────────────────────────────────────────────────

def _menu_debug(get_svc: Callable):
    _section("DEBUG MODE — TRAZA COMPLETA")

    from . import rules as cfg

    print("  Muestra EMAIL → RULES → SCORE → DECISION por cada correo.")
    print("  Solo usa DRY RUN en debug mode.\n")

    targets = cfg.CLEANUP_RULES.get("targets", [])
    print(f"  Se examinarán {len(targets)} targets (DRY RUN forzado)")
    print()
    if not _confirm("¿Continuar?"):
        return

    svc = get_svc()
    if svc is None:
        return

    from .processor import GmailProcessor, setup_logging
    setup_logging(level=logging.DEBUG)
    cfg.DRY_RUN = True
    proc = GmailProcessor(service=svc)
    proc.run(cleanup=True, learning=False)
    _pause()


# ── rules.py patching ─────────────────────────────────────────────────────────

def _patch_rules_add_contact(email: str, label: str, important: bool) -> bool:
    rules_path = Path(__file__).parent / "rules.py"
    try:
        lines = rules_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    start_idx = None
    for i, line in enumerate(lines):
        if "CONTACT_RULES: dict[str, dict] = {" in line:
            start_idx = i
            break
    if start_idx is None:
        return False

    end_idx = None
    for i in range(start_idx + 1, len(lines)):
        if lines[i].strip() == "}":
            end_idx = i
            break
    if end_idx is None:
        return False

    for line in lines[start_idx:end_idx]:
        if f'"{email}"' in line and not line.strip().startswith("#"):
            return False  # already exists

    important_str = "True" if important else "False"
    new_entry = f'    "{email}": {{"label": "{label}", "mark_important": {important_str}}},'
    lines.insert(end_idx, new_entry)

    try:
        rules_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


def _patch_rules_remove_contact(email: str) -> bool:
    rules_path = Path(__file__).parent / "rules.py"
    try:
        lines = rules_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    new_lines = []
    removed   = False
    for line in lines:
        if f'"{email}"' in line and not line.strip().startswith("#"):
            removed = True
            continue
        new_lines.append(line)

    if not removed:
        return False

    try:
        rules_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True
    except OSError:
        return False


# ── Terminal helpers ──────────────────────────────────────────────────────────

def _set_utf8():
    if os.name == "nt":
        try:
            os.system("chcp 65001 > nul 2>&1")
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _clear():
    os.system("cls" if os.name == "nt" else "clear")
