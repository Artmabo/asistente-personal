"""
Shared utilities for gmail_processor modules.
"""
import os

# Free/consumer email providers — used to decide whether a suggested Gmail
# label should be derived from the sender's display name (personal account)
# or from their domain (everything else). Shared by contact_analyzer.py and
# app.py so both derive the exact same label for a given address.
FREE_EMAIL_PROVIDERS = frozenset([
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.mx",
    "live.com", "live.com.mx", "icloud.com", "protonmail.com", "proton.me",
    "me.com", "aol.com", "msn.com",
])


def derive_label(email_addr: str, name: str) -> str:
    """Derives a short, uppercase Gmail label suggestion for a contact.

    Prefers the contact's first name; falls back to the local part of the
    address for free-provider accounts, then to the domain name, then to a
    generic placeholder.
    """
    if name:
        word  = name.strip().split()[0] if name.strip() else ""
        clean = "".join(c for c in word if c.isalpha())[:10]
        if clean:
            return clean.upper()

    domain = email_addr.split("@")[-1] if "@" in email_addr else ""
    local  = email_addr.split("@")[0]  if "@" in email_addr else email_addr

    if domain in FREE_EMAIL_PROVIDERS:
        clean = "".join(c for c in local if c.isalpha())[:10]
        if clean:
            return clean.upper()

    if domain:
        part  = domain.split(".")[0]
        clean = "".join(c for c in part if c.isalpha())[:8]
        if clean:
            return clean.upper()

    return "CONTACTO"


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
