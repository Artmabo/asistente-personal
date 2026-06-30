"""
LearningEngine — adaptive scoring with confidence-filtered, drift-controlled learning.

─── Three independent models ────────────────────────────────────────────────
  sender_model    per-email-address adjustments  decay_lambda=0.004 (~173d half-life)
  domain_model    per-domain adjustments         decay_lambda=0.002 (~346d half-life)
  category_model  per-Gmail-category stats       (observability only, no adjustment yet)

─── Score pipeline ──────────────────────────────────────────────────────────
  calculate_score(message) →  ScoreResult
    Static signals:  Gmail labels, domain type (DOMAIN_RULES), contact presence
    Learned signals: per-model adjustments with independent temporal decay
    Decision:        score >= (PROTECT_THRESHOLD - DOUBT_MARGIN) → KEEP

─── Drift control ───────────────────────────────────────────────────────────
  Each model entry tracks daily_delta + daily_delta_date.
  No sender or domain can accumulate more than MAX_DAILY_DELTA (10.0) score
  units of change in a single calendar day.  Excess is silently capped and
  logged.  The daily window resets at midnight.

─── Confidence gate ─────────────────────────────────────────────────────────
  Feedback is accepted when ANY of:
    source == "manual"                        (explicit user command)
    confidence >= CONFIDENCE_THRESHOLD (0.60)
    pending repeat count >= REPEAT_THRESHOLD (2)
  Otherwise the event is queued in pending_feedback.

─── Critical-entity protection ──────────────────────────────────────────────
  "correct" feedback (= "trash was right") is blocked for contacts in
  CONTACT_RULES and mark_important domains in DOMAIN_RULES.  These entities
  can only accumulate positive protective adjustments.

─── Metrics ─────────────────────────────────────────────────────────────────
  engine.metrics exposes a Metrics object backed by state["metrics"].
  Tracks: total_processed, total_keep, total_trash, false_positives,
          manual_overrides, by_category (per-rule), last_run, runs_total.

─── Persistence ─────────────────────────────────────────────────────────────
  learning_state.json  (version 3)
  Automatic migration from v1 and v2 on load.
"""

import copy
import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from . import rules as cfg

logger = logging.getLogger("gmail_processor.learning")

# ── Constants ─────────────────────────────────────────────────────────────────

PROTECT_THRESHOLD    = 20.0
DOUBT_MARGIN         = 5.0

CONFIDENCE_THRESHOLD = 0.60
REPEAT_THRESHOLD     = 2

SOURCE_TRUST: dict[str, float] = {
    "manual":    1.00,
    "recovery":  0.85,
    "automatic": 0.40,
}

FEEDBACK_CORRECT_DELTA   = -5.0
FEEDBACK_INCORRECT_DELTA = +15.0

DECAY_LAMBDA_SENDER   = 0.004   # half-life ≈ 173 days
DECAY_LAMBDA_DOMAIN   = 0.002   # half-life ≈ 346 days
DECAY_FLOOR           = 0.10

MAX_DAILY_DELTA = 10.0          # max absolute score change per entity per calendar day

MIN_SAMPLES_FOR_ADJUSTMENT = 10
ERROR_RATE_TRIGGER         = 0.05
THRESHOLD_INCREASE_DAYS    = 15

_GMAIL_CATEGORIES = [
    "CATEGORY_PROMOTIONS",
    "CATEGORY_SOCIAL",
    "CATEGORY_FORUMS",
    "CATEGORY_UPDATES",
]


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class FeedbackEvent:
    outcome:        str                     # "correct" | "incorrect"
    source:         str  = "manual"
    rule_name:      str  = ""
    time_to_action: Optional[float] = None  # seconds


@dataclass
class FeedbackResult:
    accepted:      bool
    confidence:    float
    gate_reason:   str
    impact:        str
    drift_capped:  bool = False   # True if drift control reduced the delta
    pending_count: int  = 0


@dataclass
class ScoreResult:
    score:    float
    factors:  list[str] = field(default_factory=list)
    decision: str       = "TRASH"   # "KEEP" | "TRASH"
    learned:  bool      = False


# ── Metrics helper ────────────────────────────────────────────────────────────

def _empty_cat() -> dict:
    return {"trashed": 0, "kept": 0, "false_positives": 0}


class Metrics:
    """Persistent quality metrics backed by the state dict."""

    def __init__(self, data: dict):
        self._d = data

    def record_processed(self):
        self._d["total_processed"] += 1

    def record_keep(self, category: str = ""):
        self._d["total_keep"] += 1
        if category:
            self._d["by_category"].setdefault(category, _empty_cat())["kept"] += 1

    def record_trash(self, rule_name: str = ""):
        self._d["total_trash"] += 1
        if rule_name:
            self._d["by_category"].setdefault(rule_name, _empty_cat())["trashed"] += 1

    def record_false_positive(self, rule_name: str = ""):
        self._d["false_positives"] += 1
        if rule_name:
            self._d["by_category"].setdefault(rule_name, _empty_cat())["false_positives"] += 1

    def record_manual_override(self):
        self._d["manual_overrides"] += 1

    def touch_run(self):
        self._d["last_run"]    = datetime.now().isoformat(timespec="seconds")
        self._d["runs_total"] += 1

    def accuracy_estimate(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for cat, s in self._d["by_category"].items():
            total = s.get("trashed", 0)
            if total == 0:
                continue
            result[cat] = round(1.0 - s.get("false_positives", 0) / total, 3)
        return result

    def summary(self) -> str:
        d = self._d
        lines = [
            f"  Total procesados   : {d['total_processed']}",
            f"  Total conservados  : {d['total_keep']}",
            f"  Total enviados     : {d['total_trash']}",
            f"  Falsos positivos   : {d['false_positives']}",
            f"  Overrides manuales : {d['manual_overrides']}",
            f"  Ejecuciones totales: {d['runs_total']}",
            f"  Última ejecución   : {d['last_run'] or 'nunca'}",
        ]
        acc = self.accuracy_estimate()
        if acc:
            lines.append("  Precisión estimada por regla:")
            for cat, a in sorted(acc.items()):
                lines.append(f"    {cat}: {a:.1%}")
        return "\n".join(lines)


# ── State schema ──────────────────────────────────────────────────────────────

def _new_model_entry() -> dict:
    return {
        "adjustment":         0.0,
        "accepted_correct":   0,
        "accepted_incorrect": 0,
        "ignored_correct":    0,
        "ignored_incorrect":  0,
        "last_accepted":      "",
        "daily_delta":        0.0,
        "daily_delta_date":   "",
    }


def _new_metrics() -> dict:
    return {
        "total_processed": 0,
        "total_keep":      0,
        "total_trash":     0,
        "false_positives": 0,
        "manual_overrides": 0,
        "by_category":     {},
        "last_run":        "",
        "runs_total":      0,
    }


_EMPTY_STATE_V3: dict = {
    "version":          3,
    "sender_model":     {},
    "domain_model":     {},
    "category_model":   {},   # Gmail category → {trashed, kept, false_positives}
    "rule_stats":       {},
    "pending_feedback": {},
    "metrics":          _new_metrics(),
}


# ── Main class ────────────────────────────────────────────────────────────────

class LearningEngine:

    def __init__(self, state_path: str = "learning_state.json"):
        self.path    = Path(state_path)
        self.state   = self._load()
        self.metrics = Metrics(self.state.setdefault("metrics", _new_metrics()))
        self._dirty  = False

    # ── Score calculation ─────────────────────────────────────────────────────

    def calculate_score(self, message: dict, rule_name: str = "") -> ScoreResult:
        """
        Scores a message that passed hard-protection checks.
        Reads from sender_model, domain_model (with independent decay),
        and applies static signals from label_ids / DOMAIN_RULES / CONTACT_RULES.
        """
        label_ids = message.get("labelIds", [])
        headers   = message.get("payload", {}).get("headers", [])
        email     = _email_from_headers(headers)
        domain    = email.split("@")[-1] if "@" in email else ""

        score:   float     = 0.0
        factors: list[str] = []
        learned: bool      = False

        # ── Static signals ────────────────────────────────────────────────────
        if "IMPORTANT" in label_ids:
            score += 40; factors.append("+40 etiqueta IMPORTANT")
        if "STARRED" in label_ids:
            score += 30; factors.append("+30 marcado con estrella")
        if "CATEGORY_PROMOTIONS" in label_ids:
            score -= 10; factors.append("-10 categoría Promociones")
        if "CATEGORY_SOCIAL" in label_ids:
            score -= 15; factors.append("-15 categoría Social")
        if "CATEGORY_FORUMS" in label_ids:
            score -= 20; factors.append("-20 categoría Foros")
        if "CATEGORY_UPDATES" in label_ids:
            score -= 8;  factors.append("-8  categoría Actualizaciones")

        for drule in cfg.DOMAIN_RULES:
            if domain in drule["domains"]:
                if drule["action"] == "mark_important":
                    score += 35; factors.append(f"+35 dominio seguro ({domain})")
                elif drule["action"] == "archive":
                    score -= 5;  factors.append(f"-5  dominio servicios ({domain})")
                break

        if email in cfg.CONTACT_RULES:
            score += 50; factors.append(f"+50 contacto protegido ({email})")

        # ── Sender model (decay_lambda = DECAY_LAMBDA_SENDER) ─────────────────
        s_entry = self.state["sender_model"].get(email, {})
        raw_s   = s_entry.get("adjustment", 0.0)
        if raw_s:
            d       = _decay(s_entry.get("last_accepted", ""), DECAY_LAMBDA_SENDER)
            s_adj   = round(raw_s * d, 1)
            if s_adj:
                score  += s_adj
                learned = True
                note    = f" [decay={d:.2f}]" if d < 0.99 else ""
                factors.append(f"{_fmt(s_adj)} sender_model{note} ({email})")

        # ── Domain model (decay_lambda = DECAY_LAMBDA_DOMAIN) ─────────────────
        d_entry = self.state["domain_model"].get(domain, {})
        raw_d   = d_entry.get("adjustment", 0.0)
        if raw_d:
            dcy     = _decay(d_entry.get("last_accepted", ""), DECAY_LAMBDA_DOMAIN)
            d_adj   = round(raw_d * dcy, 1)
            if d_adj:
                score  += d_adj
                learned = True
                note    = f" [decay={dcy:.2f}]" if dcy < 0.99 else ""
                factors.append(f"{_fmt(d_adj)} domain_model{note} ({domain})")

        floor    = PROTECT_THRESHOLD - DOUBT_MARGIN
        decision = "KEEP" if score >= floor else "TRASH"

        return ScoreResult(
            score=round(score, 1),
            factors=factors,
            decision=decision,
            learned=learned,
        )

    # ── Feedback ──────────────────────────────────────────────────────────────

    def update_from_feedback(
        self,
        sender: str,
        domain: str,
        event:  FeedbackEvent,
    ) -> FeedbackResult:
        """Processes a FeedbackEvent through the confidence gate and drift control."""
        if event.outcome not in ("correct", "incorrect"):
            raise ValueError(f"outcome must be 'correct'/'incorrect', got {event.outcome!r}")

        # 1. Critical-entity protection (block negative feedback on protected entities)
        if event.outcome == "correct" and _is_critical(sender, domain):
            entity = (f"contacto protegido ({sender})"
                      if sender in cfg.CONTACT_RULES
                      else f"dominio crítico ({domain})")
            for bucket, key in [(self.state["sender_model"], sender),
                                 (self.state["domain_model"],  domain)]:
                entry = bucket.setdefault(key, _new_model_entry())
                entry["ignored_correct"] += 1
            self._dirty = True
            return FeedbackResult(
                accepted=False, confidence=0.0,
                gate_reason=f"bloqueado — entidad crítica protegida: {entity}",
                impact="sin cambios (entidad inmune a feedback negativo)",
            )

        # 2. Pending context
        pending       = self.state["pending_feedback"].get(sender, {})
        same_outcome  = pending.get("outcome") == event.outcome
        pending_count = pending.get("count", 0) if same_outcome else 0
        total_count   = pending_count + 1

        # 3. Confidence
        confidence = _confidence(event.source, event.time_to_action, pending_count)

        # 4. Gate
        gate_pass = (
            event.source == "manual"
            or confidence >= CONFIDENCE_THRESHOLD
            or total_count >= REPEAT_THRESHOLD
        )

        if not gate_pass:
            self._add_to_pending(sender, domain, event, total_count)
            ign_key = "ignored_correct" if event.outcome == "correct" else "ignored_incorrect"
            for bucket, key in [(self.state["sender_model"], sender),
                                 (self.state["domain_model"],  domain)]:
                bucket.setdefault(key, _new_model_entry())[ign_key] += 1
            self._dirty = True
            return FeedbackResult(
                accepted=False, confidence=confidence,
                gate_reason=(
                    f"confianza insuficiente ({confidence:.2f} < {CONFIDENCE_THRESHOLD}) "
                    f"y repeticiones insuficientes ({total_count}/{REPEAT_THRESHOLD}) "
                    f"— fuente: {event.source}"
                ),
                impact="en espera",
                pending_count=total_count,
            )

        # 5. Delta with confidence scaling + drift control
        raw_delta    = (FEEDBACK_CORRECT_DELTA if event.outcome == "correct"
                        else FEEDBACK_INCORRECT_DELTA)
        scaled_delta = round(raw_delta * confidence, 1)

        impact_parts: list[str] = []
        drift_capped             = False
        ok_key  = "accepted_correct" if event.outcome == "correct" else "accepted_incorrect"
        today   = str(date.today())

        for bucket, key, model_label in [
            (self.state["sender_model"], sender, "sender"),
            (self.state["domain_model"], domain, "domain"),
        ]:
            entry    = bucket.setdefault(key, _new_model_entry())
            old_adj  = entry["adjustment"]

            allowed, capped = _drift_control(entry, scaled_delta)
            if capped:
                drift_capped = True
                logger.info(
                    f"Drift control ({model_label} {key}): "
                    f"{scaled_delta:+.1f} → {allowed:+.1f} (daily cap)"
                )

            entry["adjustment"]    = round(old_adj + allowed, 1)
            entry[ok_key]         += 1
            entry["last_accepted"] = today
            impact_parts.append(f"{model_label}:{key} {old_adj:+.1f} → {entry['adjustment']:+.1f}")

        # 6. Clear pending
        self.state["pending_feedback"].pop(sender, None)

        # 7. Rule stat + metrics
        if event.outcome == "incorrect":
            if event.rule_name:
                self._inc_incorrect(event.rule_name)
            self.metrics.record_false_positive(event.rule_name)

        self._dirty = True
        reason = _gate_reason(event.source, confidence, total_count)
        logger.info(
            f"Feedback ACEPTADO — sender={sender} outcome={event.outcome} "
            f"confidence={confidence:.2f} delta={scaled_delta:+.1f} [{reason}]"
            + ("  [drift capped]" if drift_capped else "")
        )

        return FeedbackResult(
            accepted=True,
            confidence=confidence,
            gate_reason=reason,
            impact=" | ".join(impact_parts),
            drift_capped=drift_capped,
        )

    # ── Action recording ──────────────────────────────────────────────────────

    def record_action(self, email: str, domain: str, rule_name: str):
        """Records that a message was trashed (for rule stats + category model)."""
        if rule_name:
            stats = self.state["rule_stats"].setdefault(rule_name, {
                "trashed": 0, "incorrect": 0, "threshold_days": None
            })
            stats["trashed"] += 1
            self._dirty = True

    def update_category_stats(self, label_ids: list[str], action: str):
        """
        Tracks trashed/kept counts per Gmail category (observability only).
        action: 'trash' | 'keep'
        """
        for cat in _GMAIL_CATEGORIES:
            if cat in label_ids:
                entry = self.state["category_model"].setdefault(
                    cat, {"trashed": 0, "kept": 0, "false_positives": 0}
                )
                if action == "trash":
                    entry["trashed"] += 1
                elif action == "keep":
                    entry["kept"] += 1
                self._dirty = True

    # ── Threshold adjustment ──────────────────────────────────────────────────

    def update_rule_thresholds(self) -> list[str]:
        changes = []
        for rule_name, stats in self.state["rule_stats"].items():
            trashed   = stats.get("trashed", 0)
            incorrect = stats.get("incorrect", 0)
            if trashed < MIN_SAMPLES_FOR_ADJUSTMENT:
                continue
            error_rate = incorrect / trashed
            if error_rate > ERROR_RATE_TRIGGER:
                base    = self._base_threshold(rule_name) or 30
                current = stats.get("threshold_days") or base
                new_val = current + THRESHOLD_INCREASE_DAYS
                stats["threshold_days"] = new_val
                self._dirty = True
                changes.append(
                    f"  {rule_name}: {current}d → {new_val}d  "
                    f"(tasa_error={error_rate:.1%}, {incorrect}/{trashed})"
                )
        if changes:
            logger.info("Ajustes automáticos de threshold:\n" + "\n".join(changes))
        return changes

    def get_threshold(self, rule_name: str, default: int) -> int:
        return (self.state["rule_stats"].get(rule_name, {}).get("threshold_days")
                or default)

    # ── Persistence ───────────────────────────────────────────────────────────

    def persist(self):
        if not self._dirty:
            return
        tmp = self.path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            tmp.replace(self.path)
        except OSError:
            tmp.unlink(missing_ok=True)
            raise
        logger.info(f"Estado guardado → {self.path}")
        self._dirty = False

    # ── Summaries ─────────────────────────────────────────────────────────────

    def summary(self) -> str:
        """Learning state summary (models + pending + rules)."""
        sm      = self.state["sender_model"]
        dm      = self.state["domain_model"]
        cm      = self.state["category_model"]
        rs      = self.state["rule_stats"]
        pending = self.state.get("pending_feedback", {})

        lines = [
            "─── Modelos aprendidos ───────────────────────────────",
            f"  sender_model  : {len(sm)} remitentes",
            f"  domain_model  : {len(dm)} dominios",
            f"  category_model: {len(cm)} categorías observadas",
            f"  Feedback en espera: {len(pending)}",
        ]

        if pending:
            lines.append("  Pendientes:")
            for sender, p in pending.items():
                lines.append(
                    f"    {sender}: outcome={p['outcome']} "
                    f"count={p['count']} first_seen={p['first_seen']}"
                )

        if rs:
            lines.append("─── Reglas ───────────────────────────────────────────")
            for name, stat in rs.items():
                t  = stat.get("trashed", 0)
                i  = stat.get("incorrect", 0)
                er = f"{i/t:.1%}" if t else "n/a"
                td = stat.get("threshold_days")
                lines.append(
                    f"  {name}: enviados={t}  incorrectos={i}  tasa_error={er}"
                    + (f"  threshold_aprendido={td}d" if td else "")
                )

        if cm:
            lines.append("─── Estadísticas por categoría Gmail ────────────────")
            for cat, s in cm.items():
                lines.append(
                    f"  {cat}: trashed={s.get('trashed',0)}  "
                    f"kept={s.get('kept',0)}"
                )

        return "\n".join(lines)

    # ── Private ───────────────────────────────────────────────────────────────

    def _add_to_pending(
        self, sender: str, domain: str, event: FeedbackEvent, total: int
    ):
        existing = self.state["pending_feedback"].get(sender, {})
        if existing.get("outcome") == event.outcome:
            existing["count"] = total
        else:
            self.state["pending_feedback"][sender] = {
                "outcome":    event.outcome,
                "domain":     domain,
                "rule_name":  event.rule_name,
                "count":      total,
                "first_seen": str(date.today()),
            }
        self._dirty = True

    def _inc_incorrect(self, rule_name: str):
        stats = self.state["rule_stats"].setdefault(rule_name, {
            "trashed": 0, "incorrect": 0, "threshold_days": None
        })
        stats["incorrect"] += 1

    def _base_threshold(self, rule_name: str) -> Optional[int]:
        for target in cfg.CLEANUP_RULES.get("targets", []):
            if target["rule"] == rule_name:
                m = re.search(r"older_than:(\d+)d", target["query"])
                return int(m.group(1)) if m else None
        return None

    def _load(self) -> dict:
        if self.path.exists():
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                v = data.get("version", 1)
                if v < 3:
                    data = _migrate_to_v3(data)
                    logger.info(f"Estado migrado v{v} → v3")
                logger.debug(f"Estado cargado desde {self.path}")
                return data
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.warning(f"Estado corrupto en {self.path}, reiniciando.")
        return copy.deepcopy(_EMPTY_STATE_V3)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _drift_control(entry: dict, delta: float) -> tuple[float, bool]:
    """
    Caps delta to MAX_DAILY_DELTA per calendar day.
    Returns (allowed_delta, was_capped).
    Resets daily counter at midnight.
    """
    today = str(date.today())
    if entry.get("daily_delta_date") != today:
        entry["daily_delta"]      = 0.0
        entry["daily_delta_date"] = today

    used      = abs(entry.get("daily_delta", 0.0))
    remaining = max(0.0, MAX_DAILY_DELTA - used)

    if remaining <= 0.0:
        return 0.0, True

    allowed  = math.copysign(min(abs(delta), remaining), delta)
    was_capped = abs(allowed) < abs(delta)
    entry["daily_delta"] = round(entry.get("daily_delta", 0.0) + allowed, 1)
    return round(allowed, 1), was_capped


def _confidence(
    source: str,
    time_to_action: Optional[float],
    pending_count: int,
) -> float:
    base   = SOURCE_TRUST.get(source, 0.50)
    t_bonus = 0.0
    if source == "recovery" and time_to_action is not None:
        t_bonus = 0.10 if time_to_action < 3_600 else (0.05 if time_to_action < 86_400 else 0.0)
    r_bonus = 0.20 if pending_count >= 1 else 0.0
    return min(1.0, round(base + t_bonus + r_bonus, 3))


def _gate_reason(source: str, confidence: float, total: int) -> str:
    if source == "manual":
        return f"feedback manual (confianza={confidence:.2f})"
    if total >= REPEAT_THRESHOLD:
        return f"repetición alcanzada ({total}/{REPEAT_THRESHOLD}) — confianza={confidence:.2f}"
    return f"confianza suficiente ({confidence:.2f} >= {CONFIDENCE_THRESHOLD})"


def _is_critical(sender: str, domain: str) -> bool:
    if sender in cfg.CONTACT_RULES:
        return True
    if domain and f"@{domain}" in cfg.CONTACT_RULES:
        return True
    return any(
        domain in rule["domains"]
        for rule in cfg.DOMAIN_RULES
        if rule.get("action") == "mark_important"
    )


def _decay(last_accepted: str, lam: float) -> float:
    if not last_accepted:
        return 1.0
    try:
        days = (date.today() - date.fromisoformat(last_accepted)).days
        return max(DECAY_FLOOR, math.exp(-lam * days))
    except ValueError:
        return 1.0


def _email_from_headers(headers: list[dict]) -> str:
    for h in headers:
        if h["name"].lower() == "from":
            raw = h["value"]
            if "<" in raw:
                start = raw.rfind("<")
                end = raw.find(">", start)
                if end > start:
                    return raw[start + 1 : end].strip().lower()
            return raw.strip().lower()
    return ""


def _fmt(n: float) -> str:
    return f"{n:+.0f}"


def _migrate_to_v3(old: dict) -> dict:
    """Migrates v1 or v2 state to v3 schema."""
    new = copy.deepcopy(_EMPTY_STATE_V3)

    def _to_v3_entry(src: dict) -> dict:
        entry = _new_model_entry()
        entry["adjustment"]         = src.get("adjustment", 0.0)
        entry["accepted_correct"]   = src.get("correct", src.get("accepted_correct", 0))
        entry["accepted_incorrect"] = src.get("incorrect", src.get("accepted_incorrect", 0))
        entry["ignored_correct"]    = src.get("ignored_correct", 0)
        entry["ignored_incorrect"]  = src.get("ignored_incorrect", 0)
        entry["last_accepted"]      = src.get("last_feedback", src.get("last_accepted", ""))
        return entry

    # v1 used sender_scores/domain_scores; v2 used same names
    for old_key, new_key in [
        ("sender_scores", "sender_model"),
        ("domain_model",  "domain_model"),
    ]:
        for k, v in old.get(old_key, {}).items():
            new[new_key][k] = _to_v3_entry(v)
    # v2 already has domain_model
    for k, v in old.get("domain_scores", {}).items():
        if k not in new["domain_model"]:
            new["domain_model"][k] = _to_v3_entry(v)

    new["rule_stats"]       = copy.deepcopy(old.get("rule_stats", {}))
    new["pending_feedback"] = copy.deepcopy(old.get("pending_feedback", {}))
    new["metrics"]          = old.get("metrics", _new_metrics())
    return new
