"""
DuplicateFinder: detects exact-duplicate Gmail messages.

A "duplicate" here means two or more messages sharing the same Message-ID
header — a reliable signal of the *same* email being delivered more than
once (common with forwarding filters, multi-label imports, or provider
retries), as opposed to merely similar-looking messages.

find_duplicates() only reads metadata (no bodies) and is safe to run at any
time. trash_duplicates() reuses GmailActions.trash(), so it respects
dry_run just like the rest of the app — nothing is deleted for real unless
the caller passes a live (non dry_run) GmailActions instance.
"""
import logging
from googleapiclient.errors import HttpError

logger = logging.getLogger("gmail_processor.duplicates")

_MAX_MESSAGES = 2000


def find_duplicates(
    service,
    query: str = "in:inbox",
    max_messages: int = _MAX_MESSAGES,
) -> dict[str, list[dict]]:
    """
    Scans up to `max_messages` messages matching `query` and groups them by
    Message-ID header. Returns {message_id: [entries, ...]} — only for
    groups with 2+ entries (true duplicates). Each entry has id/subject/from/
    internal_date and the list is sorted newest-first.
    """
    seen: dict[str, list[dict]] = {}
    page_token = None
    fetched = 0

    while fetched < max_messages:
        try:
            resp = service.users().messages().list(
                userId="me", q=query,
                maxResults=min(500, max_messages - fetched),
                pageToken=page_token,
            ).execute()
        except HttpError as e:
            logger.warning(f"List failed while scanning for duplicates: {e}")
            break

        stubs = resp.get("messages", [])
        if not stubs:
            break

        for stub in stubs:
            if fetched >= max_messages:
                break
            fetched += 1
            try:
                msg = service.users().messages().get(
                    userId="me", id=stub["id"], format="metadata",
                    metadataHeaders=["Message-ID", "Subject", "From"],
                ).execute()
            except HttpError:
                continue

            headers = msg.get("payload", {}).get("headers", [])
            mid = next((h["value"] for h in headers if h["name"].lower() == "message-id"), "")
            if not mid:
                continue  # nothing stable to group by — skip

            seen.setdefault(mid, []).append({
                "id":            msg["id"],
                "subject":       next((h["value"] for h in headers if h["name"].lower() == "subject"), ""),
                "from":          next((h["value"] for h in headers if h["name"].lower() == "from"), ""),
                "internal_date": int(msg.get("internalDate", 0)),
            })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return {
        mid: sorted(entries, key=lambda e: e["internal_date"], reverse=True)
        for mid, entries in seen.items() if len(entries) > 1
    }


def trash_duplicates(service, actions, duplicates: dict[str, list[dict]]) -> dict:
    """
    Trashes all but the newest message in each duplicate group.
    `actions` is a GmailActions instance — dry_run is honored via its own
    trash() implementation, so this is safe to call speculatively.
    Returns {"groups": n, "trashed": n}.
    """
    trashed = 0
    for entries in duplicates.values():
        for entry in entries[1:]:   # entries[0] is newest — keep it
            if actions.trash(entry["id"]):
                trashed += 1
    return {"groups": len(duplicates), "trashed": trashed}
