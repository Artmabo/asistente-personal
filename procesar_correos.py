"""
Entry point for the Gmail rule-based processor.

── Menú interactivo (recomendado) ───────────────────────────────────────────
  python procesar_correos.py                              # abre el menú interactivo

── Modo script (flags directos) ─────────────────────────────────────────────
  python procesar_correos.py --live                       # classify inbox (real)
  python procesar_correos.py --cleanup                    # classify + cleanup (DRY RUN)
  python procesar_correos.py --cleanup --live             # classify + cleanup (real)
  python procesar_correos.py --cleanup --live --learning  # + persist learning
  python procesar_correos.py --cleanup --debug            # full pipeline trace per email
  python procesar_correos.py --query "is:unread is:inbox"

── Subcommands ───────────────────────────────────────────────────────────────
  feedback <sender> correct|incorrect [--rule RULE] [--source SOURCE]
                                      [--time-to-action SEC]
  stats [--section learning|metrics|categories|all]
  audit [--last N] [--decision TRASH|KEEP|SKIP]

── Ejemplos ─────────────────────────────────────────────────────────────────
  python procesar_correos.py feedback newsletter@spam.com correct
  python procesar_correos.py feedback papa@gmail.com incorrect --rule promotions_60d
  python procesar_correos.py stats --section metrics
  python procesar_correos.py audit --last 50 --decision TRASH
"""
import sys
import argparse
import logging
import gmail_processor.rules as cfg
from gmail_processor import GmailProcessor, setup_logging

_SUBCOMMANDS = {"feedback", "stats", "audit"}


def main():
    # No args → interactive menu
    if len(sys.argv) == 1:
        from gmail_processor.cli_menu import run_menu
        run_menu()
        return

    # Subcommands
    if len(sys.argv) >= 2 and sys.argv[1] in _SUBCOMMANDS:
        cmd = sys.argv[1]
        if cmd == "feedback":
            _cmd_feedback(sys.argv[2:])
        elif cmd == "stats":
            _cmd_stats(sys.argv[2:])
        elif cmd == "audit":
            _cmd_audit(sys.argv[2:])
        return

    parser = argparse.ArgumentParser(
        description="Gmail rule-based processor with adaptive learning"
    )
    parser.add_argument("--live",     action="store_true",
                        help="Disable dry_run and apply changes for real")
    parser.add_argument("--cleanup",  action="store_true",
                        help="Also run storage cleanup after classification")
    parser.add_argument("--learning", action="store_true",
                        help="Write to learning_state.json and adjust rule thresholds "
                             "(requires --cleanup)")
    parser.add_argument("--query",    default=None,
                        help="Gmail search query (overrides QUERY_FILTER in rules.py)")
    parser.add_argument("--debug",    action="store_true",
                        help="Enable DEBUG log level — shows full pipeline trace per email")
    args = parser.parse_args()

    if args.live:
        cfg.DRY_RUN = False

    level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(level=level)

    processor = GmailProcessor()
    processor.run(query=args.query, cleanup=args.cleanup, learning=args.learning)


# ── feedback ──────────────────────────────────────────────────────────────────

def _cmd_feedback(argv: list[str]):
    parser = argparse.ArgumentParser(
        prog="procesar_correos.py feedback",
        description="Register feedback on a cleanup decision",
    )
    parser.add_argument("sender",  help="Email address of the sender")
    parser.add_argument(
        "outcome", choices=["correct", "incorrect"],
        help="'correct' = trash was right | 'incorrect' = should have kept it",
    )
    parser.add_argument("--rule",           default="",
                        help="Rule name that triggered the trash (e.g. promotions_60d)")
    parser.add_argument("--source",         default="manual",
                        choices=["manual", "recovery", "automatic"],
                        help="Feedback source (default: manual)")
    parser.add_argument("--time-to-action", default=None, type=float,
                        dest="time_to_action",
                        help="Seconds between original trash and this feedback")
    args = parser.parse_args(argv)

    setup_logging(level=logging.INFO)
    domain = args.sender.split("@")[-1] if "@" in args.sender else args.sender

    from gmail_processor.learning_engine import LearningEngine, FeedbackEvent
    engine = LearningEngine()
    event  = FeedbackEvent(
        outcome=args.outcome, source=args.source,
        rule_name=args.rule, time_to_action=args.time_to_action,
    )
    result = engine.update_from_feedback(sender=args.sender, domain=domain, event=event)
    engine.persist()

    status = "ACEPTADO" if result.accepted else (
        "EN ESPERA" if result.pending_count > 0 else "BLOQUEADO"
    )
    print(f"\nFeedback procesado:")
    print(f"  Remitente  : {args.sender}")
    print(f"  Dominio    : {domain}")
    print(f"  Resultado  : {args.outcome}")
    print(f"  Fuente     : {args.source}")
    print(f"  Confianza  : {result.confidence:.2f}")
    print(f"  Estado     : {status}")
    print(f"  Razón gate : {result.gate_reason}")
    print(f"  Impacto    : {result.impact}")
    if result.drift_capped:
        print("  Drift      : delta reducido por limite diario")
    if result.pending_count > 0:
        print(
            f"  Pendiente  : {result.pending_count}/{2} repeticiones"
            f" (o confianza >= 0.60)"
        )


# ── stats ─────────────────────────────────────────────────────────────────────

def _cmd_stats(argv: list[str]):
    parser = argparse.ArgumentParser(
        prog="procesar_correos.py stats",
        description="Show persistent learning state and quality metrics",
    )
    parser.add_argument(
        "--section", default="all",
        choices=["learning", "metrics", "categories", "all"],
        help="Which section to display (default: all)",
    )
    args = parser.parse_args(argv)

    setup_logging(level=logging.WARNING)

    from gmail_processor.learning_engine import LearningEngine
    engine = LearningEngine()

    section = args.section

    if section in ("learning", "all"):
        print("\n" + engine.summary())

    if section in ("metrics", "all"):
        print("\n─── Métricas de calidad ──────────────────────────────")
        print(engine.metrics.summary())

    if section in ("categories", "all"):
        cat_model = engine.state.get("category_model", {})
        if cat_model:
            print("\n─── Modelo de categorías Gmail ───────────────────────")
            for cat, s in cat_model.items():
                total = s.get("trashed", 0) + s.get("kept", 0)
                fp    = s.get("false_positives", 0)
                acc   = f"{1 - fp/s['trashed']:.1%}" if s.get("trashed") else "n/a"
                print(
                    f"  {cat}:\n"
                    f"    trashed={s.get('trashed',0)}  kept={s.get('kept',0)}"
                    f"  total={total}  precision={acc}"
                )
        else:
            print("\n  (category_model vacío — aún no se han procesado correos)")

    if section in ("all",):
        from gmail_processor.audit_log import AuditLogger
        audit_stats = AuditLogger().stats_summary()
        print("\n─── Audit log (acumulado) ────────────────────────────")
        for decision, count in audit_stats.items():
            if decision:
                print(f"  {decision}: {count}")


# ── audit ─────────────────────────────────────────────────────────────────────

def _cmd_audit(argv: list[str]):
    parser = argparse.ArgumentParser(
        prog="procesar_correos.py audit",
        description="Show recent audit log entries",
    )
    parser.add_argument("--last", default=20, type=int,
                        help="Number of recent entries to show (default: 20)")
    parser.add_argument("--decision", default=None,
                        choices=["TRASH", "KEEP", "SKIP"],
                        help="Filter by decision type")
    args = parser.parse_args(argv)

    setup_logging(level=logging.WARNING)

    from gmail_processor.audit_log import AuditLogger
    audit   = AuditLogger()
    entries = audit.recent(max(args.last * 3, 200))   # over-fetch to allow filtering

    if args.decision:
        entries = [e for e in entries if e.get("decision") == args.decision]

    entries = entries[-args.last:]

    if not entries:
        print("Audit log vacío o sin entradas para el filtro seleccionado.")
        return

    print(f"\nÚltimas {len(entries)} entradas del audit log:\n")
    print(f"{'TIMESTAMP':<22} {'DEC':<6} {'SENDER':<35} {'SCORE':>7}  {'RULE':<20}  MODE")
    print("─" * 100)
    for e in entries:
        mode = "DRY" if e.get("dry_run") else "LIVE"
        print(
            f"{e.get('ts',''):<22} "
            f"{e.get('decision',''):<6} "
            f"{e.get('sender','')[:34]:<35} "
            f"{e.get('score', 0):>+7.1f}  "
            f"{e.get('rule',''):<20}  "
            f"{mode}"
        )


if __name__ == "__main__":
    main()
