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

# KEYWORD_RULES keyword lists are static; lower-casing them once at import time
# avoids re-lowering the same keywords for every message classified.
_LOWERED_KEYWORD_RULES = [
    {
        **rule,
        "_keywords_lower": [kw if rule.get("case_sensitive", False) else kw.lower()
                             for kw in rule["keywords"]],
    }
    for rule in cfg.KEYWORD_RULES
]


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
        # Supports exact email matches AND domain entries like "@anahuac.mx",
        # which also match subdomains (e.g. sub.anahuac.mx).
        contact_key = sender if sender in cfg.CONTACT_RULES else _match_domain_rule(domain)
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
        search_text_lower = search_text.lower()
        for rule in _LOWERED_KEYWORD_RULES:
            haystack = search_text if rule.get("case_sensitive", False) else search_text_lower
            if any(kw in haystack for kw in rule["_keywords_lower"]):
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

        # 4. Domain rules
        for rule in cfg.DOMAIN_RULES:
            if domain in rule["domains"]:
                return Classification(
                    email_type="important",
                    action=rule["action"],
                    labels=[rule["label"]] if rule.get("label") else [],
                    protected=rule["action"] == "mark_important",
                )

        # 5. Default
        return Classification(email_type="unknown", action="label_only", protected=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _match_domain_rule(domain: str) -> str | None:
    """Finds a CONTACT_RULES "@domain" key matching `domain` or one of its subdomains."""
    if not domain:
        return None
    for key in cfg.CONTACT_RULES:
        if not key.startswith("@"):
            continue
        rule_domain = key[1:]
        if domain == rule_domain or domain.endswith("." + rule_domain):
            return key
    return None
