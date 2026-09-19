"""
Shared, thread-safe helpers for programmatically editing gmail_processor/rules.py.

Centralizes the read → find-insertion-point → write logic that used to be
duplicated across app.py, contact_analyzer.py and cli_menu.py with
inconsistent escaping (one copy interpolated raw values into the generated
source, which let a crafted "From" header inject arbitrary Python into
rules.py). Every value is now written via repr(), and a module-level lock
serializes concurrent read-modify-write cycles from different threads.
"""
import importlib
import threading
from pathlib import Path

_LOCK = threading.Lock()
_RULES_PATH = Path(__file__).parent / "rules.py"


def add_contact_rule(email: str, label: str, important: bool) -> dict:
    """Appends a CONTACT_RULES entry for `email` to rules.py.

    Returns {"success": True, "email": ..., "label": ...},
    {"already_protected": True}, or {"error": "..."}.
    """
    with _LOCK:
        import gmail_processor.rules as rules_mod
        importlib.reload(rules_mod)
        if email in rules_mod.CONTACT_RULES:
            return {"already_protected": True}

        try:
            lines = _RULES_PATH.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return {"error": str(exc)}

        insert_at = _find_dict_close(lines, "CONTACT_RULES")
        if insert_at is None:
            return {"error": "No se encontró CONTACT_RULES en rules.py"}

        new_line = f"    {email!r}: {{'label': {label!r}, 'mark_important': {bool(important)!r}}},"
        lines.insert(insert_at, new_line)

        try:
            _RULES_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            return {"error": str(exc)}

        importlib.reload(rules_mod)
        return {"success": True, "email": email, "label": label}


def remove_contact_rule(email: str) -> bool:
    """Removes the CONTACT_RULES entry for `email` from rules.py, if present."""
    with _LOCK:
        try:
            lines = _RULES_PATH.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False

        needle_repr  = repr(email)
        needle_plain = f'"{email}"'
        new_lines = []
        removed   = False
        for line in lines:
            if (needle_repr in line or needle_plain in line) and not line.strip().startswith("#"):
                removed = True
                continue
            new_lines.append(line)

        if not removed:
            return False

        try:
            _RULES_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except OSError:
            return False

        import gmail_processor.rules as rules_mod
        importlib.reload(rules_mod)
        return True


def add_domain_rule(domain: str, label: str, action: str = "mark_important") -> bool:
    """Appends a single-domain entry to DOMAIN_RULES in rules.py."""
    with _LOCK:
        try:
            lines = _RULES_PATH.read_text(encoding="utf-8").splitlines()
        except OSError:
            return False

        start_idx = None
        for i, line in enumerate(lines):
            if "DOMAIN_RULES: list[dict] = [" in line:
                start_idx = i
                break
        if start_idx is None:
            return False

        depth   = 1
        end_idx = None
        for i in range(start_idx + 1, len(lines)):
            for ch in lines[i]:
                if   ch == "[": depth += 1
                elif ch == "]": depth -= 1
                if depth == 0:
                    end_idx = i
                    break
            if end_idx is not None:
                break
        if end_idx is None:
            return False

        block_text = "\n".join(lines[start_idx:end_idx])
        if repr(domain) in block_text or f'"{domain}"' in block_text:
            return False

        new_entry = (
            f"    {{\n"
            f"        'domains': [{domain!r}],\n"
            f"        'label': {label!r},\n"
            f"        'action': {action!r},\n"
            f"    }},"
        )
        lines.insert(end_idx, new_entry)

        try:
            _RULES_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            return False

        import gmail_processor.rules as rules_mod
        importlib.reload(rules_mod)
        return True


def _find_dict_close(lines: list[str], var_name: str) -> int | None:
    """Returns the line index of the closing '}' for `var_name: ... = {...}`."""
    in_block = False
    depth    = 0
    for i, line in enumerate(lines):
        if not in_block:
            if var_name in line and "=" in line and "{" in line:
                in_block = True
                depth = line.count("{") - line.count("}")
        else:
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                return i
    return None
