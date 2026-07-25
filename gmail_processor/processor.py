"""
GmailProcessor: orchestrates fetching, classifying, and acting on emails.
"""
import logging
from googleapiclient.errors import HttpError

from .auth import get_service
from .classifier import EmailClassifier, Classification
from .actions import GmailActions
from .cleanup_storage import StorageCleaner
from .learning_engine import LearningEngine
from .audit_log import AuditLogger
from .utils import get_header
from . import rules as cfg

logger = logging.getLogger("gmail_processor")


def setup_logging(
    level: int = logging.INFO,
    log_file: str = "gmail_processor.log",
):
    """Configures logging to both console and a rotating log file."""
    fmt = "%(asctime)s [%(levelname)-8s] %(message)s"
    logging.basicConfig(
        level=level,
        format=fmt,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


class GmailProcessor:
    def __init__(self, service=None):
        self.service    = service or get_service()
        self.classifier = EmailClassifier()
        self.actions    = GmailActions(self.service, dry_run=cfg.DRY_RUN)
        self.engine     = LearningEngine()
        self.audit      = AuditLogger(dry_run=cfg.DRY_RUN)
        self.stats      = {
            "processed": 0,
            "labeled":   0,
            "important": 0,
            "archived":  0,
            "trashed":   0,
            "skipped":   0,
            "errors":    0,
        }

    def run(self, query: str = None, cleanup: bool = False, learning: bool = False):
        """
        Classifies and acts on emails from `query` (defaults to cfg.QUERY_FILTER).
        cleanup=True  → also runs StorageCleaner after classification.
        learning=True → enables writing to learning_state.json and threshold adjustments.
        """
        query = query or cfg.QUERY_FILTER
        mode  = "DRY RUN" if cfg.DRY_RUN else "LIVE"
        logger.info(f"{'='*55}")
        logger.info(f"  Gmail Processor — mode={mode}  query='{query}'")
        logger.info(f"{'='*55}")

        page_token = None
        page = 0
        while True:
            page += 1
            try:
                result = self.service.users().messages().list(
                    userId="me",
                    q=query,
                    maxResults=cfg.MAX_RESULTS_PER_PAGE,
                    pageToken=page_token,
                ).execute()
            except HttpError as e:
                logger.error(f"Failed to list messages (page {page}): {e}")
                break

            messages = result.get("messages", [])
            if not messages:
                logger.info("No more messages found.")
                break

            logger.info(f"Page {page}: {len(messages)} messages")
            for stub in messages:
                self._process_one(stub["id"])

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        self._print_summary()

        if cleanup:
            cleaner = StorageCleaner(
                self.service,
                self.actions,
                engine=self.engine,
                audit=self.audit,
                learning_mode=learning,
            )
            self.stats["cleanup"] = cleaner.run()

        elif learning:
            logger.warning("--learning requiere --cleanup para actualizar el estado.")

        return self.stats

    # ── Internal ──────────────────────────────────────────────────────────────

    def _process_one(self, msg_id: str):
        try:
            message = self.service.users().messages().get(
                userId="me",
                id=msg_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
        except HttpError as e:
            logger.error(f"Could not fetch {msg_id}: {e}")
            self.stats["errors"] += 1
            return

        c = self.classifier.classify(message)
        self._apply(msg_id, message, c)
        self.stats["processed"] += 1

    def _apply(self, msg_id: str, message: dict, c: Classification):
        headers = message.get("payload", {}).get("headers", [])
        sender  = get_header(headers, "From")  or "?"
        subject = get_header(headers, "Subject") or "(sin asunto)"

        logger.info(
            f"[{c.email_type.upper():<12}] {_short(sender, 40)} | {_short(subject, 50)}"
            f" → {c.action}  labels={c.labels}  protected={c.protected}"
        )

        # Apply all labels first
        for label in c.labels:
            if self.actions.add_label(msg_id, label):
                self.stats["labeled"] += 1

        # Execute primary action
        match c.action:
            case "trash":
                if c.protected:
                    logger.warning(f"  Blocked trash on protected message {msg_id}")
                    self.stats["skipped"] += 1
                elif self.actions.trash(msg_id):
                    self.stats["trashed"] += 1

            case "archive":
                if self.actions.archive(msg_id):
                    self.stats["archived"] += 1

            case "mark_important":
                if self.actions.mark_important(msg_id):
                    self.stats["important"] += 1

            case _:  # "label_only" or "unknown"
                self.stats["skipped"] += 1

    def _print_summary(self):
        s = self.stats
        logger.info(
            f"\n{'='*55}\n"
            f"  RESUMEN\n"
            f"  Procesados : {s['processed']}\n"
            f"  Etiquetados: {s['labeled']}\n"
            f"  Importantes: {s['important']}\n"
            f"  Archivados : {s['archived']}\n"
            f"  Papelera   : {s['trashed']}\n"
            f"  Omitidos   : {s['skipped']}\n"
            f"  Errores    : {s['errors']}\n"
            f"{'='*55}"
        )


def _short(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1] + "…"
