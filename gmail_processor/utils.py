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


def parse_from_header(raw: str) -> tuple[str, str]:
    """Parses a raw From/To header value into (email_address, display_name).

    Delegates to the stdlib's RFC 2822 parser (email.utils.parseaddr) instead of
    hand-rolled bracket splitting, so quoted display names that themselves
    contain '<'/'>' (e.g. '"User <nickname>" <user@example.com>') are parsed
    correctly.
    """
    if not raw:
        return "", ""
    name, addr = email.utils.parseaddr(raw)
    return addr.strip().lower(), name.strip().strip('"').strip("'")


def extract_email_address(raw: str) -> str:
    """Extracts a bare email address from a raw From/To header value."""
    return parse_from_header(raw)[0]
