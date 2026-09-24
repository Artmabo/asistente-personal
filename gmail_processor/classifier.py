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
from .utils import get_header, extract_email_address, extract_domain


@dataclass
class Classification:
    """Result of classifying one email: what it is, what to do, and how."""
    email_type: str              # personal | important | spam | promotion | social | unknown
    action: str                  # mark_important | archive | trash | label_only
    labels: list[str] = field(default_factory=list)
    protected: bool = False      # If True, trash action is blocked regardless of rule


class EmailClassifier:
    """Applies CONTACT/KEYWORD/CATEGORY/DOMAIN rules (in that priority order) to a message."""

    def __init__(self):
        # Precompute the lowercased keyword lists once at construction time instead
        # of re-lowering the same static keywords on every classify() call — this
        # runs once per program run, not once per message in the hot path.
        self._keyword_rules = [
            {
                **rule,
                "_keywords_norm": tuple(
                    kw if rule.get("case_sensitive", False) else kw.lower()
                    for kw in rule["keywords"]
                ),
            }
            for rule in cfg.KEYWORD_RULES
        ]

    def classify(self, message: dict) -> Classification:
        """
        Classifies a Gmail message (metadata format).
        `message` must include payload.headers (From, Subject) and labelIds.
        """
        headers  = message.get("payload", {}).get("headers", [])
        label_ids = message.get("labelIds", [])

        sender  = extract_email_address(get_header(headers, "From"))
        domain  = extract_domain(sender)
        subject = get_header(headers, "Subject")
        search_text = f"{sender} {subject}"

        # 1. Contact rules (highest priority — always protected)
        # Supports exact email matches AND domain-prefix entries like "@anahuac.mx"
        contact_key = sender if sender in cfg.CONTACT_RULES else (
            f"@{domain}" if domain and f"@{domain}" in cfg.CONTACT_RULES else None
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
        for rule in self._keyword_rules:
            if _matches_any(search_text, rule["_keywords_norm"], rule.get("case_sensitive", False)):
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

def _matches_any(text: str, keywords, case_sensitive: bool) -> bool:
    """Returns True if any (already-normalized) keyword is a substring of `text`."""
    haystack = text if case_sensitive else text.lower()
    return any(kw in haystack for kw in keywords)
