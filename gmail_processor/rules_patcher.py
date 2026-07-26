"""
Shared helpers to safely patch gmail_processor/rules.py at runtime.

rules.py is loaded as executable Python (`from . import rules as cfg`) and
reloaded after every edit, so any programmatic patch here must:
  1. Escape values before embedding them in a string literal — email
     display names and domains originate from untrusted inbound mail
     (via smart_setup.py's contact/domain suggestions), so an unescaped
     quote or backslash could break out of the literal and inject code
     that runs the moment rules.py is next imported/reloaded.
  2. Write atomically (temp file + rename) — a crash mid-write must never
     leave rules.py truncated, since every part of the app imports it.

cli_menu.py and contact_analyzer.py both mutate CONTACT_RULES/DOMAIN_RULES;
this module is the single place that does so, replacing what used to be
two independently-maintained (and inconsistently escaped) copies of the
same logic.
"""
import importlib
from pathlib import Path

RULES_PATH = Path(__file__).parent / "rules.py"

_CONTACT_RULES_MARKER = "CONTACT_RULES: dict[str, dict] = {"
_DOMAIN_RULES_MARKER  = "DOMAIN_RULES: list[dict] = ["


def escape_py_str(value: str) -> str:
    """Escapes backslashes and double quotes so `value` is safe to embed
    inside a double-quoted Python string literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _read_lines() -> list[str] | None:
    try:
        return RULES_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None


def _write_lines(lines: list[str]) -> bool:
    """Atomically writes `lines` back to rules.py and reloads the module."""
    try:
        tmp = RULES_PATH.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(RULES_PATH)
    except OSError:
        return False

    from . import rules as rules_mod
    importlib.reload(rules_mod)
    return True


def _find_brace_block(lines: list[str], marker: str) -> tuple[int, int] | None:
    """Finds the (start, end) line range of a `marker ... }` dict block.

    `start` is the line containing `marker`; `end` is the line with the
    matching closing `}` (both indices are into `lines`; entries live on
    the lines strictly between them).
    """
    start_idx = None
    for i, line in enumerate(lines):
        if marker in line:
            start_idx = i
            break
    if start_idx is None:
        return None

    end_idx = None
    for i in range(start_idx + 1, len(lines)):
        if lines[i].strip() == "}":
            end_idx = i
            break
    if end_idx is None:
        return None

    return start_idx, end_idx


def add_contact_rule(email: str, label: str, important: bool) -> bool:
    """Appends a new CONTACT_RULES entry. Returns False if it already
    exists, or if rules.py could not be read/parsed/written."""
    lines = _read_lines()
    if lines is None:
        return False

    block = _find_brace_block(lines, _CONTACT_RULES_MARKER)
    if block is None:
        return False
    start_idx, end_idx = block

    safe_email = escape_py_str(email)
    for line in lines[start_idx:end_idx]:
        if f'"{safe_email}"' in line and not line.strip().startswith("#"):
            return False  # already exists

    safe_label    = escape_py_str(label)
    important_str = "True" if important else "False"
    new_entry = f'    "{safe_email}": {{"label": "{safe_label}", "mark_important": {important_str}}},'
    lines.insert(end_idx, new_entry)

    return _write_lines(lines)


def remove_contact_rule(email: str) -> bool:
    """Removes the CONTACT_RULES entry for `email`, scoped strictly to the
    CONTACT_RULES block so it can never touch unrelated lines elsewhere in
    rules.py."""
    lines = _read_lines()
    if lines is None:
        return False

    block = _find_brace_block(lines, _CONTACT_RULES_MARKER)
    if block is None:
        return False
    start_idx, end_idx = block

    safe_email = escape_py_str(email)
    new_lines  = list(lines)
    removed    = False
    for i in range(end_idx - 1, start_idx, -1):
        if f'"{safe_email}"' in new_lines[i] and not new_lines[i].strip().startswith("#"):
            del new_lines[i]
            removed = True

    if not removed:
        return False

    return _write_lines(new_lines)


def add_domain_rule(domain: str, label: str, action: str = "mark_important") -> bool:
    """Appends a new single-domain entry to DOMAIN_RULES in rules.py."""
    lines = _read_lines()
    if lines is None:
        return False

    start_idx = None
    for i, line in enumerate(lines):
        if _DOMAIN_RULES_MARKER in line:
            start_idx = i
            break
    if start_idx is None:
        return False

    # Find closing ] by tracking bracket depth
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

    safe_domain = escape_py_str(domain)
    block_text  = "\n".join(lines[start_idx:end_idx])
    if f'"{safe_domain}"' in block_text:
        return False

    safe_label  = escape_py_str(label)
    safe_action = escape_py_str(action)
    new_entry = (
        f'    {{\n'
        f'        "domains": ["{safe_domain}"],\n'
        f'        "label": "{safe_label}",\n'
        f'        "action": "{safe_action}",\n'
        f'    }},'
    )
    lines.insert(end_idx, new_entry)

    return _write_lines(lines)
