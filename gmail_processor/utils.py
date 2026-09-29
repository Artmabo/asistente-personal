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


def domain_matches(domain: str, candidates) -> bool:
    """True if `domain` equals a candidate or is a subdomain of one.

    e.g. 'info.cibc.com' matches 'cibc.com'; 'evilcibc.com' does not.
    """
    if not domain:
        return False
    return any(domain == c or domain.endswith("." + c) for c in candidates)


def find_contact_key(sender: str, contact_rules) -> str | None:
    """Returns the CONTACT_RULES key covering `sender`, or None.

    Matches the exact address, then '@domain' entries (subdomains included).
    """
    if sender in contact_rules:
        return sender
    domain = sender.split("@")[-1] if "@" in sender else ""
    if not domain:
        return None
    parts = domain.split(".")
    for i in range(len(parts) - 1):          # never match a bare TLD
        key = "@" + ".".join(parts[i:])
        if key in contact_rules:
            return key
    return None
