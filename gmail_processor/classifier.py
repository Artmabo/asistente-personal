"""
Classifier: inspects a Gmail message and decides its type + action.

Priority order (first match wins):
  1. Contact rules        — specific sender emails (protected contacts)
  2. Protected domain rules — DOMAIN_RULES entries with action="mark_important"
  3. Keyword rules        — subject / sender contains keywords
  4. Category rules       — Gmail auto-categories (CATEGORY_PROMOTIONS, etc.)
  5. Remaining domain rules — other DOMAIN_RULES entries (e.g. action="archive")
  6. Default              — unknown, no action

Protected domain rules run before keyword/category rules so that, e.g., a
promotional email from a bank domain in DOMAIN_RULES isn't trashed by a
SPAM keyword match before its domain protection is ever consulted.
"""
from dataclasses import dataclass, field
from . import rules as cfg
from .utils import extract_email_address, get_header


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

        # 2. Protected domain rules (mark_important) — checked before keyword/category
        # rules so a protected domain (bank, government, ...) can't be trashed/archived
        # by an unrelated keyword or Gmail auto-category match.
        for rule in cfg.DOMAIN_RULES:
            if rule["action"] == "mark_important" and domain in rule["domains"]:
                return Classification(
                    email_type="important",
                    action=rule["action"],
                    labels=[rule["label"]] if rule.get("label") else [],
                    protected=True,
                )

        # 3. Keyword rules
        for rule in cfg.KEYWORD_RULES:
            if _matches_any(search_text, rule["keywords"], rule.get("case_sensitive", False)):
                return Classification(
                    email_type="spam" if rule["action"] == "trash" else "important",
                    action=rule["action"],
                    labels=[rule["label"]] if rule.get("label") else [],
                    protected=False,
                )

        # 4. Gmail category labels
        for category, rule in cfg.CATEGORY_RULES.items():
            if category in label_ids:
                return Classification(
                    email_type=category.replace("CATEGORY_", "").lower(),
                    action=rule["action"],
                    labels=[rule["label"]] if rule.get("label") else [],
                    protected=False,
                )

        # 5. Remaining domain rules (e.g. action="archive")
        for rule in cfg.DOMAIN_RULES:
            if domain in rule["domains"]:
                return Classification(
                    email_type="important",
                    action=rule["action"],
                    labels=[rule["label"]] if rule.get("label") else [],
                    protected=False,
                )

        # 6. Default
        return Classification(email_type="unknown", action="label_only", protected=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _matches_any(text: str, keywords: list[str], case_sensitive: bool) -> bool:
    haystack = text if case_sensitive else text.lower()
    return any((kw if case_sensitive else kw.lower()) in haystack for kw in keywords)
