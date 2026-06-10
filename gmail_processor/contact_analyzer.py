"""
ContactAnalyzer: análisis por lotes de remitentes con memoria persistente.

Calcula un score 0-100 para cada remitente combinando señales de interacción real
(respuestas, destinatarios directos) con señales negativas (ESP, noreply, List-Unsubscribe).
Persiste el estado en analysis_state.json para poder reanudar análisis interrumpidos.
"""
import json
import re
import time
import email.utils
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from googleapiclient.errors import HttpError

# ── Constantes ────────────────────────────────────────────────────────────────

STATE_PATH = Path("analysis_state.json")
_BATCH_SLEEP = 0.2

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

SCORE_AUTO_PERSONAL = 70   # >= este score → personal automático
SCORE_AUTO_SPAM     = 20   # <= este score → spam automático


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_from(raw: str) -> tuple[str, str]:
    """Returns (email_lower, display_name) from a raw From header."""
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


def _has_marketing_subject(subject: str) -> bool:
    sl = subject.lower()
    return any(w in sl for w in _MARKETING_WORDS)


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


# ── Core class ────────────────────────────────────────────────────────────────

class ContactAnalyzer:
    def __init__(self, service, state_path: str | Path = STATE_PATH):
        self.svc   = service
        self.path  = Path(state_path)
        self.state = self._load()

    # ── Public ────────────────────────────────────────────────────────────────

    def analyze_batch(
        self,
        days_range: int | None = 180,
        batch_size: int = 200,
        progress_cb: Callable | None = None,
    ) -> dict:
        """
        Scans inbox messages in pages of batch_size, scores new senders.
        Returns {auto_personal, auto_spam, pending, already_reviewed}.
        Persists state after each page (tolerant to interruptions).
        """
        date_q  = _date_filter(days_range)
        query   = f"in:inbox -in:sent{date_q}"

        # Build sent-thread index first (needed for reply signal)
        sent_threads = self._index_sent_threads(days_range, progress_cb)

        reviewed    = self.state["reviewed"]
        pending_set = set(self.state["pending"])

        auto_personal = 0
        auto_spam     = 0
        new_pending   = 0
        already       = 0
        scanned       = 0
        page_token    = None
        page          = 0

        while True:
            page += 1
            try:
                result = self.svc.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=min(batch_size, 500),
                    pageToken=page_token,
                ).execute()
            except HttpError:
                break

            stubs = result.get("messages", [])
            if not stubs:
                break

            for stub in stubs:
                scanned += 1
                try:
                    msg = self.svc.users().messages().get(
                        userId="me",
                        id=stub["id"],
                        format="metadata",
                        metadataHeaders=[
                            "From", "Subject", "Date",
                            "List-Unsubscribe", "List-Unsubscribe-Post",
                        ],
                    ).execute()
                except HttpError:
                    continue

                headers = msg.get("payload", {}).get("headers", [])
                addr, name = _parse_from(_get_header(headers, "From"))
                if not addr:
                    continue

                if addr in reviewed:
                    already += 1
                    continue
                if addr in pending_set:
                    already += 1
                    continue

                subject   = _get_header(headers, "Subject")
                has_unsub = bool(_get_header(headers, "List-Unsubscribe"))
                date_hdr  = _get_header(headers, "Date")

                score, signals = self._score(
                    addr, name, subject, has_unsub, sent_threads,
                )

                entry = {
                    "name":       name,
                    "score":      score,
                    "signals":    signals,
                    "decided_at": datetime.now().isoformat(timespec="seconds"),
                }

                if score >= SCORE_AUTO_PERSONAL:
                    entry["decision"] = "personal"
                    entry["auto"]     = True
                    reviewed[addr]    = entry
                    auto_personal    += 1
                elif score <= SCORE_AUTO_SPAM:
                    entry["decision"] = "spam"
                    entry["auto"]     = True
                    reviewed[addr]    = entry
                    auto_spam        += 1
                else:
                    pending_set.add(addr)
                    self.state["pending_meta"] = self.state.get("pending_meta", {})
                    self.state["pending_meta"][addr] = {
                        "name":    name,
                        "score":   score,
                        "signals": signals,
                    }
                    new_pending += 1

            self.state["pending"] = list(pending_set)
            self.state["stats"]["total_scanned"] = (
                self.state["stats"].get("total_scanned", 0) + len(stubs)
            )
            self._save()

            if progress_cb:
                progress_cb(
                    scanned=scanned,
                    total_estimated=scanned + 200,
                    new_pending=new_pending,
                    new_auto=auto_personal + auto_spam,
                )

            page_token = result.get("nextPageToken")
            if not page_token:
                break

            time.sleep(_BATCH_SLEEP)

        self.state["last_processed_date"] = datetime.now().isoformat(timespec="seconds")
        self._update_stats()
        self._save()

        return {
            "auto_personal":    auto_personal,
            "auto_spam":        auto_spam,
            "pending":          new_pending,
            "already_reviewed": already,
            "scanned":          scanned,
        }

    def apply_decisions(self, decisions: dict[str, str]) -> dict:
        """
        Applies user decisions for pending senders.
        decisions: {email: "personal" | "spam" | "skip"}
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
            meta = pending_meta.get(addr, {})
            entry = {
                "name":       meta.get("name", ""),
                "score":      meta.get("score", 0),
                "signals":    meta.get("signals", []),
                "decision":   decision,
                "auto":       False,
                "decided_at": datetime.now().isoformat(timespec="seconds"),
            }

            if decision == "personal":
                result = self._write_contact_rule(addr, meta.get("name", ""))
                if "error" in result:
                    errors.append(f"{addr}: {result['error']}")
                else:
                    protected += 1
            elif decision == "spam":
                n = self._trash_sender(addr)
                if n >= 0:
                    trashed_senders += 1
                    trashed_msgs    += n
                else:
                    errors.append(f"{addr}: error al mover a papelera")
            # "skip" → just mark reviewed, no action

            reviewed[addr] = entry
            pending_set.discard(addr)
            pending_meta.pop(addr, None)

        self.state["pending"]      = list(pending_set)
        self.state["pending_meta"] = pending_meta
        self._update_stats()
        self._save()

        return {
            "protected":       protected,
            "trashed_senders": trashed_senders,
            "trashed_msgs":    trashed_msgs,
            "errors":          errors,
        }

    def get_pending(self) -> list[dict]:
        """Returns pending senders with their metadata, sorted by score desc."""
        pending_meta = self.state.get("pending_meta", {})
        result = []
        for addr in self.state.get("pending", []):
            meta = pending_meta.get(addr, {})
            result.append({
                "email":   addr,
                "name":    meta.get("name", ""),
                "score":   meta.get("score", 0),
                "signals": meta.get("signals", []),
            })
        return sorted(result, key=lambda x: x["score"], reverse=True)

    def get_stats(self) -> dict:
        return self.state.get("stats", {})

    def has_previous_state(self) -> bool:
        return self.path.exists() and bool(self.state.get("reviewed"))

    def reset(self):
        self.state = _empty_state()
        self._save()

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score(
        self,
        addr: str,
        name: str,
        subject: str,
        has_unsub: bool,
        sent_threads: set[str],
    ) -> tuple[int, list[str]]:
        score   = 50
        signals = []

        thread_id = None  # We don't have thread_id here, use domain heuristic

        # +40 replied (thread in sent)
        # We check by addr in sent_threads (built as set of recipient emails)
        if addr in sent_threads:
            score += 40
            signals.append("+40 respondiste a este remitente")

        # +15 non-mass domain
        d = _domain(addr)
        if d and d not in _FREE_PROVIDERS and not _is_esp(addr):
            score += 15
            signals.append("+15 dominio corporativo/personal")

        # +10 no List-Unsubscribe
        if not has_unsub:
            score += 10
            signals.append("+10 sin cabecera de baja")
        else:
            score -= 30
            signals.append("-30 tiene List-Unsubscribe (newsletter)")

        # -20 noreply pattern
        if _NOREPLY_RE.match(addr):
            score -= 20
            signals.append("-20 dirección noreply/automatizada")

        # -20 ESP domain
        if _is_esp(addr):
            score -= 20
            signals.append("-20 dominio de plataforma de email masivo")

        # -15 marketing subject
        if _has_marketing_subject(subject):
            score -= 15
            signals.append("-15 asunto contiene palabras de marketing")

        return max(0, min(100, score)), signals

    # ── Sent index ────────────────────────────────────────────────────────────

    def _index_sent_threads(
        self,
        days_range: int | None,
        progress_cb: Callable | None,
    ) -> set[str]:
        """Returns set of To: email addresses found in sent mail."""
        date_q = _date_filter(days_range)
        query  = f"in:sent{date_q}"
        addrs: set[str] = set()
        page_token = None
        fetched    = 0
        page       = 0

        while True:
            page += 1
            try:
                result = self.svc.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=500,
                    pageToken=page_token,
                ).execute()
            except HttpError:
                break

            stubs = result.get("messages", [])
            if not stubs:
                break

            for stub in stubs:
                try:
                    msg = self.svc.users().messages().get(
                        userId="me",
                        id=stub["id"],
                        format="metadata",
                        metadataHeaders=["To", "Cc"],
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
                    scanned=fetched,
                    total_estimated=fetched + 200,
                    new_pending=0,
                    new_auto=0,
                    phase="sent",
                    page=page,
                )

            page_token = result.get("nextPageToken")
            if not page_token:
                break

            time.sleep(_BATCH_SLEEP)

        return addrs

    # ── Trash helper ─────────────────────────────────────────────────────────

    def _trash_sender(self, addr: str) -> int:
        """Moves all inbox messages from addr to trash. Returns count or -1 on error."""
        query      = f"from:{addr}"
        page_token = None
        total      = 0

        while True:
            try:
                result = self.svc.users().messages().list(
                    userId="me", q=query, maxResults=500, pageToken=page_token,
                ).execute()
            except HttpError:
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
            except HttpError:
                pass

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return total

    # ── Write to rules.py ─────────────────────────────────────────────────────

    def _write_contact_rule(self, email_addr: str, name: str) -> dict:
        """Adds email_addr to CONTACT_RULES in rules.py. Same logic as app.py _proteger_remitente."""
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

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return _empty_state()

    def _save(self):
        self.path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _update_stats(self):
        reviewed = self.state["reviewed"]
        stats    = self.state.setdefault("stats", _empty_stats())
        stats["personal"]   = sum(1 for e in reviewed.values() if e.get("decision") == "personal")
        stats["spam"]       = sum(1 for e in reviewed.values() if e.get("decision") == "spam")
        stats["commercial"] = sum(1 for e in reviewed.values() if e.get("decision") == "commercial")


# ── Module-level helpers ──────────────────────────────────────────────────────

def _empty_stats() -> dict:
    return {"total_scanned": 0, "personal": 0, "spam": 0, "commercial": 0}


def _empty_state() -> dict:
    return {
        "reviewed":            {},
        "pending":             [],
        "pending_meta":        {},
        "last_processed_date": None,
        "stats":               _empty_stats(),
    }


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
