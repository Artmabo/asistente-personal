"""
Shared utilities for gmail_processor modules.
"""
import os


def get_api_key() -> str | None:
    """Returns the Anthropic API key from environment (loads .env if present)."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return os.getenv("ANTHROPIC_API_KEY")


def get_header(headers: list[dict], name: str) -> str:
    """Returns the value of the first header matching `name` (case-insensitive)."""
    name_lower = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""


def extract_email_address(raw: str) -> str:
    """Extracts a bare email address from a raw From/To header value.

    Uses rfind to handle display names that contain angle brackets, e.g.:
    '"User <nickname>" <user@example.com>' → 'user@example.com'
    """
    if not raw:
        return ""
    if "<" in raw:
        start = raw.rfind("<")
        end   = raw.find(">", start)
        if end > start:
            return raw[start + 1 : end].strip().lower()
        return ""  # Unmatched '<' — malformed header, not a usable address
    return raw.strip().lower()


def build_protected_domains(domain_rules: list[dict]) -> frozenset[str]:
    """Returns sender domains that DOMAIN_RULES marks as `mark_important`.

    Shared by every module that must never trash mail from these domains
    (StorageCleaner, the quick-cleanup script, the classifier).
    """
    protected: set[str] = set()
    for rule in domain_rules:
        if rule.get("action") == "mark_important":
            protected.update(rule["domains"])
    return frozenset(protected)


def protection_reason(
    email: str,
    domain: str,
    label_ids: list[str],
    contact_rules: dict,
    protected_domains: frozenset[str],
    safe_domains: frozenset[str] = frozenset(),
) -> str | None:
    """Returns a human-readable reason `email` must never be trashed, or None.

    Single source of truth for "hard protection" so every trash/cleanup path
    (StorageCleaner, limpiar_correos.py, cli_menu quick actions) agrees on
    which messages are off-limits — regardless of which Gmail category or
    query surfaced them.
    """
    if "STARRED" in label_ids:
        return "marcado con estrella (STARRED)"
    if "IMPORTANT" in label_ids:
        return "marcado como importante (IMPORTANT)"
    if email in contact_rules:
        return f"contacto protegido ({email})"
    if domain and f"@{domain}" in contact_rules:
        return f"dominio protegido por contacto ({domain})"
    if domain in protected_domains:
        return f"dominio protegido ({domain})"
    if domain in safe_domains:
        return f"dominio seguro adicional ({domain})"
    return None
