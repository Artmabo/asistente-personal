"""
Shared hard-protection check for destructive cleanup operations.

A message matching any of these is never trashed automatically, regardless
of which entry point triggered the check (StorageCleaner's scheduled
cleanup, limpiar_correos.py's manual/CLI cleanup, or any future one).
Centralizing this in one place avoids the protections silently drifting
apart between entry points — limpiar_correos.py used to have no protection
checks at all while cleanup_storage.py did.
"""
from . import rules as cfg


def _build_protected_domains() -> frozenset[str]:
    protected: set[str] = set()
    for rule in cfg.DOMAIN_RULES:
        if rule.get("action") == "mark_important":
            protected.update(rule["domains"])
    return frozenset(protected)


def get_header(message: dict, name: str) -> str:
    for h in message.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def sender_email(message: dict) -> str:
    raw = get_header(message, "From")
    if "<" in raw:
        return raw.split("<")[1].rstrip(">").strip().lower()
    return raw.strip().lower()


def protection_reason(message: dict) -> str | None:
    """Returns a human-readable reason `message` must NOT be trashed, or None
    if it isn't hard-protected. None does not mean "safe to trash" — callers
    may still apply their own scoring/soft-protection on top of this check.
    """
    label_ids = message.get("labelIds", [])

    if "STARRED" in label_ids:
        return "marcado con estrella (STARRED)"
    if "IMPORTANT" in label_ids:
        return "marcado como importante (IMPORTANT)"

    email  = sender_email(message)
    domain = email.split("@")[-1] if "@" in email else ""

    if email in cfg.CONTACT_RULES:
        return f"contacto protegido ({email})"
    if domain and f"@{domain}" in cfg.CONTACT_RULES:
        return f"dominio protegido por contacto ({domain})"
    if domain in _build_protected_domains():
        return f"dominio protegido ({domain})"

    extra = set(cfg.CLEANUP_RULES.get("safe_domains", []))
    if domain in extra:
        return f"dominio seguro adicional ({domain})"

    return None
