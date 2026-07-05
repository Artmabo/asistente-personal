"""
Shared utilities for gmail_processor modules.
"""
import os
import re

_dotenv_loaded = False


def get_api_key() -> str | None:
    """Returns the Anthropic API key from environment (loads .env if present)."""
    global _dotenv_loaded
    if not _dotenv_loaded:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        _dotenv_loaded = True
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
    """Extracts the display name portion from a raw From/To header value.

    '"User <nickname>" <user@example.com>' → 'User <nickname>'
    'user@example.com' (no display name) → ''
    """
    if not raw or "<" not in raw:
        return ""
    start = raw.rfind("<")
    return raw[:start].strip().strip('"').strip("'")


_EMAIL_RE = re.compile(r"^[^@\s\"'\\]+@[^@\s\"'\\]+\.[^@\s\"'\\]+$")
_DOMAIN_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def is_valid_email(addr: str) -> bool:
    """Strict check that `addr` is a plain email address with no quoting/
    control characters — used to validate values before they are spliced
    into rules.py source, which is later importlib.reload()ed as code."""
    return bool(addr) and bool(_EMAIL_RE.match(addr))


def is_valid_domain(domain: str) -> bool:
    """Strict check that `domain` looks like a bare DNS domain name — same
    purpose as is_valid_email(): gates values before they reach rules.py."""
    return bool(domain) and bool(_DOMAIN_RE.match(domain))
