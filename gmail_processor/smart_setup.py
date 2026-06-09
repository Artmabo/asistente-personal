"""
SmartSetup: analyzes Gmail history to suggest important contacts and domains.

Scans up to MAX_MESSAGES from the last SCAN_DAYS days using three signal passes:
  1. IMPORTANT + STARRED messages (highest-signal, fetched first)
  2. Sent thread IDs (to detect reply patterns)
  3. Recent inbox messages (frequency and interaction signals)

Each sender receives a score based on weighted signals. Results above MIN_SCORE
are returned sorted descending, ready for the CLI to present and approve.
"""
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from googleapiclient.errors import HttpError

logger = logging.getLogger("gmail_processor.smart_setup")

# ── Scan limits ───────────────────────────────────────────────────────────────
MAX_MESSAGES      = 500    # inbox messages to scan
MAX_SENT          = 400    # sent messages to index for reply detection
SCAN_DAYS         = 365    # look back 12 months
TOP_N             = 20     # max contacts to present
TOP_DOMAINS       = 8      # max domain suggestions

MIN_SCORE         = 30     # minimum score to appear as suggestion
MIN_MESSAGES      = 2      # minimum emails from sender to be considered

# ── Score weights ─────────────────────────────────────────────────────────────
W_IMPORTANT   = 30          # per email marked IMPORTANT
W_IMPORTANT_CAP = 3         # cap at 3 IMPORTANT signals
W_STARRED     = 25          # per starred email
W_STARRED_CAP = 2
W_REPLY       = 20          # per thread where user replied
W_REPLY_CAP   = 3
W_MSG         = 1           # per message received
W_MSG_CAP     = 30          # cap contribution

DOMAIN_BONUS: dict[str, int] = {
    "financial":   20,
    "government":  20,
    "educational": 15,
    "corporate":   10,
    "personal":     0,
    "promotional": -40,
    "social":      -30,
    "unknown":      0,
}

# ── Label defaults per domain type ────────────────────────────────────────────
DOMAIN_LABELS: dict[str, tuple[str, bool]] = {
    "financial":   ("FINANZAS",  True),   # (label, mark_important)
    "government":  ("GOBIERNO",  True),
    "educational": ("ESCUELA",   False),
    "corporate":   ("TRABAJO",   True),
    "personal":    ("PERSONAL",  False),
    "unknown":     ("CONTACTOS", False),
    "promotional": ("SPAM",      False),
    "social":      ("SOCIAL",    False),
}

# ── Domain classification ─────────────────────────────────────────────────────
_FINANCIAL_DOMAINS = frozenset([
    "banamex.com", "bbva.com", "bancomer.com", "hsbc.com", "hsbc.com.mx",
    "santander.com.mx", "banorte.com", "scotiabank.com.mx", "inbursa.com",
    "banregio.com", "banbajio.com", "citibanamex.com",
    "paypal.com", "stripe.com", "mercadopago.com", "clip.mx",
    "americanexpress.com", "visa.com", "mastercard.com",
    "afore.com.mx", "metlife.com.mx", "gnp.com.mx", "axa.com.mx",
])

_SOCIAL_DOMAINS = frozenset([
    "facebookmail.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "tiktok.com", "youtube.com", "reddit.com",
    "discord.com", "twitch.tv", "pinterest.com", "snapchat.com",
    "notification.twitter.com", "mail.instagram.com",
])

_PROMOTIONAL_DOMAINS = frozenset([
    "mailchimp.com", "sendgrid.net", "constantcontact.com",
    "campaignmonitor.com", "klaviyo.com", "hubspot.com", "marketo.com",
    "exacttarget.com", "salesforce.com", "mailgun.org",
    "amazonses.com", "em.servicios.com", "bounce.com",
])

_FREE_EMAIL_DOMAINS = frozenset([
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com",
    "yahoo.com.mx", "live.com", "live.com.mx", "icloud.com",
    "protonmail.com", "proton.me", "mail.com", "zoho.com",
    "aol.com", "msn.com", "me.com",
])

_AUTOMATED_LOCALS = frozenset([
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "bounces",
    "notifications", "notification", "newsletter", "newsletters",
    "subscriptions", "unsubscribe", "mailing", "auto-reply",
    "autoreply", "support", "help", "info",  # generic — only excluded if domain is promo
])

_DEFINITELY_AUTOMATED = frozenset([
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "bounces",
])


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SenderStats:
    email:           str
    name:            str
    domain:          str
    count:           int         = 0
    important_count: int         = 0
    starred_count:   int         = 0
    replied_threads: set         = field(default_factory=set)
    domain_type:     str         = "unknown"
    score:           float       = 0.0

    @property
    def replied(self) -> int:
        return len(self.replied_threads)


@dataclass
class DomainSuggestion:
    domain:      str
    label:       str
    action:      str             # "mark_important" | "archive"
    sender_count: int            # distinct senders from this domain
    total_msgs:  int
    domain_type: str
    already_in_rules: bool = False


# ── Main class ────────────────────────────────────────────────────────────────

class SmartSetup:
    """Analyzes Gmail history and surfaces important contacts and domains."""

    def __init__(self, service):
        self.service    = service
        self.user_email = self._fetch_user_email()

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(self, progress_cb=None) -> tuple[list[SenderStats], list[DomainSuggestion]]:
        """
        Full scan. Returns (contact_suggestions, domain_suggestions).
        progress_cb(scanned: int, total_estimate: int) is called during the scan.
        """
        from . import rules as cfg

        # Step 1: Index sent thread IDs (reply detection)
        sent_threads = self._index_sent_threads(progress_cb)

        # Step 2: Scan inbox messages
        senders = self._scan_inbox(sent_threads, progress_cb)

        # Step 3: Score + classify
        existing_emails  = set(cfg.CONTACT_RULES.keys())
        existing_domains = {
            d
            for rule in cfg.DOMAIN_RULES
            for d in rule.get("domains", [])
        }

        for stats in senders.values():
            stats.domain_type = _classify_domain(stats.domain)
            stats.score       = _score(stats)

        # Step 4: Filter contact suggestions
        contacts = [
            s for s in senders.values()
            if s.score   >= MIN_SCORE
            and s.count  >= MIN_MESSAGES
            and s.email  not in existing_emails
            and not _is_definitely_automated(s.email)
            and s.domain_type not in ("promotional",)
        ]
        contacts.sort(key=lambda s: s.score, reverse=True)
        contacts = contacts[:TOP_N]

        # Step 5: Domain suggestions (only financial/government/educational
        #          with multiple senders and not already in DOMAIN_RULES)
        domain_stats: dict[str, list[SenderStats]] = {}
        for s in senders.values():
            if s.domain_type in ("financial", "government", "educational"):
                domain_stats.setdefault(s.domain, []).append(s)

        domains: list[DomainSuggestion] = []
        for domain, entries in domain_stats.items():
            if domain in existing_domains or domain in _FREE_EMAIL_DOMAINS:
                continue
            total = sum(e.count for e in entries)
            dtype = entries[0].domain_type
            label, important = DOMAIN_LABELS[dtype]
            action = "mark_important" if important else "archive"
            domains.append(DomainSuggestion(
                domain=domain, label=label, action=action,
                sender_count=len(entries), total_msgs=total,
                domain_type=dtype,
            ))
        domains.sort(key=lambda d: d.total_msgs, reverse=True)
        domains = domains[:TOP_DOMAINS]

        return contacts, domains

    # ── Private: data collection ──────────────────────────────────────────────

    def _fetch_user_email(self) -> str:
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return profile.get("emailAddress", "").lower()
        except Exception:
            return ""

    def _index_sent_threads(self, progress_cb=None) -> set[str]:
        """Returns the set of threadIds where the user sent a message."""
        thread_ids: set[str] = set()
        query      = f"in:sent newer_than:{SCAN_DAYS}d"
        page_token = None
        fetched    = 0

        if progress_cb:
            progress_cb(0, MAX_SENT, phase="sent")

        while fetched < MAX_SENT:
            try:
                result = self.service.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=min(100, MAX_SENT - fetched),
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                logger.warning(f"Error al indexar enviados: {e}")
                break

            for stub in result.get("messages", []):
                thread_ids.add(stub.get("threadId", ""))
                fetched += 1

            if progress_cb:
                progress_cb(fetched, MAX_SENT, phase="sent")

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.debug(f"Sent threads indexados: {len(thread_ids)}")
        return thread_ids

    def _scan_inbox(
        self,
        sent_threads: set[str],
        progress_cb=None,
    ) -> dict[str, SenderStats]:
        """
        Scans inbox messages (plus IMPORTANT/STARRED) and builds per-sender stats.
        Uses two sub-queries: high-signal first, then recent general messages.
        """
        senders: dict[str, SenderStats] = {}

        # Pass A: IMPORTANT and STARRED messages (most valuable signals)
        high_signal_q = (
            f"newer_than:{SCAN_DAYS}d "
            f"(is:important OR is:starred) "
            f"-in:sent"
        )
        self._fetch_and_process(
            query=high_signal_q,
            cap=200,
            sent_threads=sent_threads,
            senders=senders,
            progress_cb=progress_cb,
            offset=0,
            total=MAX_MESSAGES,
        )

        # Pass B: General recent messages (frequency signals)
        general_q = f"newer_than:{SCAN_DAYS}d in:inbox -in:sent"
        self._fetch_and_process(
            query=general_q,
            cap=MAX_MESSAGES - len(senders),
            sent_threads=sent_threads,
            senders=senders,
            progress_cb=progress_cb,
            offset=len(senders),
            total=MAX_MESSAGES,
        )

        return senders

    def _fetch_and_process(
        self,
        query:        str,
        cap:          int,
        sent_threads: set[str],
        senders:      dict[str, SenderStats],
        progress_cb,
        offset:       int,
        total:        int,
    ):
        page_token = None
        fetched    = 0

        while fetched < cap:
            try:
                result = self.service.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=min(100, cap - fetched),
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                logger.warning(f"Error al listar: {e}")
                break

            stubs = result.get("messages", [])
            if not stubs:
                break

            for stub in stubs:
                if fetched >= cap:
                    break
                try:
                    msg = self.service.users().messages().get(
                        userId="me",
                        id=stub["id"],
                        format="metadata",
                        metadataHeaders=["From"],
                    ).execute()
                except HttpError:
                    fetched += 1
                    continue

                self._ingest(msg, sent_threads, senders)
                fetched += 1

                if progress_cb and fetched % 50 == 0:
                    progress_cb(offset + fetched, total, phase="inbox")

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        if progress_cb:
            progress_cb(offset + fetched, total, phase="inbox")

    def _ingest(
        self,
        message:      dict,
        sent_threads: set[str],
        senders:      dict[str, SenderStats],
    ):
        headers   = message.get("payload", {}).get("headers", [])
        label_ids = message.get("labelIds", [])
        thread_id = message.get("threadId", "")

        email = _extract_email(headers)
        if not email or email == self.user_email:
            return

        name   = _extract_name(headers)
        domain = email.split("@")[-1] if "@" in email else ""

        if email not in senders:
            senders[email] = SenderStats(email=email, name=name, domain=domain)
        s = senders[email]
        if not s.name and name:
            s.name = name

        s.count += 1
        if "IMPORTANT" in label_ids:
            s.important_count += 1
        if "STARRED" in label_ids:
            s.starred_count += 1
        if thread_id and thread_id in sent_threads:
            s.replied_threads.add(thread_id)


# ── Scoring & classification ──────────────────────────────────────────────────

def _score(s: SenderStats) -> float:
    score  = 0.0
    score += min(s.important_count, W_IMPORTANT_CAP) * W_IMPORTANT
    score += min(s.starred_count,   W_STARRED_CAP)   * W_STARRED
    score += min(s.replied,         W_REPLY_CAP)      * W_REPLY
    score += min(s.count,           W_MSG_CAP)        * W_MSG
    score += DOMAIN_BONUS.get(s.domain_type, 0)
    return round(score, 1)


def _classify_domain(domain: str) -> str:
    if not domain:
        return "unknown"
    domain = domain.lower()

    if domain in _FINANCIAL_DOMAINS:
        return "financial"
    if domain in _SOCIAL_DOMAINS:
        return "social"
    if domain in _PROMOTIONAL_DOMAINS:
        return "promotional"

    if any(domain.endswith(t) for t in (".gob.mx", ".gov", ".gob", ".mil", ".gob.mx")):
        return "government"
    if any(domain.endswith(t) for t in (".edu", ".edu.mx", ".ac.mx", ".ac.uk", ".edu.co")):
        return "educational"

    if domain in _FREE_EMAIL_DOMAINS:
        return "personal"

    # Non-free, non-known → corporate
    # But check for common promo/automated patterns in the domain itself
    promo_keywords = ("newsletter", "email.", "mail.", "notify.", "noreply.",
                       "marketing", "promo", "bulk", "bounce", "campaign")
    if any(kw in domain for kw in promo_keywords):
        return "promotional"

    return "corporate"


def _is_definitely_automated(email: str) -> bool:
    local = email.split("@")[0].lower()
    return local in _DEFINITELY_AUTOMATED


# ── Header helpers ────────────────────────────────────────────────────────────

def _get_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_email(headers: list[dict]) -> str:
    raw = _get_header(headers, "From")
    if "<" in raw:
        return raw.split("<")[1].rstrip(">").strip().lower()
    return raw.strip().lower()


def _extract_name(headers: list[dict]) -> str:
    raw = _get_header(headers, "From")
    if "<" in raw:
        name = raw.split("<")[0].strip().strip('"').strip("'")
        return name
    return ""
