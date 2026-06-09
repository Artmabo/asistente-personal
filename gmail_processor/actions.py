"""
Actions: executes Gmail API operations with retry logic.

All public methods return True on success, False on failure.
In dry_run mode they log the intended action and return True without touching the API.
"""
import time
import logging
from googleapiclient.errors import HttpError

logger = logging.getLogger("gmail_processor.actions")

_MAX_RETRIES = 3
_BASE_DELAY  = 1.0   # seconds before first retry (doubles each attempt)


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
        """Executes a Gmail API call with exponential-backoff retry on rate limits."""
        delay = _BASE_DELAY
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return method(**kwargs).execute()
            except HttpError as e:
                status = int(e.resp.status)
                # Hard permission failure — raise immediately
                if status == 403 and "insufficient" in str(e).lower():
                    logger.error(f"Insufficient permissions: {e}")
                    raise
                # Rate limit — retry with backoff
                if status in (403, 429) and attempt < _MAX_RETRIES:
                    logger.warning(f"Rate limit ({status}), retry {attempt}/{_MAX_RETRIES} in {delay:.1f}s")
                    time.sleep(delay)
                    delay *= 2
                    continue
                logger.error(f"API error {status} on attempt {attempt}: {e}")
                return None
        return None
