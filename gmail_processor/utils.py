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


def extract_display_name(raw: str) -> str:
    """Extracts the display name from a raw From/To header value.

    Uses rfind (mirroring extract_email_address) so a display name that
    itself contains angle brackets isn't truncated early, e.g.:
    '"Bob <VIP>" <bob@example.com>' → 'Bob <VIP>' (not just 'Bob ').
    """
    if not raw:
        return ""
    if "<" not in raw:
        return raw.strip()
    return raw[: raw.rfind("<")].strip().strip('"').strip("'")


def get_protection_reason(email_addr: str, domain: str, label_ids: list[str]) -> str | None:
    """Returns a human-readable reason if a sender/message must never be trashed,
    or None if it's safe to clean up.

    Mirrors gmail_processor.rules: an exact CONTACT_RULES email, a CONTACT_RULES
    "@domain" wildcard, a DOMAIN_RULES entry with action "mark_important", or a
    STARRED/IMPORTANT label. This is the same "hard protection" check
    cleanup_storage.StorageCleaner applies before trashing anything — any other
    code path that moves messages to trash (e.g. limpiar_correos.limpiar_bandeja)
    should run it too, so "protect this sender" actually holds everywhere.
    """
    from . import rules as cfg

    if "STARRED" in label_ids:
        return "marcado con estrella (STARRED)"
    if "IMPORTANT" in label_ids:
        return "marcado como importante (IMPORTANT)"
    if email_addr in cfg.CONTACT_RULES:
        return f"contacto protegido ({email_addr})"
    if domain and f"@{domain}" in cfg.CONTACT_RULES:
        return f"dominio protegido por contacto ({domain})"
    protected_domains = {
        d
        for rule in cfg.DOMAIN_RULES
        if rule.get("action") == "mark_important"
        for d in rule.get("domains", [])
    }
    if domain in protected_domains:
        return f"dominio protegido ({domain})"
    if domain in set(cfg.CLEANUP_RULES.get("safe_domains", [])):
        return f"dominio seguro adicional ({domain})"
    return None


def batch_get_messages(
    service,
    msg_ids: list[str],
    *,
    format: str = "metadata",
    metadata_headers: list[str] | None = None,
    chunk_size: int = 90,
) -> dict[str, dict]:
    """Fetches multiple Gmail messages via the batch HTTP API.

    Replaces a sequential get() call per message with a handful of batched
    HTTP requests (chunked to stay under Gmail's ~100-request batch cap).
    Returns {msg_id: message_dict} — ids that failed or errored are omitted,
    mirroring the try/except-continue behavior of a sequential fetch loop.
    """
    results: dict[str, dict] = {}
    if not msg_ids:
        return results

    def _on_response(request_id, response, exception):
        if exception is None and response is not None:
            results[request_id] = response

    for i in range(0, len(msg_ids), chunk_size):
        chunk = msg_ids[i : i + chunk_size]
        batch = service.new_batch_http_request(callback=_on_response)
        for mid in chunk:
            kwargs = {"userId": "me", "id": mid, "format": format}
            if metadata_headers:
                kwargs["metadataHeaders"] = metadata_headers
            batch.add(service.users().messages().get(**kwargs), request_id=mid)
        try:
            batch.execute()
        except Exception:
            pass  # partial/total batch failure — ids simply stay absent from results

    return results
