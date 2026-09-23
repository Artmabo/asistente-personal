"""
AuditLogger: structured per-decision log in JSONL format.

One JSON object per line in audit_log.jsonl:
  {"ts":"…","msg_id":"…","sender":"…","domain":"…","score":-15.0,
   "decision":"TRASH","action":"trash","rule":"promotions_60d",
   "reason":"…","learned":false,"protected":false,"dry_run":true}

The file is capped at MAX_ENTRIES lines; older entries are rotated out
when the cap is exceeded (keeps the most recent MAX_ENTRIES).

Writes are buffered in memory and flushed to disk in one pass via flush().
This avoids one open() per message during high-volume runs.
"""
import csv
import io
import json
import logging
from collections import deque
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("gmail_processor.audit")

MAX_ENTRIES = 10_000


class AuditLogger:
    def __init__(self, path: str = "audit_log.jsonl", dry_run: bool = False):
        self.path    = Path(path)
        self.dry_run = dry_run
        self._buf: list[dict] = []

    # ── Public ────────────────────────────────────────────────────────────────

    def log(
        self,
        *,
        msg_id:    str,
        sender:    str,
        domain:    str,
        score:     float,
        decision:  str,        # "TRASH" | "KEEP" | "SKIP"
        action:    str,        # "trash" | "keep" | "skip"
        rule:      str,
        reason:    str,
        learned:   bool = False,
        protected: bool = False,
    ):
        self._buf.append({
            "ts":        datetime.now().isoformat(timespec="seconds"),
            "msg_id":    msg_id,
            "sender":    sender,
            "domain":    domain,
            "score":     score,
            "decision":  decision,
            "action":    action,
            "rule":      rule,
            "reason":    reason,
            "learned":   learned,
            "protected": protected,
            "dry_run":   self.dry_run,
        })

    def flush(self):
        """Writes buffered entries to disk. Called once per run."""
        if not self._buf:
            return
        existing = self._load()
        combined = (existing + self._buf)[-MAX_ENTRIES:]
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            for entry in combined:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        tmp_path.replace(self.path)
        logger.debug(f"Audit: {len(self._buf)} entries → {self.path}  (total={len(combined)})")
        self._buf = []

    def recent(self, n: int = 20) -> list[dict]:
        """Returns the n most recent entries (including un-flushed buffer)."""
        if n <= 0:
            return []
        buf_entries = self._buf[-n:]
        if len(buf_entries) >= n:
            return buf_entries
        persisted = self._load_tail(n - len(buf_entries))
        return (persisted + self._buf)[-n:]

    def recent_filtered(self, last: int, decision: str | None = None) -> list[dict]:
        """Returns the `last` most recent entries matching `decision` (or all if None).

        The requested decision may be sparse in the recent window, so this widens
        the fetch window geometrically until enough matches are found or the whole
        log has been scanned.
        """
        if last <= 0:
            return []
        fetch_n = max(last * 3, 200)
        while True:
            candidates = self.recent(fetch_n)
            entries = (
                [e for e in candidates if e.get("decision") == decision]
                if decision is not None
                else candidates
            )
            if len(entries) >= last or fetch_n >= MAX_ENTRIES:
                return entries[-last:]
            fetch_n = min(fetch_n * 4, MAX_ENTRIES)

    def stats_summary(self) -> dict:
        """Counts decisions from the persisted log."""
        counts: dict[str, int] = {"TRASH": 0, "KEEP": 0, "SKIP": 0}
        for entry in self._load():
            decision = entry.get("decision", "")
            if decision in counts:
                counts[decision] += 1
        return counts

    def export_csv(self, n: int = MAX_ENTRIES) -> str:
        """Returns the most recent `n` log entries as a UTF-8 CSV string."""
        return self.entries_to_csv(self.recent(n))

    def entries_to_csv(self, entries: list[dict]) -> str:
        """Serializes a list of audit entries (e.g. pre-filtered by caller) to CSV."""
        if not entries:
            return ""
        fieldnames = ["ts", "sender", "domain", "score", "decision", "action", "rule", "reason", "learned", "protected", "dry_run", "msg_id"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(entries)
        return buf.getvalue()

    # ── Private ───────────────────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []
        return self._parse_lines(lines)

    def _load_tail(self, n: int) -> list[dict]:
        """Reads only the last n lines using a deque to avoid loading the whole file."""
        if not self.path.exists() or n <= 0:
            return []
        try:
            with open(self.path, encoding="utf-8") as f:
                tail = deque((ln for ln in f if ln.strip()), maxlen=n)
        except OSError:
            return []
        return self._parse_lines(tail)

    @staticmethod
    def _parse_lines(lines) -> list[dict]:
        """Parses JSONL lines, skipping any individually corrupted line rather than
        discarding the whole (otherwise valid) history a single bad line was found in."""
        entries = []
        for line in lines:
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Audit log: skipping malformed line")
        return entries
