"""
Shared utilities for gmail_processor modules.
"""
import os
from pathlib import Path

# Free/consumer email providers — shared by contact_analyzer (scoring signal)
# and the contact-labeling helpers below (label derivation).
FREE_EMAIL_PROVIDERS = frozenset([
    "gmail.com", "hotmail.com", "outlook.com", "yahoo.com", "yahoo.com.mx",
    "live.com", "live.com.mx", "icloud.com", "protonmail.com", "proton.me",
    "me.com", "aol.com", "msn.com",
])


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


def derive_label(email: str, name: str) -> str:
    """Derives a short, uppercase Gmail label from a contact's name or email.

    Prefers the contact's first name; falls back to the local part of the
    address for free-provider domains, then to the domain name itself.
    Shared by app.py and contact_analyzer.py so a contact gets the same
    label regardless of which flow protected it.
    """
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


def add_contact_rule(
    email: str,
    label: str,
    mark_important: bool = True,
    rules_path: str | Path | None = None,
) -> dict:
    """Inserts a new entry into CONTACT_RULES in rules.py and reloads the module.

    Shared by app.py (_proteger_remitente) and contact_analyzer.py
    (_write_contact_rule) — both used to hand-roll this same brace-depth
    scan and string-insertion logic independently.

    Returns one of:
      {"success": True, "email": email, "label": label}
      {"already_protected": True}
      {"error": "..."}
    """
    import importlib
    import gmail_processor.rules as rules_mod

    if email in rules_mod.CONTACT_RULES:
        return {"already_protected": True}

    path = Path(rules_path) if rules_path is not None else Path(rules_mod.__file__)

    try:
        lines = path.read_text(encoding="utf-8").split("\n")

        in_cr = False
        depth = 0
        insert_at = -1
        for i, line in enumerate(lines):
            if not in_cr:
                if "CONTACT_RULES" in line and "=" in line and "{" in line:
                    in_cr = True
                    depth = line.count("{") - line.count("}")
            else:
                depth += line.count("{") - line.count("}")
                if depth <= 0:
                    insert_at = i
                    break

        if insert_at == -1:
            return {"error": "No se encontró CONTACT_RULES en rules.py"}

        # repr() safely escapes quotes/backslashes for the Python string literal
        mark_str = "True" if mark_important else "False"
        new_line = f"    {email!r}: {{\"label\": {label!r}, \"mark_important\": {mark_str}}},"
        lines.insert(insert_at, new_line)
        path.write_text("\n".join(lines), encoding="utf-8")

        importlib.reload(rules_mod)
        return {"success": True, "email": email, "label": label}
    except Exception as exc:
        return {"error": str(exc)}
