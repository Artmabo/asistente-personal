"""
DuplicateFinder: detects and trashes exact duplicate emails — the same
message delivered more than once (sync glitches, forwarding loops,
accidental resends by a sender's mailing tool).

Message-ID equality is the criterion: it's a header the sending server
assigns once per unique email, so it only ever matches a message against a
byte-identical copy of itself. Unlike similarity-based dedup (matching on
subject/sender/date), this can't produce false positives against emails
that merely look alike.
"""
import logging
import time
from collections import defaultdict
from typing import Optional

from googleapiclient.errors import HttpError

from .actions import GmailActions
from .audit_log import AuditLogger
from .utils import get_header, extract_email_address, get_domain
from . import rules as cfg

logger = logging.getLogger("gmail_processor.dedupe")

_REQUEST_SLEEP = 0.03


def find_duplicate_messages(
    service,
    actions:     GmailActions,
    query:       str = "in:inbox",
    max_results: int = 1000,
    audit:       Optional[AuditLogger] = None,
) -> dict:
    """
    Scans `query` for messages sharing the same Message-ID header and trashes
    every copy but the oldest. Protected contacts (CONTACT_RULES) are always
    skipped entirely — not even their extra copies are touched. Respects
    `actions.dry_run`.

    Returns {"examined", "duplicate_groups", "trashed", "skipped_protected"}.
    """
    stats = {"examined": 0, "duplicate_groups": 0, "trashed": 0, "skipped_protected": 0}
    groups: dict[str, list[dict]] = defaultdict(list)

    page_token = None
    fetched    = 0
    while fetched < max_results:
        try:
            result = service.users().messages().list(
                userId="me", q=query,
                maxResults=min(500, max_results - fetched),
                pageToken=page_token,
            ).execute()
        except HttpError as e:
            logger.warning(f"Error al listar mensajes: {e}")
            break

        stubs = result.get("messages", [])
        if not stubs:
            break

        for stub in stubs:
            try:
                msg = service.users().messages().get(
                    userId="me", id=stub["id"],
                    format="metadata",
                    metadataHeaders=["Message-ID", "From", "Subject"],
                ).execute()
            except HttpError:
                continue
            finally:
                time.sleep(_REQUEST_SLEEP)

            headers    = msg.get("payload", {}).get("headers", [])
            msg_id_hdr = get_header(headers, "Message-ID").strip()
            if not msg_id_hdr:
                continue  # no Message-ID → can't safely dedupe

            groups[msg_id_hdr].append({
                "id":            stub["id"],
                "sender":        extract_email_address(get_header(headers, "From")),
                "subject":       get_header(headers, "Subject"),
                "internal_date": int(msg.get("internalDate", 0)),
            })
            stats["examined"] += 1
            fetched += 1
            if fetched >= max_results:
                break

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    for copies in groups.values():
        if len(copies) < 2:
            continue

        sender = copies[0]["sender"]
        if sender in cfg.CONTACT_RULES:
            stats["skipped_protected"] += 1
            continue

        stats["duplicate_groups"] += 1
        copies.sort(key=lambda c: c["internal_date"])  # keep the oldest copy
        for dup in copies[1:]:
            if actions.trash(dup["id"]):
                stats["trashed"] += 1
                if audit:
                    audit.log(
                        msg_id=dup["id"], sender=sender, domain=get_domain(sender),
                        score=0.0, decision="TRASH", action="trash",
                        rule="duplicate_message",
                        reason="Copia duplicada exacta (mismo Message-ID)",
                    )

    if audit:
        audit.flush()

    logger.info(
        f"Dedupe: {stats['examined']} examinados, {stats['duplicate_groups']} grupos duplicados,"
        f" {stats['trashed']} enviados a papelera, {stats['skipped_protected']} protegidos omitidos"
    )
    return stats
