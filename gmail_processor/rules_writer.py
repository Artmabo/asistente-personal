"""
Shared helper for programmatically patching gmail_processor/rules.py.

CLI menu, the Streamlit app, and ContactAnalyzer all let the user protect a
sender with one click; each used to reimplement its own copy of the
CONTACT_RULES-block-splicing logic. Centralized here so there is exactly one
place that knows how to safely insert/remove a rules.py entry.
"""
import importlib
from pathlib import Path

RULES_PATH = Path(__file__).parent / "rules.py"


def add_contact_rule(email: str, label: str, mark_important: bool = True) -> dict:
    """
    Appends a CONTACT_RULES entry for `email` to rules.py and reloads the
    module. Returns {"success": True, "label": ...}, {"already_protected": True},
    or {"error": ...}.
    """
    from . import rules as rules_mod

    if email in rules_mod.CONTACT_RULES:
        return {"already_protected": True}

    try:
        lines = RULES_PATH.read_text(encoding="utf-8").split("\n")
    except OSError as exc:
        return {"error": str(exc)}

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
        return {"error": "CONTACT_RULES closing brace not found in rules.py"}

    # Double-quoted key (matching the existing entries and remove_contact_rule's
    # own double-quote match below) with backslashes/quotes escaped so the
    # written line stays valid Python.
    safe_email = email.replace("\\", "\\\\").replace('"', '\\"')
    safe_label = label.replace("\\", "\\\\").replace('"', '\\"')
    new_line = f'    "{safe_email}": {{"label": "{safe_label}", "mark_important": {mark_important!r}}},'
    lines.insert(insert_at, new_line)

    try:
        RULES_PATH.write_text("\n".join(lines), encoding="utf-8")
    except OSError as exc:
        return {"error": str(exc)}

    importlib.reload(rules_mod)
    return {"success": True, "email": email, "label": label}


def remove_contact_rule(email: str) -> bool:
    """Removes the CONTACT_RULES line for `email` from rules.py. Returns True if removed."""
    from . import rules as rules_mod

    try:
        lines = RULES_PATH.read_text(encoding="utf-8").split("\n")
    except OSError:
        return False

    new_lines = []
    removed = False
    for line in lines:
        if f'"{email}"' in line and not line.strip().startswith("#"):
            removed = True
            continue
        new_lines.append(line)

    if not removed:
        return False

    try:
        RULES_PATH.write_text("\n".join(new_lines), encoding="utf-8")
    except OSError:
        return False

    importlib.reload(rules_mod)
    return True


def derive_label(email: str, name: str = "") -> str:
    """
    Derives a short Gmail label from a contact's name (preferred) or email.
    Free-provider addresses (gmail.com, etc.) use the local part; corporate
    domains use the domain's first segment.
    """
    from .utils import FREE_EMAIL_PROVIDERS

    words = name.strip().split()
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
