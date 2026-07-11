"""
Shared utilities for gmail_processor modules.
"""
import os
import re

_EMAIL_RE  = re.compile(r"^[^@\s\"'\\]+@[^@\s\"'\\]+\.[^@\s\"'\\]+$")
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$")

_FREE_EMAIL_PROVIDERS = frozenset([
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.mx",
    "live.com", "live.com.mx", "icloud.com", "protonmail.com", "proton.me",
    "me.com", "aol.com", "msn.com",
])


def is_valid_email(email: str) -> bool:
    """True if `email` looks like a bare address safe to embed in generated
    Python source (no quotes/backslashes/whitespace that could break out of
    a string literal or corrupt rules.py when written + reloaded)."""
    return bool(email) and bool(_EMAIL_RE.match(email))


def is_valid_domain(domain: str) -> bool:
    """True if `domain` looks like a bare hostname (letters, digits, dots,
    hyphens only) safe to embed in generated Python source."""
    return bool(domain) and bool(_DOMAIN_RE.match(domain))


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


def derive_contact_label(email: str, name: str) -> str:
    """Derives a short uppercase label for a contact from their display name
    (falls back to the local part or domain of the email address)."""
    if name:
        words = name.strip().split()
        if words:
            clean = "".join(c for c in words[0] if c.isalpha())[:10]
            if clean:
                return clean.upper()
    domain = email.split("@")[-1] if "@" in email else ""
    local  = email.split("@")[0]  if "@" in email else email
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
