"""
StorageCleaner: identifies and trashes expired/irrelevant emails.

Decision pipeline per message:
  1. Fetch metadata
  2. Hard protection check  → [SKIP] (logged to audit, metrics.record_keep)
  3. Score via LearningEngine → [KEEP] if score >= floor
  4. [TRASH]

--debug mode adds a structured pipeline trace at DEBUG log level:
  EMAIL → RULES → SCORE → CONFIDENCE → DECISION
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from googleapiclient.errors import HttpError

_SUMMARY_PATH = Path("cleanup_summary.json")

from .actions import GmailActions
from .learning_engine import LearningEngine, PROTECT_THRESHOLD, DOUBT_MARGIN
from .audit_log import AuditLogger
from . import rules as cfg

logger = logging.getLogger("gmail_processor.cleanup")


class StorageCleaner:
    def __init__(
        self,
        service,
        actions:       GmailActions,
        engine:        Optional[LearningEngine] = None,
        audit:         Optional[AuditLogger]    = None,
        learning_mode: bool = False,
    ):
        self.service       = service
        self.actions       = actions
        self.engine        = engine
        self.audit         = audit
        self.learning_mode = learning_mode
        self._protected_domains = _build_protected_domains()
        self.stats = {
            "examined": 0,
            "trashed":  0,
            "skipped":  0,
            "kept":     0,
            "errors":   0,
        }

    def run(self) -> dict:
        targets = cfg.CLEANUP_RULES.get("targets", [])
        max_per = cfg.CLEANUP_RULES.get("max_per_query", 200)
        mode    = "DRY RUN" if cfg.DRY_RUN else "LIVE"
        scoring = "activo" if self.engine else "inactivo"

        logger.info(f"\n{'─'*55}")
        logger.info(
            f"  CLEANUP — mode={mode}  targets={len(targets)}"
            f"  cap={max_per}  scoring={scoring}"
        )
        logger.info(f"{'─'*55}")

        if self.engine:
            self.engine.metrics.touch_run()

        for target in targets:
            self._run_target(target, max_per)

        if self.engine and self.learning_mode:
            changes = self.engine.update_rule_thresholds()
            if not changes:
                logger.info("Sin ajustes de threshold necesarios.")
            self.engine.persist()

        if self.audit:
            self.audit.flush()

        self._print_summary()
        self._write_summary()
        return self.stats

    # ── Target loop ───────────────────────────────────────────────────────────

    def _run_target(self, target: dict, cap: int):
        query     = target["query"]
        reason    = target["reason"]
        rule_name = target["rule"]

        logger.info(f"\n[TARGET] rule={rule_name}  query='{query}'")

        count      = 0
        page_token = None

        while count < cap:
            try:
                result = self.service.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=min(100, cap - count),
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                logger.error(f"  List failed: {e}")
                break

            messages = result.get("messages", [])
            if not messages:
                logger.info("  Sin candidatos para este target.")
                break

            for stub in messages:
                if count >= cap:
                    logger.warning(f"  Cap ({cap}) alcanzado — deteniendo este target.")
                    break
                self._evaluate(stub["id"], reason, rule_name)
                count += 1

            page_token = result.get("nextPageToken")
            if not page_token:
                break

    # ── Per-message evaluation ────────────────────────────────────────────────

    def _evaluate(self, msg_id: str, reason: str, rule_name: str):
        self.stats["examined"] += 1

        try:
            message = self.service.users().messages().get(
                userId="me",
                id=msg_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
        except HttpError as e:
            logger.error(f"  Could not fetch {msg_id}: {e}")
            self.stats["errors"] += 1
            return

        sender    = _sender_display(message)
        subject   = _subject(message)
        email     = _sender_email(message)
        domain    = email.split("@")[-1] if "@" in email else ""
        label_ids = message.get("labelIds", [])

        if self.engine:
            self.engine.metrics.record_processed()

        # ── DEBUG: pipeline header ────────────────────────────────────────────
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"\n  ┌─ PIPELINE  {msg_id}\n"
                f"  │  EMAIL   : {sender}\n"
                f"  │  SUBJECT : {subject}\n"
                f"  │  LABELS  : {' '.join(label_ids) or 'ninguno'}\n"
                f"  │  RULE    : {rule_name}"
            )

        # 1. Hard protection
        block = self._protection_reason(message)
        if block:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"  │  RULES   : HARD PROTECTION → {block}\n  └─ DECISION: SKIP")
            logger.info(
                f"  [SKIP ] {_s(sender, 38)} | {_s(subject, 44)}\n"
                f"           Protección : {block}"
            )
            self.stats["skipped"] += 1
            if self.engine:
                self.engine.metrics.record_keep(rule_name)
                self.engine.update_category_stats(label_ids, "keep")
            if self.audit:
                self.audit.log(
                    msg_id=msg_id, sender=email, domain=domain,
                    score=0.0, decision="SKIP", action="skip",
                    rule=rule_name, reason=f"hard_protection:{block}", protected=True,
                )
            return

        # 2. Score-based soft protection
        scored = None
        if self.engine:
            scored = self.engine.calculate_score(message, rule_name)
            floor  = PROTECT_THRESHOLD - DOUBT_MARGIN
            factors_str = " | ".join(scored.factors) if scored.factors else "sin señales"
            learned_tag = "Sí" if scored.learned else "No"

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    f"  │  RULES   : hard_protection=None\n"
                    f"  │  SCORE   : {scored.score:+.1f}  (floor={floor})\n"
                    f"  │  FACTORES: {factors_str}\n"
                    f"  │  APRENDIZ: {learned_tag}\n"
                    f"  └─ DECISION: {scored.decision}"
                    f"  ({'score >= floor' if scored.decision == 'KEEP' else 'score < floor'})"
                )

            if scored.decision == "KEEP":
                logger.info(
                    f"  [KEEP ] {_s(sender, 38)} | {_s(subject, 44)}\n"
                    f"           Score   : {scored.score:+.1f} → KEEP  "
                    f"(aprendizaje: {learned_tag})\n"
                    f"           Factores: {factors_str}"
                )
                self.stats["kept"] += 1
                self.engine.metrics.record_keep(rule_name)
                self.engine.update_category_stats(label_ids, "keep")
                if self.audit:
                    self.audit.log(
                        msg_id=msg_id, sender=email, domain=domain,
                        score=scored.score, decision="KEEP", action="keep",
                        rule=rule_name, reason="score_above_floor",
                        learned=scored.learned,
                    )
                return

        # 3. Trash
        mode       = "DRY RUN" if cfg.DRY_RUN else "LIVE"
        score_line = ""
        if scored:
            factors_str = " | ".join(scored.factors) if scored.factors else "sin señales"
            learned_tag = "Sí" if scored.learned else "No"
            score_line  = (
                f"\n           Score   : {scored.score:+.1f} → TRASH  "
                f"(aprendizaje: {learned_tag})"
                f"\n           Factores: {factors_str}"
            )

        logger.info(
            f"  [TRASH] {_s(sender, 38)} | {_s(subject, 44)}"
            f"{score_line}\n"
            f"           Razón  : {reason}\n"
            f"           Regla  : {rule_name}\n"
            f"           Acción : [{mode}] trash → {msg_id}"
        )

        if self.actions.trash(msg_id):
            self.stats["trashed"] += 1
            if self.engine:
                self.engine.metrics.record_trash(rule_name)
                self.engine.update_category_stats(label_ids, "trash")
                if self.learning_mode:
                    self.engine.record_action(email, domain, rule_name)
            if self.audit:
                self.audit.log(
                    msg_id=msg_id, sender=email, domain=domain,
                    score=scored.score if scored else 0.0,
                    decision="TRASH", action="trash",
                    rule=rule_name, reason=reason,
                    learned=scored.learned if scored else False,
                )
        else:
            self.stats["errors"] += 1

    # ── Hard protection check ─────────────────────────────────────────────────

    def _protection_reason(self, message: dict) -> str | None:
        label_ids = message.get("labelIds", [])

        if "STARRED" in label_ids:
            return "marcado con estrella (STARRED)"
        if "IMPORTANT" in label_ids:
            return "marcado como importante (IMPORTANT)"

        email  = _sender_email(message)
        domain = email.split("@")[-1] if "@" in email else ""

        if email in cfg.CONTACT_RULES:
            return f"contacto protegido ({email})"
        if domain and f"@{domain}" in cfg.CONTACT_RULES:
            return f"dominio protegido por contacto ({domain})"
        if domain in self._protected_domains:
            return f"dominio protegido ({domain})"

        extra = set(cfg.CLEANUP_RULES.get("safe_domains", []))
        if domain in extra:
            return f"dominio seguro adicional ({domain})"

        return None

    # ── Summary ───────────────────────────────────────────────────────────────

    def _write_summary(self):
        """Persists a cleanup summary to cleanup_summary.json for the UI."""
        summary = {
            "ts":      datetime.now().isoformat(timespec="seconds"),
            "dry_run": cfg.DRY_RUN,
            **self.stats,
        }
        try:
            _SUMMARY_PATH.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as e:
            logger.warning(f"Could not write cleanup summary: {e}")

    def _print_summary(self):
        s = self.stats
        logger.info(
            f"\n{'='*55}\n"
            f"  RESUMEN CLEANUP\n"
            f"  Examinados : {s['examined']}\n"
            f"  Papelera   : {s['trashed']}\n"
            f"  Protegidos : {s['skipped']}  (reglas duras)\n"
            f"  Conservados: {s['kept']}  (score)\n"
            f"  Errores    : {s['errors']}\n"
            f"{'='*55}"
        )


# ── Module helpers ────────────────────────────────────────────────────────────

def _build_protected_domains() -> frozenset[str]:
    protected: set[str] = set()
    for rule in cfg.DOMAIN_RULES:
        if rule.get("action") == "mark_important":
            protected.update(rule["domains"])
    return frozenset(protected)


def _get_header(message: dict, name: str) -> str:
    for h in message.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _sender_email(message: dict) -> str:
    raw = _get_header(message, "From")
    if "<" in raw:
        start = raw.rfind("<")
        end = raw.find(">", start)
        if end > start:
            return raw[start + 1 : end].strip().lower()
    return raw.strip().lower()


def _sender_display(message: dict) -> str:
    return _get_header(message, "From") or "?"


def _subject(message: dict) -> str:
    return _get_header(message, "Subject") or "(sin asunto)"


def _s(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"
