"""
Shared utilities for gmail_processor modules.
"""
import os
import re
from pathlib import Path

# Conservative allowlist for text spliced into rules.py source (contact
# emails, domains, labels). Several call sites string-interpolate this kind
# of value — sometimes derived from Gmail headers, i.e. attacker-influenced —
# directly into rules.py and then importlib.reload() it. Rejecting anything
# outside this set (quotes, backslashes, braces, newlines) up front is safer
# than trying to escape it correctly at every call site.
_SAFE_RULE_VALUE_RE = re.compile(r"^[\w .@-]{1,80}$", re.UNICODE)


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


def is_safe_rule_value(value: str) -> bool:
    """Returns True if `value` is safe to splice into rules.py source as a string literal.

    Allows letters (incl. accented), digits, spaces, '.', '@', '-', '_' — enough
    for emails, domains and Gmail labels — and rejects everything else,
    notably quotes, backslashes, braces and newlines that could break out of
    the literal or corrupt the file.
    """
    return isinstance(value, str) and bool(_SAFE_RULE_VALUE_RE.match(value))


def backup_rules_file(rules_path: str | Path) -> None:
    """Writes a single-generation backup of rules.py alongside it, best-effort."""
    rules_path = Path(rules_path)
    if not rules_path.exists():
        return
    try:
        backup_path = rules_path.with_suffix(rules_path.suffix + ".bak")
        backup_path.write_text(rules_path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        pass
