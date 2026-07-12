"""
Shared utilities for gmail_processor modules.
"""
import json
import logging
import os
import time

from googleapiclient.errors import HttpError

_MAX_RETRIES = 3
_BASE_DELAY  = 1.0   # seconds before first retry (doubles each attempt)

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


def is_permission_error(exc: HttpError) -> bool:
    """Returns True when a 403 signals missing OAuth scopes, not a quota hit."""
    try:
        body = json.loads(exc.content)
        reasons = {
            err.get("reason", "")
            for err in body.get("error", {}).get("errors", [])
        }
        return bool(reasons & _PERMISSION_REASONS)
    except Exception:
        return "insufficient" in str(exc).lower()


def call_with_retry(
    method,
    *,
    logger: logging.Logger | None = None,
    max_retries: int = _MAX_RETRIES,
    base_delay: float = _BASE_DELAY,
    **kwargs,
):
    """Executes a Gmail API call with exponential-backoff retry on rate limits.

    `method` is an unbound API method (e.g. `service.users().messages().list`);
    `kwargs` are passed to it before `.execute()`. Returns None if all retries
    are exhausted; re-raises immediately on a hard permission failure (missing
    OAuth scope), since retrying that can't succeed.
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
