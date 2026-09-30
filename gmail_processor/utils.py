"""
Shared utilities for gmail_processor modules.
"""
import logging
import os

from googleapiclient.errors import HttpError

logger = logging.getLogger("gmail_processor.utils")

METADATA_HEADERS = ["From", "Subject", "Date", "List-Unsubscribe"]
_BATCH_SIZE = 50   # Gmail allows up to 100 calls per batch; 50 keeps quota bursts small


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


def fetch_metadata_batch(service, msg_ids: list[str]) -> dict[str, dict | None]:
    """Fetches message metadata for many IDs using batched HTTP requests.

    Replaces one sequential HTTP round-trip per message with one per
    `_BATCH_SIZE` messages. Returns {msg_id: message | None}; None marks
    a message that could not be fetched (deleted, rate-limited, ...).
    """
    results: dict[str, dict | None] = {mid: None for mid in msg_ids}

    def _on_response(request_id, response, exception):
        if exception is None and response is not None:
            results[request_id] = response
        else:
            logger.debug(f"Batch fetch failed for {request_id}: {exception}")

    for i in range(0, len(msg_ids), _BATCH_SIZE):
        chunk = msg_ids[i : i + _BATCH_SIZE]
        batch = service.new_batch_http_request(callback=_on_response)
        for mid in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me", id=mid, format="metadata",
                    metadataHeaders=METADATA_HEADERS,
                ),
                request_id=mid,
            )
        try:
            batch.execute()
        except HttpError as e:
            logger.error(f"Batch metadata request failed: {e}")
    return results
