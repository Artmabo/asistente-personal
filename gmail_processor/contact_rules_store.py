"""
ContactRulesStore: safe, atomic persistence for contact/domain rules added at runtime.

Previously, "Proteger remitente" (app.py), the smart-setup wizard (cli_menu.py)
and the contact analyzer (contact_analyzer.py) each added new entries by
string-splicing a Python source line directly into rules.py and then calling
importlib.reload(). That approach had two problems:

  1. Some call sites interpolated the sender's email/label into the new line
     without escaping quotes/backslashes. A crafted quoted-string local part
     (valid per RFC 5321, e.g. '"a\\"b"@example.com') could break out of the
     string literal and inject arbitrary Python that then executed on reload.
  2. Writing straight to rules.py is a non-atomic edit of an imported module:
     a crash mid-write (process kill, container restart) leaves rules.py
     truncated/invalid, breaking every other import in the app.
  3. Real contact emails ended up hardcoded in a file that's tracked by git.

Runtime-added entries are instead stored as data in config/contact_rules.json
(gitignored) and merged over the static defaults in rules.py at import time.
Writes use a temp-file + atomic rename so a crash mid-write can't corrupt
the store.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger("gmail_processor.contact_rules_store")

_STORE_PATH = Path(__file__).resolve().parent.parent / "config" / "contact_rules.json"


def _empty() -> dict:
    return {"contacts": {}, "domains": []}


def load() -> dict:
    """Returns the persisted overrides: {"contacts": {...}, "domains": [...]}."""
    if _STORE_PATH.exists():
        try:
            data = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
            data.setdefault("contacts", {})
            data.setdefault("domains", [])
            return data
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"No se pudo leer {_STORE_PATH}: {e}")
    return _empty()


def _save(data: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_STORE_PATH)


def add_contact(email: str, label: str, mark_important: bool, existing: dict = None) -> bool:
    """Persists a new contact rule. Returns False if already present (in the
    store or in `existing`, e.g. the static CONTACT_RULES defaults)."""
    if not email or (existing and email in existing):
        return False
    data = load()
    if email in data["contacts"]:
        return False
    data["contacts"][email] = {"label": label, "mark_important": mark_important}
    _save(data)
    return True


def remove_contact(email: str) -> bool:
    """Removes a contact rule previously added at runtime. Returns False if it
    isn't in the store (e.g. it's one of the static defaults in rules.py)."""
    data = load()
    if email not in data["contacts"]:
        return False
    del data["contacts"][email]
    _save(data)
    return True


def add_domain(domain: str, label: str, action: str = "mark_important", existing_domains: set = None) -> bool:
    """Persists a new single-domain rule. Returns False if already covered."""
    if existing_domains and domain in existing_domains:
        return False
    data = load()
    for rule in data["domains"]:
        if domain in rule.get("domains", []):
            return False
    data["domains"].append({"domains": [domain], "label": label, "action": action})
    _save(data)
    return True
