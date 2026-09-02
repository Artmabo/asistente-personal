"""
Shared utilities for gmail_processor modules.
"""
import os
import re


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
    """Extracts the display name from a raw From/To header value.

    Uses rfind (matching extract_email_address) so a display name that
    itself contains '<'/'>' doesn't get truncated, e.g.:
    '"Smith <VIP> John" <john@example.com>' → 'Smith <VIP> John'
    """
    if not raw or "<" not in raw:
        return ""
    end = raw.rfind("<")
    return raw[:end].strip().strip('"').strip("'")


def gmail_query_atom(value: str) -> str:
    """Quotes a value for safe interpolation into a Gmail search query
    (e.g. f"from:{gmail_query_atom(addr)}"), so header-derived text can't
    inject Gmail search operators (OR, to:, newer_than:, etc.)."""
    return '"' + value.replace('"', "") + '"'


def get_domain(email: str) -> str:
    """Returns the domain part of an email address, or '' if there is none."""
    return email.split("@")[-1] if email and "@" in email else ""


_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_for_log(text: str) -> str:
    """Strips control/escape characters from untrusted text (e.g. email
    headers) before it is written to logs or a terminal, preventing log
    forging and terminal escape-sequence injection."""
    if not text:
        return text
    return _CONTROL_CHARS_RE.sub(" ", text)
