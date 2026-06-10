"""
SmartSetup: analyzes Gmail history to suggest important contacts and domains.

── Scoring philosophy ────────────────────────────────────────────────────────
The single strongest signal that something is a real contact (not a newsletter)
is that the user has replied to them.  Newsletters are one-directional by
definition: they never appear in the user's "sent" threads.

Signal hierarchy (highest → lowest):
  1. User replied to a thread from this sender  (+25 each, cap 5)
  2. User starred an email from this sender      (+20 each, cap 2)
  3. Gmail marked the email IMPORTANT            (+8  each, cap 3 — low weight:
                                                  Gmail auto-marks newsletters)
  4. Frequency of received emails                (+1  each, cap 20)
  5. Domain type bonus/penalty                   (±25 to ±-60)

Anti-newsletter signals:
  - Email local part matches known marketing patterns          → −60
  - Email local part starts with known marketing prefix        → −40
  - Display name contains marketing keywords                   → −30
  - High volume (15+) with zero replies                        → −25
  - Behavioral reclassification: corporate + 15+ msgs, 0 reply → newsletter type

── Domain types ──────────────────────────────────────────────────────────────
  financial    banks, payments, insurance
  government   .gob.mx / .gov / .mil
  educational  .edu / .edu.mx / .ac.mx
  corporate    real business domain (non-free, non-promotional)
  personal     free email provider (likely a real person)
  service      account/security alert domains (important but not a "contact")
  newsletter   detected by behavioral or local-part signals
  marketing    detected by name/local-part marketing patterns
  promotional  known ESP/bulk-mail infrastructure domains
  social       social-network notification domains
"""
import logging
import time
from dataclasses import dataclass, field

from googleapiclient.errors import HttpError

logger = logging.getLogger("gmail_processor.smart_setup")

# ── Scan limits ───────────────────────────────────────────────────────────────
# MAX_MESSAGES / MAX_SENT no longer used — analyze() paginates until exhausted.
SCAN_DAYS_DEFAULT = 365   # default look-back passed to analyze(scan_days=…)
TOP_N         = 20    # max contact suggestions to present
TOP_DOMAINS   = 8     # max domain suggestions
MIN_SCORE     = 35    # must clear this threshold to appear as suggestion
MIN_MESSAGES  = 2     # min emails received from sender

_BATCH_SLEEP  = 0.2   # seconds between list-pagination calls (rate-limit headroom)

# ── Scoring weights ───────────────────────────────────────────────────────────
W_REPLY           = 25    # per thread where user replied
W_REPLY_CAP       = 5     # max 5 threads counted  → max +125

W_STARRED         = 20    # per starred email
W_STARRED_CAP     = 2     # max +40

W_IMPORTANT       = 8     # per IMPORTANT label (Gmail auto-marks = low signal)
W_IMPORTANT_CAP   = 3     # max +24

W_FREQUENCY       = 1     # per message received
W_FREQUENCY_CAP   = 20    # max +20

# Penalty for one-way communication (many emails, zero replies)
ONEWAY_THRESHOLD  = 15    # messages received before applying penalty
ONEWAY_PENALTY    = -25

# Newsletter / marketing signal penalties
P_NEWSLETTER_LOCAL  = -60   # exact match in _NEWSLETTER_EXACT_LOCALS
P_MARKETING_PREFIX  = -40   # local part starts with a known marketing prefix
P_MARKETING_NAME    = -30   # display name contains a marketing keyword (once only)

# Domain bonuses applied after all other signals
DOMAIN_BONUS: dict[str, int] = {
    "financial":   25,
    "government":  25,
    "educational": 15,
    "corporate":    8,
    "personal":    10,
    "service":     -5,
    "newsletter":  -50,
    "marketing":   -60,
    "promotional": -50,
    "social":      -40,
    "unknown":      0,
}

# ── Label defaults per domain type ────────────────────────────────────────────
# (label_name, mark_important)
DOMAIN_LABELS: dict[str, tuple[str, bool]] = {
    "financial":   ("FINANZAS",   True),
    "government":  ("GOBIERNO",   True),
    "educational": ("ESCUELA",    False),
    "corporate":   ("TRABAJO",    True),
    "personal":    ("PERSONAL",   False),
    "service":     ("SERVICIOS",  False),
    "newsletter":  ("NEWSLETTER", False),
    "marketing":   ("MARKETING",  False),
    "unknown":     ("CONTACTOS",  False),
    "promotional": ("SPAM",       False),
    "social":      ("SOCIAL",     False),
}

# ── Domain classification sets ────────────────────────────────────────────────
_FINANCIAL_DOMAINS = frozenset([
    "banamex.com", "bbva.com", "bancomer.com", "hsbc.com", "hsbc.com.mx",
    "santander.com.mx", "banorte.com", "scotiabank.com.mx", "inbursa.com",
    "banregio.com", "banbajio.com", "citibanamex.com", "afirme.com",
    "paypal.com", "stripe.com", "mercadopago.com", "clip.mx",
    "americanexpress.com", "visa.com", "mastercard.com",
    "afore.com.mx", "metlife.com.mx", "gnp.com.mx", "axa.com.mx",
    "chubb.com", "zurich.com.mx",
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
    "amazonses.com", "bounce.com", "mktg.com",
])

_FREE_EMAIL_DOMAINS = frozenset([
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com",
    "yahoo.com.mx", "live.com", "live.com.mx", "icloud.com",
    "protonmail.com", "proton.me", "mail.com", "zoho.com",
    "aol.com", "msn.com", "me.com",
])

_GOV_TLDS     = (".gob.mx", ".gov", ".gob", ".mil")
_EDU_TLDS     = (".edu", ".edu.mx", ".ac.mx", ".ac.uk", ".edu.co", ".edu.ar")

# ESP subdomain prefixes that indicate bulk/marketing infrastructure
_ESP_SUBDOMAINS = frozenset([
    "em", "e", "email", "mail", "send", "bulk", "click",
    "bounce", "track", "link", "offers", "deals", "promo",
    "news", "newsletter", "campaign", "mkt",
])

# ── Newsletter / marketing detection ─────────────────────────────────────────
# Email local part — exact match triggers P_NEWSLETTER_LOCAL (-60)
_NEWSLETTER_EXACT_LOCALS = frozenset([
    "newsletter", "newsletters", "news", "noticias", "boletin",
    "offers", "ofertas", "promo", "promotions", "promociones",
    "deals", "marketing", "sale", "sales", "ventas", "descuentos",
    "discount", "coupons", "cupones", "campaign", "campaigns",
    "advertising", "mailer", "digest", "unsubscribe", "subscriptions",
    "novedades", "promoreal", "promos",
])

# Email local part — startswith triggers P_MARKETING_PREFIX (-40)
_MARKETING_PREFIXES = (
    "newsletter", "noticias", "boletin",
    "mailer", "digest", "blast", "bulk", "campaign",
    "donotreply", "no-reply", "noreply",
    "offers", "promo", "deal",
)

# Display name substrings — first match triggers P_MARKETING_NAME (-30)
_MARKETING_NAME_KEYWORDS = (
    "newsletter", "digest", "% off", "% de descuento", "descuento",
    "oferta", "deals", "sale", "subscribe", "unsubscribe",
    "marketing", "savings", "promo",
)

# Local parts that are definitely automated — exclude entirely before scoring
_DEFINITELY_AUTOMATED_LOCALS = frozenset([
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "bounce", "bounces",
])


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SenderStats:
    email:            str
    name:             str
    domain:           str
    count:            int   = 0
    important_count:  int   = 0
    starred_count:    int   = 0
    replied_threads:  set   = field(default_factory=set)
    domain_type:      str   = "unknown"
    score:            float = 0.0
    score_factors:    list  = field(default_factory=list)  # list[tuple[float, str]]

    @property
    def replied(self) -> int:
        return len(self.replied_threads)


@dataclass
class DomainSuggestion:
    domain:       str
    label:        str
    action:       str   # "mark_important" | "archive"
    sender_count: int
    total_msgs:   int
    domain_type:  str


# ── Main class ────────────────────────────────────────────────────────────────

class SmartSetup:
    """Analyzes Gmail history and surfaces important contacts and domains."""

    def __init__(self, service):
        self.service    = service
        self.user_email = self._fetch_user_email()

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(
        self,
        scan_days: int | None = SCAN_DAYS_DEFAULT,
        progress_cb=None,
    ) -> tuple[list[SenderStats], list[DomainSuggestion]]:
        """
        Full scan. Returns (contact_suggestions, domain_suggestions).
        scan_days: look-back window in days; None means all time.
        progress_cb(scanned, phase, page) called after each paginated batch.
        """
        from . import rules as cfg

        sent_threads = self._index_sent_threads(scan_days, progress_cb)
        senders      = self._scan_inbox(sent_threads, scan_days, progress_cb)

        existing_emails  = set(cfg.CONTACT_RULES.keys())
        existing_domains = {
            d
            for rule in cfg.DOMAIN_RULES
            for d in rule.get("domains", [])
        }

        # Score + classify every sender
        for stats in senders.values():
            stats.domain_type = _classify_domain(stats.domain)
            stats.domain_type = _behavioral_reclassify(stats)
            stats.score, stats.score_factors = _score(stats)

        # Contact suggestions: score threshold + exclude clearly non-personal types
        contacts = [
            s for s in senders.values()
            if s.score  >= MIN_SCORE
            and s.count >= MIN_MESSAGES
            and s.email not in existing_emails
            and not _is_definitely_automated(s.email)
            and s.domain_type not in ("promotional", "social", "newsletter", "marketing")
        ]
        contacts.sort(key=lambda s: s.score, reverse=True)
        contacts = contacts[:TOP_N]

        # Domain suggestions: financial / government / educational not in rules yet
        domain_map: dict[str, list[SenderStats]] = {}
        for s in senders.values():
            if s.domain_type in ("financial", "government", "educational"):
                domain_map.setdefault(s.domain, []).append(s)

        domains: list[DomainSuggestion] = []
        for domain, entries in domain_map.items():
            if domain in existing_domains or domain in _FREE_EMAIL_DOMAINS:
                continue
            total  = sum(e.count for e in entries)
            dtype  = entries[0].domain_type
            label, important = DOMAIN_LABELS[dtype]
            action = "mark_important" if important else "archive"
            domains.append(DomainSuggestion(
                domain=domain, label=label, action=action,
                sender_count=len(entries), total_msgs=total, domain_type=dtype,
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

    def _index_sent_threads(
        self, scan_days: int | None, progress_cb=None
    ) -> set[str]:
        """Paginate sent messages to build a set of thread IDs (for reply detection)."""
        thread_ids: set[str] = set()
        date_filter = f" newer_than:{scan_days}d" if scan_days else ""
        query       = f"in:sent{date_filter}"
        page_token  = None
        fetched     = 0
        page        = 0

        while True:
            try:
                result = self.service.users().messages().list(
                    userId="me", q=query,
                    maxResults=500,
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                logger.warning(f"Error al indexar enviados: {e}")
                break

            stubs = result.get("messages", [])
            if not stubs:
                break

            for stub in stubs:
                thread_ids.add(stub.get("threadId", ""))
                fetched += 1

            page += 1
            if progress_cb:
                progress_cb(fetched, phase="sent", page=page)

            page_token = result.get("nextPageToken")
            if not page_token:
                break

            time.sleep(_BATCH_SLEEP)

        logger.debug(f"Sent threads indexados: {len(thread_ids)} en {page} páginas")
        return thread_ids

    def _scan_inbox(
        self,
        sent_threads: set[str],
        scan_days:    int | None,
        progress_cb=None,
    ) -> dict[str, SenderStats]:
        """Single paginated pass through inbox; avoids the deduplication problem
        that the old two-pass approach caused when both passes were uncapped."""
        senders: dict[str, SenderStats] = {}
        date_filter = f" newer_than:{scan_days}d" if scan_days else ""
        self._fetch_and_process(
            query=f"in:inbox -in:sent{date_filter}",
            sent_threads=sent_threads,
            senders=senders,
            progress_cb=progress_cb,
            phase="inbox",
        )
        return senders

    def _fetch_and_process(
        self, query, sent_threads, senders, progress_cb, phase
    ):
        """Paginate a Gmail query, fetch metadata per message, and ingest signals.
        Sleeps _BATCH_SLEEP seconds between list pages to stay within rate limits."""
        page_token = None
        fetched    = 0
        page       = 0

        while True:
            try:
                result = self.service.users().messages().list(
                    userId="me", q=query,
                    maxResults=500,
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                logger.warning(f"Error al listar (fase {phase}): {e}")
                break

            stubs = result.get("messages", [])
            if not stubs:
                break

            for stub in stubs:
                try:
                    msg = self.service.users().messages().get(
                        userId="me", id=stub["id"],
                        format="metadata", metadataHeaders=["From"],
                    ).execute()
                except HttpError:
                    fetched += 1
                    continue
                self._ingest(msg, sent_threads, senders)
                fetched += 1

            page += 1
            if progress_cb:
                progress_cb(fetched, phase=phase, page=page)

            page_token = result.get("nextPageToken")
            if not page_token:
                break

            time.sleep(_BATCH_SLEEP)

        logger.debug(f"Fase '{phase}': {fetched} mensajes en {page} páginas")

    def _ingest(self, message, sent_threads, senders):
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


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(s: SenderStats) -> tuple[float, list[tuple[float, str]]]:
    """
    Returns (total_score, factors).
    factors is a list of (delta, description) for explainability display.
    Positive delta = signal of importance.
    Negative delta = signal of automation / newsletter.
    """
    total:   float                   = 0.0
    factors: list[tuple[float, str]] = []

    def _add(delta: float, desc: str):
        nonlocal total
        if delta == 0:
            return
        total += delta
        factors.append((round(delta, 1), desc))

    # 1. Replies — strongest real-contact signal
    reply_count = min(s.replied, W_REPLY_CAP)
    if reply_count > 0:
        hilos = f"{s.replied} hilo{'s' if s.replied > 1 else ''} respondido{'s' if s.replied > 1 else ''}"
        _add(reply_count * W_REPLY, hilos)

    # 2. Stars — explicit user action, reliable signal
    star_count = min(s.starred_count, W_STARRED_CAP)
    if star_count > 0:
        _add(star_count * W_STARRED,
             f"marcado con estrella (×{star_count})")

    # 3. IMPORTANT — low weight: Gmail auto-marks many newsletters
    imp_count = min(s.important_count, W_IMPORTANT_CAP)
    if imp_count > 0:
        _add(imp_count * W_IMPORTANT,
             f"etiqueta IMPORTANT (×{imp_count}) — señal débil")

    # 4. Frequency
    freq = min(s.count, W_FREQUENCY_CAP)
    if freq > 0:
        _add(freq * W_FREQUENCY,
             f"frecuencia ({s.count} correos recibidos)")

    # 5. Domain type bonus
    domain_bonus = DOMAIN_BONUS.get(s.domain_type, 0)
    if domain_bonus != 0:
        _add(domain_bonus, f"tipo de dominio: {s.domain_type}")

    # 6. One-way communication penalty (newsletters never get replies)
    if s.count >= ONEWAY_THRESHOLD and s.replied == 0:
        _add(ONEWAY_PENALTY,
             f"comunicación unidireccional ({s.count} recibidos, nunca respondido)")
    elif s.count >= 5 and s.replied == 0 and s.domain_type in ("corporate", "unknown"):
        _add(-10, "sin respuestas registradas hacia este remitente")

    # 7. Newsletter/marketing local-part penalty
    local = s.email.split("@")[0].lower()
    if local in _NEWSLETTER_EXACT_LOCALS:
        _add(P_NEWSLETTER_LOCAL,
             f"patrón newsletter en dirección ({local}@...)")
    elif any(local.startswith(p) for p in _MARKETING_PREFIXES):
        _add(P_MARKETING_PREFIX,
             f"prefijo de marketing en dirección ({local}@...)")

    # 8. Marketing display-name penalty (fire once at most)
    name_lower = s.name.lower()
    for kw in _MARKETING_NAME_KEYWORDS:
        if kw in name_lower:
            _add(P_MARKETING_NAME,
                 f"nombre contiene patrón de marketing (\"{kw}\")")
            break

    return round(total, 1), factors


# ── Classification ────────────────────────────────────────────────────────────

def _classify_domain(domain: str) -> str:
    if not domain:
        return "unknown"
    d = domain.lower()

    if d in _FINANCIAL_DOMAINS:   return "financial"
    if d in _SOCIAL_DOMAINS:      return "social"
    if d in _PROMOTIONAL_DOMAINS: return "promotional"

    if any(d.endswith(t) for t in _GOV_TLDS): return "government"
    if any(d.endswith(t) for t in _EDU_TLDS): return "educational"
    if d in _FREE_EMAIL_DOMAINS:              return "personal"

    # ESP subdomain patterns (e.g. em.michaels.com, e.temu.com)
    subdomain = d.split(".")[0]
    if subdomain in _ESP_SUBDOMAINS:
        return "promotional"

    # Marketing keywords embedded in domain name
    _mkt_kw = ("newsletter", "mailer", "campaign", "marketing",
               "promo", "offers", "deals", "email-", "emkt", "bulkmail")
    if any(kw in d for kw in _mkt_kw):
        return "promotional"

    return "corporate"


def _behavioral_reclassify(stats: SenderStats) -> str:
    """
    Overrides the domain-based classification using behavioral signals.
    A 'corporate' sender with 15+ emails and zero replies is almost certainly
    a newsletter or automated marketing account.
    """
    dtype = stats.domain_type

    # Never override authoritative financial/government/educational classifications
    if dtype in ("financial", "government", "educational"):
        return dtype

    local = stats.email.split("@")[0].lower()

    # Exact newsletter local → always newsletter
    if local in _NEWSLETTER_EXACT_LOCALS:
        return "newsletter"

    # High-volume, zero-reply → newsletter (strongest behavioral signal)
    if stats.count >= ONEWAY_THRESHOLD and stats.replied == 0:
        if dtype in ("corporate", "unknown", "personal"):
            return "newsletter"

    # Marketing prefix on corporate domain → marketing
    if any(local.startswith(p) for p in _MARKETING_PREFIXES):
        if dtype in ("corporate", "unknown"):
            return "marketing"

    return dtype


def _is_definitely_automated(email: str) -> bool:
    return email.split("@")[0].lower() in _DEFINITELY_AUTOMATED_LOCALS


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
        return raw.split("<")[0].strip().strip('"').strip("'")
    return ""
