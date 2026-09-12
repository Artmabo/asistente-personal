"""
Shared utilities for gmail_processor modules.
"""
import json
import logging
import os
import time

from googleapiclient.errors import HttpError

_PERMISSION_REASONS = {"insufficientPermissions", "authError"}


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


FREE_EMAIL_PROVIDERS = frozenset([
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.mx",
    "live.com", "live.com.mx", "icloud.com", "protonmail.com", "proton.me",
    "me.com", "aol.com", "msn.com",
])


def derive_label(email: str, name: str) -> str:
    """Derives a short, uppercase Gmail label for a contact: their first name
    if given, otherwise the local-part (for free providers) or domain."""
    words = name.strip().split() if name else []
    if words:
        clean = "".join(c for c in words[0] if c.isalpha())[:10]
        if clean:
            return clean.upper()
    domain = email.split("@")[-1] if "@" in email else ""
    local  = email.split("@")[0]  if "@" in email else email
    if domain in FREE_EMAIL_PROVIDERS:
        clean = "".join(c for c in local if c.isalpha())[:10]
        if clean:
            return clean.upper()
    if domain:
        part  = domain.split(".")[0]
        clean = "".join(c for c in part if c.isalpha())[:8]
        if clean:
            return clean.upper()
    return "CONTACTO"


def is_permission_error(exc: HttpError) -> bool:
    """Returns True when a 403 HttpError signals missing OAuth scopes, not a quota hit."""
    try:
        body = json.loads(exc.content)
        reasons = {
            err.get("reason", "")
            for err in body.get("error", {}).get("errors", [])
        }
        return bool(reasons & _PERMISSION_REASONS)
    except Exception:
        return "insufficient" in str(exc).lower()


def call_with_backoff(method, *, max_retries: int = 3, base_delay: float = 1.0,
                       logger: logging.Logger | None = None, **kwargs):
    """Executes a Gmail API request (e.g. `service.users().messages().list`) with
    exponential-backoff retry on rate-limit (403/429) or transient (500/503) errors.

    Raises immediately on a 403 that signals missing OAuth scopes rather than a
    quota hit, since retrying that would never succeed. Returns the executed
    response, or None once retries are exhausted.
    """
    delay = base_delay
    for attempt in range(1, max_retries + 1):
        try:
            return method(**kwargs).execute()
        except HttpError as e:
            status = int(e.resp.status)
            if status == 403 and is_permission_error(e):
                if logger:
                    logger.error(f"Insufficient permissions: {e}")
                raise
            if status in (403, 429, 500, 503) and attempt < max_retries:
                if logger:
                    kind = "Rate limit" if status in (403, 429) else "Server error"
                    logger.warning(f"{kind} ({status}), retry {attempt}/{max_retries} in {delay:.1f}s")
                time.sleep(delay)
                delay *= 2
                continue
            if logger:
                logger.error(f"API error {status} on attempt {attempt}: {e}")
            return None
    return None
