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


def extract_display_name(raw: str) -> str:
    """Extracts the display name portion from a raw From header value.

    Uses the first '<' as the split point (the display name always precedes
    the address), e.g.: '"Jane Doe" <jane@example.com>' → 'Jane Doe'
    """
    if not raw or "<" not in raw:
        return ""
    return raw.split("<")[0].strip().strip('"').strip("'")


_FREE_EMAIL_PROVIDERS = frozenset([
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.mx",
    "live.com", "live.com.mx", "icloud.com", "protonmail.com", "proton.me",
    "me.com", "aol.com", "msn.com",
])


def derive_contact_label(email_addr: str, name: str) -> str:
    """Derives a short, all-caps Gmail label from a contact's name or address.

    Prefers the first word of `name` (letters only, max 10 chars). Falls back
    to the local-part for free email providers, then the domain, then a
    generic "CONTACTO" label.
    """
    words = (name or "").strip().split()
    if words:
        clean = "".join(c for c in words[0] if c.isalpha())[:10]
        if clean:
            return clean.upper()
    domain = email_addr.split("@")[-1] if "@" in email_addr else ""
    local  = email_addr.split("@")[0]  if "@" in email_addr else email_addr
    if domain in _FREE_EMAIL_PROVIDERS:
        clean = "".join(c for c in local if c.isalpha())[:10]
        if clean:
            return clean.upper()
    if domain:
        part  = domain.split(".")[0]
        clean = "".join(c for c in part if c.isalpha())[:8]
        if clean:
            return clean.upper()
    return "CONTACTO"
