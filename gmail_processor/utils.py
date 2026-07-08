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


def safe_query_term(field: str, value: str) -> str:
    """Builds a quoted Gmail search operator, e.g. safe_query_term("from", addr)
    -> 'from:"addr"'. Quoting keeps `value` as a single literal search term —
    unquoted, a value containing a space (e.g. a malformed/crafted header)
    would be split into separate AND-ed terms and could broaden the query to
    match unrelated messages."""
    return f'{field}:"{value.replace(chr(34), "")}"'


def atomic_write_text(path: str | Path, content: str, encoding: str = "utf-8") -> None:
    """Writes `content` to `path` via a tmp-file + os.replace, so a crash or
    interruption mid-write can never leave `path` truncated/corrupted."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding=encoding)
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_json(path: str | Path, data, **json_kwargs) -> None:
    """Serializes `data` as JSON and writes it atomically via atomic_write_text."""
    json_kwargs.setdefault("ensure_ascii", False)
    json_kwargs.setdefault("indent", 2)
    atomic_write_text(path, json.dumps(data, **json_kwargs))
