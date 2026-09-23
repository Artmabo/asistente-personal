"""
Actions: executes Gmail API operations with retry logic.

All public methods return True on success, False on failure.
In dry_run mode they log the intended action and return True without touching the API.
"""
import json
import socket
import ssl
import time
import logging
from googleapiclient.errors import HttpError
from google.auth.exceptions import TransportError

logger = logging.getLogger("gmail_processor.actions")

_MAX_RETRIES = 3
_BASE_DELAY  = 1.0   # seconds before first retry (doubles each attempt)

# Transient transport-level failures (not HttpError, since the request never
# got a response) — a dropped connection or DNS blip shouldn't abort the run.
_TRANSIENT_ERRORS = (ConnectionError, TimeoutError, socket.error, ssl.SSLError, TransportError)


class GmailActions:
    def __init__(self, service, dry_run: bool = False):
        self.service  = service
        self.dry_run  = dry_run
        self._labels: dict[str, str] = {}   # label name → label id cache

    # ── Label management ──────────────────────────────────────────────────────

    def ensure_label(self, name: str) -> str:
        """Returns the label ID for `name`, creating it in Gmail if needed."""
        if not self._labels:
            self._load_labels()

        if name in self._labels:
            return self._labels[name]

        if self.dry_run:
            fake_id = f"dry_{name}"
            self._labels[name] = fake_id
            logger.debug(f"[DRY RUN] Would create label '{name}'")
            return fake_id

        result = self._call(
            self.service.users().labels().create,
            userId="me",
            body={
                "name": name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        if result:
            self._labels[name] = result["id"]
            logger.info(f"Created Gmail label '{name}' (id={result['id']})")
            return result["id"]
        return ""

    def _load_labels(self):
        result = self._call(self.service.users().labels().list, userId="me")
        if result:
            for lbl in result.get("labels", []):
                self._labels[lbl["name"]] = lbl["id"]

    # ── Message operations ────────────────────────────────────────────────────

    def add_label(self, msg_id: str, label_name: str) -> bool:
        label_id = self.ensure_label(label_name)
        if not label_id:
            return False
        if self.dry_run:
            logger.info(f"[DRY RUN] add_label '{label_name}' → {msg_id}")
            return True
        return self._modify(msg_id, add=[label_id])

    def remove_label(self, msg_id: str, label_name: str) -> bool:
        if not self._labels:
            self._load_labels()
        label_id = self._labels.get(label_name)
        if not label_id:
            return True  # Label doesn't exist — nothing to remove
        if self.dry_run:
            logger.info(f"[DRY RUN] remove_label '{label_name}' → {msg_id}")
            return True
        return self._modify(msg_id, remove=[label_id])

    def apply_all(
        self,
        msg_id: str,
        label_names: list[str] = None,
        add_system: list[str] = None,
        remove_system: list[str] = None,
    ) -> bool:
        """Combines label additions and a system-label change (archive/mark_important)
        into a single Gmail API call instead of one modify() per label + one per action."""
        add_ids = []
        resolved_ok = True
        for name in (label_names or []):
            label_id = self.ensure_label(name)
            if label_id:
                add_ids.append(label_id)
            else:
                resolved_ok = False
        add_ids.extend(add_system or [])

        if not add_ids and not remove_system:
            return resolved_ok

        if self.dry_run:
            logger.info(
                f"[DRY RUN] apply_all labels={label_names} add_system={add_system} "
                f"remove_system={remove_system} → {msg_id}"
            )
            return resolved_ok

        return resolved_ok and self._modify(msg_id, add=add_ids or None, remove=remove_system)

    def mark_important(self, msg_id: str) -> bool:
        if self.dry_run:
            logger.info(f"[DRY RUN] mark_important → {msg_id}")
            return True
        return self._modify(msg_id, add=["IMPORTANT"])

    def archive(self, msg_id: str) -> bool:
        """Archive by removing the INBOX label."""
        if self.dry_run:
            logger.info(f"[DRY RUN] archive → {msg_id}")
            return True
        return self._modify(msg_id, remove=["INBOX"])

    def trash(self, msg_id: str) -> bool:
        if self.dry_run:
            logger.info(f"[DRY RUN] trash → {msg_id}")
            return True
        result = self._call(
            self.service.users().messages().trash,
            userId="me",
            id=msg_id,
        )
        return result is not None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _modify(self, msg_id: str, add: list = None, remove: list = None) -> bool:
        body = {}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove
        result = self._call(
            self.service.users().messages().modify,
            userId="me",
            id=msg_id,
            body=body,
        )
        return result is not None

    def _call(self, method, **kwargs):
        """Executes a Gmail API call with exponential-backoff retry on rate limits
        and on transient network failures (the request never reached Google)."""
        delay = _BASE_DELAY
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return method(**kwargs).execute()
            except HttpError as e:
                status = int(e.resp.status)
                # Hard permission failure — raise immediately (do not retry)
                if status == 403 and _is_permission_error(e):
                    logger.error(f"Insufficient permissions: {e}")
                    raise
                # Rate limit or transient server error — retry with backoff
                if status in (403, 429, 500, 503) and attempt < _MAX_RETRIES:
                    kind = "Rate limit" if status in (403, 429) else "Server error"
                    logger.warning(f"{kind} ({status}), retry {attempt}/{_MAX_RETRIES} in {delay:.1f}s")
                    time.sleep(delay)
                    delay *= 2
                    continue
                logger.error(f"API error {status} on attempt {attempt}: {e}")
                return None
            except _TRANSIENT_ERRORS as e:
                if attempt < _MAX_RETRIES:
                    logger.warning(f"Network error ({e}), retry {attempt}/{_MAX_RETRIES} in {delay:.1f}s")
                    time.sleep(delay)
                    delay *= 2
                    continue
                logger.error(f"Network error on attempt {attempt}: {e}")
                return None
        return None


def _is_permission_error(exc: HttpError) -> bool:
    """Returns True when the 403 signals missing OAuth scopes, not a quota hit."""
    _PERMISSION_REASONS = {"insufficientPermissions", "authError"}
    try:
        body = json.loads(exc.content)
        reasons = {
            err.get("reason", "")
            for err in body.get("error", {}).get("errors", [])
        }
        return bool(reasons & _PERMISSION_REASONS)
    except Exception:
        return "insufficient" in str(exc).lower()
