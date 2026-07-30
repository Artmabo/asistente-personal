"""
Shared utilities for gmail_processor modules.
"""
import functools
import logging
import os
import random
import time

from googleapiclient.errors import HttpError

logger = logging.getLogger("gmail_processor.utils")

# HTTP statuses worth retrying: 429 (rate limit) and 5xx (transient server errors).
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


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


def extract_domain(email: str) -> str:
    """Extracts the domain from a bare email address, e.g. 'user@example.com' → 'example.com'."""
    return email.rsplit("@", 1)[-1].lower() if email and "@" in email else ""


def with_backoff(max_retries: int = 5, base_delay: float = 1.0):
    """Retries a Gmail API call with exponential backoff + jitter on 429/5xx HttpErrors.

    Other HttpErrors (e.g. 404, 403 permission errors) are not retryable and
    are re-raised immediately.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except HttpError as e:
                    status = int(getattr(e.resp, "status", 0) or 0)
                    if status not in _RETRYABLE_STATUSES or attempt == max_retries:
                        raise
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(
                        f"Gmail API {status} on {func.__name__}, retry {attempt + 1}/{max_retries} in {delay:.1f}s"
                    )
                    time.sleep(delay)
        return wrapper
    return decorator
