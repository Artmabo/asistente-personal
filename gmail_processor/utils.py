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


def gmail_address_query(operator: str, email: str) -> str:
    """Builds a safe `<operator>:"..."` Gmail search operand for an email address.

    Quotes the address and strips characters that could let it break out of
    the quoted operand and inject additional search terms/operators.
    """
    safe = email.replace('"', "").replace("\n", "").replace("\r", "").strip()
    return f'{operator}:"{safe}"'


def gmail_from_query(email: str) -> str:
    """Builds a safe `from:"..."` Gmail search operand for an email address."""
    return gmail_address_query("from", email)
