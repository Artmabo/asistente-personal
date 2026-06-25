"""
Shared utilities for gmail_processor modules.
"""
import email.utils
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

    Uses email.utils.getaddresses for RFC 5322 compliance, handling edge cases
    like quoted names and multiple angle-bracket groups that naive splitting misses.
    """
    if not raw:
        return ""
    pairs = email.utils.getaddresses([raw])
    if pairs:
        _, addr = pairs[0]
        return addr.strip().lower()
    return raw.strip().lower()
