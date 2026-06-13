"""
ContactAnalyzer: análisis por lotes de remitentes con memoria persistente.

Calcula un score 0-100 por remitente usando señales de interacción real.
Aprende de las decisiones del usuario ajustando pesos de señales y votando
dominios para clasificación automática futura.
Persiste estado en analysis_state.json y aprendizaje en user_patterns.json.
"""
import json
import logging
import re
import time
import email.utils
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from googleapiclient.errors import HttpError

logger = logging.getLogger("gmail_processor.contact_analyzer")

# ── Constantes públicas ───────────────────────────────────────────────────────

STATE_PATH    = Path("analysis_state.json")
PATTERNS_PATH = Path("user_patterns.json")
_BATCH_SLEEP  = 0.2

SCORE_AUTO_PERSONAL = 70
SCORE_AUTO_SPAM     = 20
_DOMAIN_AUTO_VOTES  = 3   # votos mínimos para auto-clasificar dominio

# Señales y sus pesos base (+ positivo, - negativo)
_SIGNAL_BASE: dict[str, int] = {
    "replied":          40,
    "non_mass_domain":  15,
    "no_unsubscribe":   10,
    "has_unsubscribe": -30,
    "is_noreply":      -20,
    "is_esp":          -20,
    "marketing_words": -15,
}

# Etiquetas para la UI (clave → (texto, es_positiva))
SIGNAL_LABELS: dict[str, tuple[str, bool]] = {
    "replied":         ("respondiste alguna vez",        True),
    "non_mass_domain": ("dominio corporativo/personal",  True),
    "no_unsubscribe":  ("sin botón de baja",             True),
    "has_unsubscribe": ("tiene botón de baja",           False),
    "is_noreply":      ("dirección automática/noreply",  False),
    "is_esp":          ("plataforma de email masivo",    False),
    "marketing_words": ("palabras de marketing",         False),
}

# ── Clasificadores ────────────────────────────────────────────────────────────

_FREE_PROVIDERS = frozenset([
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.mx",
    "live.com", "live.com.mx", "icloud.com", "protonmail.com", "proton.me",
    "me.com", "aol.com", "msn.com",
])

_ESP_DOMAINS = frozenset([
    "mailchimp.com", "list-manage.com", "sendgrid.net", "klaviyo.com",
    "constantcontact.com", "hubspot.com", "salesforce.com", "marketo.net",
    "amazonses.com", "mandrillapp.com", "mailgun.org", "sendpulse.com",
    "campaignmonitor.com", "brevo.com", "sendinblue.com", "mailjet.com",
    "postmarkapp.com", "sparkpostmail.com",
])

_NOREPLY_RE = re.compile(
    r"^(no[_\-]?reply|donotreply|noreply|notifications?|mailer[_\-]?daemon|"
    r"bounce|auto[_\-]?reply|newsletter|info|news|updates?|alerts?)@",
    re.IGNORECASE,
)

_MARKETING_WORDS = frozenset([
    "oferta", "descuento", "promo", "promocion", "sale", "% off",
    "unsubscribe", "newsletter", "deal", "gratis", "free", "winner",
    "ganador", "ganaste", "premio", "click here", "limited time",
    "exclusive", "exclusivo", "black friday", "cyber monday",
])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_from(raw: str) -> tuple[str, str]:
    if not raw:
        return "", ""
    pairs = email.utils.getaddresses([raw])
    if pairs:
        name, addr = pairs[0]
        return addr.strip().lower(), name.strip()
    return raw.strip().lower(), ""


def _domain(addr: str) -> str:
    return addr.split("@")[-1].lower() if "@" in addr else ""


def _is_esp(addr: str) -> bool:
    d = _domain(addr)
    return d in _ESP_DOMAINS or any(d.endswith("." + e) for e in _ESP_DOMAINS)


def _has_marketing_subject(subjects: list[str]) -> bool:
    text = " ".join(subjects).lower()
    return any(w in text for w in _MARKETING_WORDS)


def _date_filter(days: int | None) -> str:
    if not days:
        return ""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    return f" after:{since}"


def _get_header(headers: list[dict], name: str) -> str:
    name_l = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_l:
            return h.get("value", "")
    return ""


def _parse_date(date_str: str) -> datetime | None:
    try:
        return email.utils.parsedate_to_datetime(date_str).replace(tzinfo=None)
    except Exception:
        return None


def _default_weights() -> dict[str, float]:
    return {k: 1.0 for k in _SIGNAL_BASE}


def _empty_stats() -> dict:
    return {"total_scanned": 0, "personal": 0, "spam": 0, "commercial": 0, "stale_pending": 0}


def _empty_state() -> dict:
    return {
        "reviewed":            {},
        "pending":             [],
        "pending_meta":        {},
        "last_processed_date": None,
        "stats":               _empty_stats(),
    }


def _empty_patterns() -> dict:
    return {
        "domain_votes":    {},
        "signal_weights":  _default_weights(),
        "decisions_count": 0,
    }


# ── Core class ────────────────────────────────────────────────────────────────

class ContactAnalyzer:
    def __init__(self, service, state_path: str | Path = STATE_PATH):
        self.svc      = service
        self.path     = Path(state_path)
        self.state    = self._load_state()
        self.patterns = self._load_patterns()

    # ── Análisis ──────────────────────────────────────────────────────────────

    def analyze_batch(
        self,
        days_range: int | None = 180,
        batch_size: int = 200,
        progress_cb: Callable | None = None,
    ) -> dict:
        """
        Escanea hasta batch_size mensajes del inbox, agrupa por remitente,
        y clasifica. Los nuevos datos ricos (asuntos, fechas) se acumulan
        por remitente antes de decidir. Persiste después de cada página.
        Returns {auto_personal, auto_spam, pending, already_reviewed, scanned}.
        """
        sent_addrs = self._index_sent_threads(days_range, progress_cb)

        reviewed    = self.state["reviewed"]
        pending_set = set(self.state["pending"])

        _working: dict[str, dict] = {}
        scanned    = 0
        page_token = None
        page       = 0
        date_q     = _date_filter(days_range)
        query      = f"in:inbox -in:sent{date_q}"

        while scanned < batch_size:
            page += 1
            remaining = batch_size - scanned
            try:
                result = self.svc.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=min(remaining, 500),
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                logger.error(f"Error listando mensajes del inbox (página {page}): {e}")
                break

            stubs = result.get("messages", [])
            if not stubs:
                break

            for stub in stubs:
                if scanned >= batch_size:
                    break
                scanned += 1
                try:
                    msg = self.svc.users().messages().get(
                        userId="me",
                        id=stub["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date", "List-Unsubscribe"],
                    ).execute()
                except HttpError as e:
                    logger.warning(f"No se pudo obtener mensaje {stub['id']}: {e}")
                    continue

                headers        = msg.get("payload", {}).get("headers", [])
                addr, name     = _parse_from(_get_header(headers, "From"))
                if not addr:
                    continue

                if addr in reviewed or addr in pending_set:
                    continue

                subject   = _get_header(headers, "Subject")
                date_hdr  = _get_header(headers, "Date")
                has_unsub = bool(_get_header(headers, "List-Unsubscribe"))

                if addr not in _working:
                    _working[addr] = {
                        "name":      name or "",
                        "subjects":  [],
                        "dates":     [],
                        "has_unsub": False,
                        "count":     0,
                    }
                w = _working[addr]
                if name and not w["name"]:
                    w["name"] = name
                if subject and len(w["subjects"]) < 3 and subject not in w["subjects"]:
                    w["subjects"].append(subject)
                if date_hdr:
                    w["dates"].append(date_hdr)
                w["has_unsub"] = w["has_unsub"] or has_unsub
                w["count"]    += 1

            # Persist running count so scan is resumable
            self.state["stats"]["total_scanned"] = (
                self.state["stats"].get("total_scanned", 0) + len(stubs)
            )
            self._save_state()

            if progress_cb:
                progress_cb(
                    scanned=scanned,
                    total_estimated=batch_size,
                    new_pending=0,
                    new_auto=0,
                    phase="inbox",
                    page=page,
                )

            page_token = result.get("nextPageToken")
            if not page_token:
                break
            time.sleep(_BATCH_SLEEP)

        # Classify all accumulated profiles
        auto_personal = 0
        auto_spam     = 0
        new_pending   = 0
        now           = datetime.now().isoformat(timespec="seconds")
        pending_meta  = self.state.setdefault("pending_meta", {})

        for addr, w in _working.items():
            score, signals = self._score(addr, w["subjects"], w["has_unsub"], sent_addrs)
            domain         = _domain(addr)
            auto_dir       = self._check_domain_auto(domain)

            dates_valid = [d for d in (_parse_date(s) for s in w["dates"]) if d]
            first_seen  = min(dates_valid).strftime("%Y-%m-%d") if dates_valid else ""
            last_seen   = max(dates_valid).strftime("%Y-%m-%d") if dates_valid else ""

            entry_base = {"name": w["name"], "score": score, "signals": signals}

            if auto_dir == "personal" or (score >= SCORE_AUTO_PERSONAL and auto_dir != "spam"):
                reviewed[addr] = {**entry_base, "decision": "personal", "auto": True, "decided_at": now}
                auto_personal += 1
            elif auto_dir == "spam" or (score <= SCORE_AUTO_SPAM and auto_dir != "personal"):
                reviewed[addr] = {**entry_base, "decision": "spam", "auto": True, "decided_at": now}
                auto_spam     += 1
            else:
                pending_set.add(addr)
                pending_meta[addr] = {
                    **entry_base,
                    "sample_subjects": w["subjects"][:3],
                    "first_seen":      first_seen,
                    "last_seen":       last_seen,
                    "count":           w["count"],
                    "asked_at":        now,
                }
                new_pending += 1

        already_reviewed  = scanned - sum(w["count"] for w in _working.values())

        self.state["pending"]             = list(pending_set)
        self.state["pending_meta"]        = pending_meta
        self.state["last_processed_date"] = now
        self._update_stats()
        self._save_state()

        return {
            "auto_personal":    auto_personal,
            "auto_spam":        auto_spam,
            "pending":          new_pending,
            "already_reviewed": already_reviewed,
            "scanned":          scanned,
        }

    # ── Aplicar decisiones ────────────────────────────────────────────────────

    def apply_decisions(self, decisions: dict[str, str]) -> dict:
        """
        Aplica las decisiones del usuario para los pendientes.
        Llama learn_from_decision por cada decisión para actualizar patrones.
        Returns {protected, trashed_senders, trashed_msgs, errors}.
        """
        protected       = 0
        trashed_senders = 0
        trashed_msgs    = 0
        errors: list[str] = []

        reviewed     = self.state["reviewed"]
        pending_set  = set(self.state["pending"])
        pending_meta = self.state.get("pending_meta", {})

        for addr, decision in decisions.items():
            meta    = pending_meta.get(addr, {})
            signals = meta.get("signals", [])
            score   = meta.get("score",   0)
            domain  = _domain(addr)

            entry = {
                "name":       meta.get("name", ""),
                "score":      score,
                "signals":    signals,
                "decision":   decision,
                "auto":       False,
                "decided_at": datetime.now().isoformat(timespec="seconds"),
            }

            if decision == "personal":
                r = self._write_contact_rule(addr, meta.get("name", ""))
                if "error" in r and not r.get("already_protected"):
                    errors.append(f"{addr}: {r['error']}")
                else:
                    protected += 1
            elif decision == "spam":
                n = self._trash_sender(addr)
                if n >= 0:
                    trashed_senders += 1
                    trashed_msgs    += n
                else:
                    errors.append(f"{addr}: error al mover a papelera")

            reviewed[addr] = entry
            pending_set.discard(addr)
            pending_meta.pop(addr, None)

            # Aprender de esta decisión
            self.learn_from_decision(addr, domain, decision, score, signals)

        self.state["pending"]      = list(pending_set)
        self.state["pending_meta"] = pending_meta
        self._update_stats()
        self._save_state()

        return {
            "protected":       protected,
            "trashed_senders": trashed_senders,
            "trashed_msgs":    trashed_msgs,
            "errors":          errors,
        }

    # ── Aprendizaje ───────────────────────────────────────────────────────────

    def learn_from_decision(
        self,
        email_addr: str,
        domain: str,
        decision: str,
        score: int,
        signals: list[str],
    ) -> None:
        """
        Actualiza user_patterns.json:
        - domain_votes: vota el dominio hacia personal/spam/skip
        - signal_weights: refuerza o debilita según las señales activas
        Cada ajuste es ±0.05 con límites [0.1, 2.0].
        """
        # Votar dominio
        domain_votes = self.patterns.setdefault("domain_votes", {})
        dv = domain_votes.setdefault(domain, {"personal": 0, "spam": 0, "skip": 0})
        if decision in dv:
            dv[decision] = dv.get(decision, 0) + 1

        # Ajustar pesos de señales
        weights = self.patterns.setdefault("signal_weights", _default_weights())
        for sig in signals:
            base = _SIGNAL_BASE.get(sig, 0)
            if sig not in weights:
                weights[sig] = 1.0
            current = weights[sig]
            if decision == "personal":
                if base > 0:
                    weights[sig] = min(2.0, current + 0.05)
                elif base < 0:
                    weights[sig] = max(0.1, current - 0.05)
            elif decision == "spam":
                if base < 0:
                    weights[sig] = min(2.0, current + 0.05)
                elif base > 0:
                    weights[sig] = max(0.1, current - 0.05)

        self.patterns["decisions_count"] = self.patterns.get("decisions_count", 0) + 1
        self._save_patterns()

    def get_learning_stats(self) -> dict:
        """Devuelve estadísticas de aprendizaje para la UI."""
        domain_votes = self.patterns.get("domain_votes", {})
        auto_domains = sum(
            1 for d, votes in domain_votes.items()
            if self._check_domain_auto_from_votes(votes) is not None
        )
        return {
            "decisions_count": self.patterns.get("decisions_count", 0),
            "auto_domains":    auto_domains,
            "domain_votes":    domain_votes,
            "signal_weights":  self.patterns.get("signal_weights", _default_weights()),
        }

    # ── Consultas de estado ───────────────────────────────────────────────────

    def get_pending(self) -> list[dict]:
        """Devuelve pendientes con metadata completa, ordenados por score desc."""
        pending_meta = self.state.get("pending_meta", {})
        result = []
        for addr in self.state.get("pending", []):
            meta = pending_meta.get(addr, {})
            result.append({
                "email":           addr,
                "name":            meta.get("name",            ""),
                "score":           meta.get("score",           0),
                "signals":         meta.get("signals",         []),
                "sample_subjects": meta.get("sample_subjects", []),
                "first_seen":      meta.get("first_seen",      ""),
                "last_seen":       meta.get("last_seen",       ""),
                "count":           meta.get("count",           0),
            })
        return sorted(result, key=lambda x: x["score"], reverse=True)

    def get_stats(self) -> dict:
        return self.state.get("stats", {})

    def has_previous_state(self) -> bool:
        return self.path.exists() and bool(self.state.get("reviewed"))

    def reset(self):
        self.state = _empty_state()
        self._save_state()

    # ── Score con pesos aprendidos ────────────────────────────────────────────

    def _score(
        self,
        addr: str,
        subjects: list[str],
        has_unsub: bool,
        sent_addrs: set[str],
    ) -> tuple[int, list[str]]:
        weights        = self.patterns.get("signal_weights", _default_weights())
        active_signals = []

        if addr in sent_addrs:
            active_signals.append("replied")

        d = _domain(addr)
        if d and d not in _FREE_PROVIDERS and not _is_esp(addr):
            active_signals.append("non_mass_domain")

        if not has_unsub:
            active_signals.append("no_unsubscribe")
        else:
            active_signals.append("has_unsubscribe")

        if _NOREPLY_RE.match(addr):
            active_signals.append("is_noreply")

        if _is_esp(addr):
            active_signals.append("is_esp")

        if subjects and _has_marketing_subject(subjects):
            active_signals.append("marketing_words")

        score = 50
        for sig in active_signals:
            base = _SIGNAL_BASE[sig]
            w    = weights.get(sig, 1.0)
            score += int(base * w)

        return max(0, min(100, score)), active_signals

    def _check_domain_auto(self, domain: str) -> str | None:
        votes = self.patterns.get("domain_votes", {}).get(domain, {})
        return self._check_domain_auto_from_votes(votes)

    def _check_domain_auto_from_votes(self, votes: dict) -> str | None:
        for direction in ("personal", "spam"):
            count    = votes.get(direction, 0)
            opposite = votes.get("spam" if direction == "personal" else "personal", 0)
            if count >= _DOMAIN_AUTO_VOTES and count > opposite:
                return direction
        return None

    # ── Índice de enviados ────────────────────────────────────────────────────

    def _index_sent_threads(
        self,
        days_range: int | None,
        progress_cb: Callable | None,
    ) -> set[str]:
        date_q     = _date_filter(days_range)
        query      = f"in:sent{date_q}"
        addrs: set[str] = set()
        page_token = None
        fetched    = 0
        page       = 0

        while True:
            page += 1
            try:
                result = self.svc.users().messages().list(
                    userId="me", q=query, maxResults=500, pageToken=page_token,
                ).execute()
            except HttpError:
                break

            stubs = result.get("messages", [])
            if not stubs:
                break

            for stub in stubs:
                try:
                    msg = self.svc.users().messages().get(
                        userId="me", id=stub["id"],
                        format="metadata", metadataHeaders=["To", "Cc"],
                    ).execute()
                    headers = msg.get("payload", {}).get("headers", [])
                    for hname in ("To", "Cc"):
                        raw = _get_header(headers, hname)
                        if raw:
                            for _, a in email.utils.getaddresses([raw]):
                                if a:
                                    addrs.add(a.strip().lower())
                except HttpError:
                    continue

            fetched += len(stubs)
            if progress_cb:
                progress_cb(
                    scanned=fetched, total_estimated=fetched + 200,
                    new_pending=0, new_auto=0, phase="sent", page=page,
                )

            page_token = result.get("nextPageToken")
            if not page_token:
                break
            time.sleep(_BATCH_SLEEP)

        return addrs

    # ── Borrar correos de un remitente ────────────────────────────────────────

    def _trash_sender(self, addr: str) -> int:
        query      = f"from:{addr}"
        page_token = None
        total      = 0

        while True:
            try:
                result = self.svc.users().messages().list(
                    userId="me", q=query, maxResults=500, pageToken=page_token,
                ).execute()
            except HttpError as e:
                logger.error(f"Error listando mensajes de {addr}: {e}")
                return -1

            msgs = result.get("messages", [])
            if not msgs:
                break

            ids = [m["id"] for m in msgs]
            try:
                self.svc.users().messages().batchModify(
                    userId="me",
                    body={"ids": ids, "addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"]},
                ).execute()
                total += len(ids)
            except HttpError as e:
                logger.warning(f"batchModify failed for {len(ids)} msgs from {addr}: {e}")

            page_token = result.get("nextPageToken")
            if not page_token:
                break
            time.sleep(_BATCH_SLEEP)

        return total

    # ── Escribir en rules.py ──────────────────────────────────────────────────

    def _write_contact_rule(self, email_addr: str, name: str) -> dict:
        import re as _re
        if not _re.fullmatch(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", email_addr):
            return {"error": f"Dirección de email inválida: {email_addr!r}"}
        try:
            import importlib
            import gmail_processor.rules as rules_mod

            if email_addr in rules_mod.CONTACT_RULES:
                return {"already_protected": True}

            label      = _derive_label(email_addr, name)
            rules_path = Path(__file__).parent / "rules.py"
            content    = rules_path.read_text(encoding="utf-8")
            lines      = content.split("\n")

            in_cr = False; depth = 0; insert_at = -1
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
                return {"error": "CONTACT_RULES closing brace not found"}

            new_line = f'    "{email_addr}": {{"label": "{label}", "mark_important": True}},'
            lines.insert(insert_at, new_line)
            rules_path.write_text("\n".join(lines), encoding="utf-8")
            importlib.reload(rules_mod)
            return {"success": True, "label": label}
        except Exception as exc:
            return {"error": str(exc)}

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _load_state(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return _empty_state()

    def _save_state(self):
        try:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            logger.error(f"No se pudo guardar estado de análisis: {exc}")

    def _load_patterns(self) -> dict:
        if PATTERNS_PATH.exists():
            try:
                return json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return _empty_patterns()

    def _save_patterns(self):
        try:
            tmp = PATTERNS_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.patterns, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(PATTERNS_PATH)
        except OSError as exc:
            logger.error(f"No se pudo guardar patrones de usuario: {exc}")

    def _update_stats(self):
        reviewed     = self.state["reviewed"]
        pending_meta = self.state.get("pending_meta", {})
        stats        = self.state.setdefault("stats", _empty_stats())
        stats["personal"]   = sum(1 for e in reviewed.values() if e.get("decision") == "personal")
        stats["spam"]       = sum(1 for e in reviewed.values() if e.get("decision") == "spam")
        stats["commercial"] = sum(1 for e in reviewed.values() if e.get("decision") == "commercial")

        cutoff = (datetime.now() - timedelta(days=30)).isoformat(timespec="seconds")
        stats["stale_pending"] = sum(
            1 for m in pending_meta.values()
            if m.get("asked_at", "") < cutoff
        )


# ── Module-level helpers ──────────────────────────────────────────────────────

def _derive_label(email_addr: str, name: str) -> str:
    if name:
        word  = name.strip().split()[0]
        clean = "".join(c for c in word if c.isalpha())[:10]
        if clean:
            return clean.upper()
    domain = email_addr.split("@")[-1] if "@" in email_addr else ""
    local  = email_addr.split("@")[0]  if "@" in email_addr else email_addr
    if domain in _FREE_PROVIDERS:
        clean = "".join(c for c in local if c.isalpha())[:10]
        if clean:
            return clean.upper()
    if domain:
        part  = domain.split(".")[0]
        clean = "".join(c for c in part if c.isalpha())[:8]
        if clean:
            return clean.upper()
    return "CONTACTO"
