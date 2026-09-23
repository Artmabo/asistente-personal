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


def extract_domain(raw: str) -> str:
    """Extracts the lowercase domain from a raw From/To header value or bare address."""
    address = extract_email_address(raw)
    return address.split("@")[-1] if "@" in address else address


def extract_display_name(raw: str) -> str:
    """Extracts the display name portion of a raw From/To header value, if any.

    '"Jane Doe" <jane@example.com>' → 'Jane Doe'
    'jane@example.com' → ''
    """
    if not raw:
        return ""
    if "<" in raw:
        start = raw.rfind("<")
        return raw[:start].strip().strip('"').strip("'")
    return ""


def escape_py_str(value: str) -> str:
    """Escapes a string for safe embedding inside a double-quoted Python literal.

    Used when generating source lines (e.g. rules.py entries) from user input,
    so values containing quotes or backslashes don't produce invalid/broken syntax.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')
