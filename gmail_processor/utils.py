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
    return raw.strip().lower()


def find_contact_rule_key(sender: str, domain: str, contact_rules: dict) -> str | None:
    """Finds the CONTACT_RULES key protecting `sender`/`domain`, or None.

    Matches, in priority order:
      1. Exact sender email (e.g. "user@example.com")
      2. Exact domain entry (e.g. "@example.com")
      3. A protected parent domain when `domain` is one of its subdomains
         (e.g. "profesor@alumnos.anahuac.mx" is matched by "@anahuac.mx")
    """
    if sender in contact_rules:
        return sender
    if not domain:
        return None
    exact = f"@{domain}"
    if exact in contact_rules:
        return exact
    for key in contact_rules:
        if key.startswith("@") and domain.endswith("." + key[1:]):
            return key
    return None
