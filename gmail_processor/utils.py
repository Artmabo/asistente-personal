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


def secure_chmod(path) -> None:
    """Restricts a persisted state file (chat history, contact profiles, audit
    log, etc.) to owner-only read/write, since these files hold plaintext PII
    — email addresses, subjects, AI-generated summaries of correspondence.
    Best-effort: silently no-ops on platforms/filesystems that don't support it.
    """
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def mask_email(address: str) -> str:
    """Masks the local part of an email for safe logging, e.g. 'jd***@example.com'.

    Keeps the domain (useful for scanning logs by sender domain) while avoiding
    persisting a full correspondent address in plaintext log files.
    """
    if not address or "@" not in address:
        return address
    local, _, domain = address.partition("@")
    visible = local[:2]
    return f"{visible}***@{domain}"


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
