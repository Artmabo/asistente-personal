"""Safe, single-source-of-truth editing of gmail_processor/rules.py's rule tables.

This used to be implemented three times (app.py::_proteger_remitente,
contact_analyzer.py::_write_contact_rule, cli_menu.py::_patch_rules_add_contact/
_patch_rules_add_domain), each with its own hand-rolled brace matching and a
different level of escaping. The cli_menu.py copies did no escaping at all:
an email or label containing a `"` (attacker-controlled, since it comes from
parsed `From` headers of arbitrary inbound mail) would corrupt rules.py, and
a crafted value could inject arbitrary Python that runs on the next
`importlib.reload`. All three call sites now go through the helpers below,
which validate the address/domain and use `repr()` to escape every value
written into the file.
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

_EMAIL_RE = re.compile(r"^[^@\s\"'\\]+@[^@\s\"'\\]+\.[^@\s\"'\\]+$")
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$")

_RULES_PATH = Path(__file__).parent / "rules.py"


def _reload_rules():
    import gmail_processor.rules as rules_mod
    importlib.reload(rules_mod)
    return rules_mod


def _find_block_end(lines: list[str], marker: str, open_ch: str, close_ch: str) -> int | None:
    """Returns the index of the line closing the `open_ch`/`close_ch` block that
    starts on the line containing `marker`, or None if not found."""
    start_idx = None
    for i, line in enumerate(lines):
        if marker in line and open_ch in line:
            start_idx = i
            break
    if start_idx is None:
        return None

    depth = lines[start_idx].count(open_ch) - lines[start_idx].count(close_ch)
    for i in range(start_idx + 1, len(lines)):
        depth += lines[i].count(open_ch) - lines[i].count(close_ch)
        if depth <= 0:
            return i
    return None


def add_contact_rule(email: str, label: str, important: bool = True) -> dict:
    """Inserts a new CONTACT_RULES entry. Returns a dict with either
    `success`, `already_protected`, or `error`."""
    if not _EMAIL_RE.match(email):
        return {"error": f"Dirección de correo no válida: {email}"}

    rules_mod = _reload_rules()
    if email in rules_mod.CONTACT_RULES:
        return {"already_protected": True}

    try:
        lines = _RULES_PATH.read_text(encoding="utf-8").split("\n")
    except OSError as exc:
        return {"error": str(exc)}

    insert_at = _find_block_end(lines, "CONTACT_RULES", "{", "}")
    if insert_at is None:
        return {"error": "No se encontró CONTACT_RULES en rules.py"}

    new_line = f"    {email!r}: {{\"label\": {label!r}, \"mark_important\": {important!r}}},"
    lines.insert(insert_at, new_line)

    try:
        _RULES_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"error": str(exc)}

    _reload_rules()
    return {"success": True, "email": email, "label": label}


def remove_contact_rule(email: str) -> bool:
    """Removes the CONTACT_RULES entry for `email`, if present."""
    try:
        lines = _RULES_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    needle = repr(email)
    new_lines, removed = [], False
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("#") and stripped.startswith(needle + ":"):
            removed = True
            continue
        new_lines.append(line)

    if not removed:
        return False

    try:
        _RULES_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except OSError:
        return False

    _reload_rules()
    return True


def add_domain_rule(domain: str, label: str, action: str = "mark_important") -> dict:
    """Inserts a new DOMAIN_RULES entry. Returns a dict with either
    `success`, `already_exists`, or `error`."""
    if not _DOMAIN_RE.match(domain):
        return {"error": f"Dominio no válido: {domain}"}

    try:
        lines = _RULES_PATH.read_text(encoding="utf-8").split("\n")
    except OSError as exc:
        return {"error": str(exc)}

    end_idx = _find_block_end(lines, "DOMAIN_RULES", "[", "]")
    if end_idx is None:
        return {"error": "No se encontró DOMAIN_RULES en rules.py"}

    start_idx = next(i for i, line in enumerate(lines) if "DOMAIN_RULES" in line and "[" in line)
    block_text = "\n".join(lines[start_idx:end_idx])
    if repr(domain) in block_text:
        return {"already_exists": True}

    new_entry = (
        f"    {{\n"
        f"        \"domains\": [{domain!r}],\n"
        f"        \"label\": {label!r},\n"
        f"        \"action\": {action!r},\n"
        f"    }},"
    )
    lines.insert(end_idx, new_entry)

    try:
        _RULES_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        return {"error": str(exc)}

    _reload_rules()
    return {"success": True, "domain": domain, "label": label}
