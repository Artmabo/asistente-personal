"""
Classifier: inspects a Gmail message and decides its type + action.

Priority order (first match wins):
  1. Contact rules  — specific sender emails (protected contacts)
  2. Keyword rules  — subject / sender contains keywords
  3. Category rules — Gmail auto-categories (CATEGORY_PROMOTIONS, etc.)
  4. Domain rules   — sender domain matches
  5. Default        — unknown, no action
"""
from dataclasses import dataclass, field
from . import rules as cfg
from .utils import get_header, extract_email_address


@dataclass
class Classification:
    email_type: str              # personal | important | spam | promotion | social | unknown
    action: str                  # mark_important | archive | trash | label_only
    labels: list[str] = field(default_factory=list)
    protected: bool = False      # If True, trash action is blocked regardless of rule


class EmailClassifier:
    def classify(self, message: dict) -> Classification:
        """
        Classifies a Gmail message (metadata format).
        `message` must include payload.headers (From, Subject) and labelIds.
        """
        headers  = message.get("payload", {}).get("headers", [])
        label_ids = message.get("labelIds", [])

        sender  = extract_email_address(get_header(headers, "From"))
        domain  = sender.split("@")[-1] if "@" in sender else ""
        subject = get_header(headers, "Subject")
        search_text = f"{sender} {subject}"

        # 1. Contact rules (highest priority — always protected)
        # Supports exact email matches AND domain-prefix entries like "@anahuac.mx"
        # (subdomain-aware: "@anahuac.mx" also protects "alerts@e.anahuac.mx")
        contact_key = sender if sender in cfg.CONTACT_RULES else _match_domain_key(
            domain, cfg.CONTACT_RULES
        )
        if contact_key:
            rule = cfg.CONTACT_RULES[contact_key]
            action = "mark_important" if rule.get("mark_important") else "label_only"
            return Classification(
                email_type="personal",
                action=action,
                labels=[rule["label"]] if rule.get("label") else [],
                protected=True,
            )

        # 2. Keyword rules
        # A "trash" keyword match (e.g. generic marketing terms like "oferta
        # exclusiva") must never override hard domain protection — otherwise a
        # promotional email from a protected bank domain gets trashed before
        # DOMAIN_RULES (priority 4) ever gets a chance to protect it.
        protected_domains = _protected_domains()
        for rule in cfg.KEYWORD_RULES:
            if rule["action"] == "trash" and _domain_matches_any(domain, protected_domains):
                continue
            if _matches_any(search_text, rule["keywords"], rule.get("case_sensitive", False)):
                return Classification(
                    email_type="spam" if rule["action"] == "trash" else "important",
                    action=rule["action"],
                    labels=[rule["label"]] if rule.get("label") else [],
                    protected=False,
                )

        # 3. Gmail category labels
        for category, rule in cfg.CATEGORY_RULES.items():
            if category in label_ids:
                return Classification(
                    email_type=category.replace("CATEGORY_", "").lower(),
                    action=rule["action"],
                    labels=[rule["label"]] if rule.get("label") else [],
                    protected=False,
                )

        # 4. Domain rules (subdomain-aware)
        for rule in cfg.DOMAIN_RULES:
            if _domain_matches_any(domain, rule["domains"]):
                return Classification(
                    email_type="important",
                    action=rule["action"],
                    labels=[rule["label"]] if rule.get("label") else [],
                    protected=rule["action"] == "mark_important",
                )

        # 5. Default
        return Classification(email_type="unknown", action="label_only", protected=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _matches_any(text: str, keywords: list[str], case_sensitive: bool) -> bool:
    haystack = text if case_sensitive else text.lower()
    return any((kw if case_sensitive else kw.lower()) in haystack for kw in keywords)


def _protected_domains() -> frozenset[str]:
    """Domains hard-protected via a DOMAIN_RULES `mark_important` entry."""
    protected: set[str] = set()
    for rule in cfg.DOMAIN_RULES:
        if rule.get("action") == "mark_important":
            protected.update(rule["domains"])
    return frozenset(protected)


def _domain_matches(domain: str, candidate: str) -> bool:
    """True if `domain` equals `candidate` or is one of its subdomains."""
    return bool(domain) and (domain == candidate or domain.endswith(f".{candidate}"))


def _domain_matches_any(domain: str, candidates) -> bool:
    return any(_domain_matches(domain, c) for c in candidates)


def _match_domain_key(domain: str, contact_rules: dict) -> str | None:
    """Finds a "@domain" CONTACT_RULES key matching `domain` or one of its subdomains."""
    if not domain:
        return None
    for key in contact_rules:
        if key.startswith("@") and _domain_matches(domain, key[1:]):
            return key
    return None
