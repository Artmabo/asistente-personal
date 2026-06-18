"""
Shared utilities for gmail_processor modules.
"""
import json
import os
from pathlib import Path


def atomic_write_json(path: Path, data, **kwargs) -> None:
    """Writes JSON to `path` atomically via a temp file + rename.

    Prevents corrupted state files if the process is interrupted mid-write.
    Extra kwargs are forwarded to json.dumps (e.g. indent=2, ensure_ascii=False).
    """
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, **kwargs), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


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
    """Extracts a bare email address from a raw From/To header value."""
    if "<" in raw:
        return raw.split("<")[1].rstrip(">").strip().lower()
    return raw.strip().lower()
