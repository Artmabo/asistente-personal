"""
Shared utilities for gmail_processor modules.
"""
import json
import os
from pathlib import Path


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
    """Extracts the display name from a raw From header value, e.g.:
    '"Jane Doe" <jane@example.com>' → 'Jane Doe'. Returns "" if there is
    no bracketed address (the whole value is then just an address).

    Unlike extract_email_address, splitting on the *first* "<" here is
    correct even if the address itself contains further angle brackets,
    since the display name always precedes them.
    """
    if not raw or "<" not in raw:
        return ""
    return raw.split("<")[0].strip().strip('"').strip("'")


def read_json_file(path: str | Path, default=None):
    """Reads and parses a JSON file, returning `default` if it doesn't
    exist or fails to parse/read. Centralizes the read-json-or-default
    pattern used throughout gmail_processor for local state files."""
    if default is None:
        default = {}
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default
