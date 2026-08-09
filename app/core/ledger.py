"""
Durable, tamper-evident proof ledger backed by SQLite (WAL).

Every scored transaction and ZK proof lifecycle event is appended as an
immutable row chained to the previous row by SHA-256, so a proof record can be
independently re-verified long after it has been evicted from the in-memory
live store (and survives process restarts).

- SQLite in WAL mode (durable, concurrent readers + single writer).
- Hash chain: entry_hash = SHA256(prev_hash | created_at | event_type | tx_hash
  | status | canonical_payload). Any reordering, deletion, or edit breaks the
  chain and is caught by verify_chain().
- Optional Postgres transport: when settings.postgres_url is set the same rows
  are mirrored there via INSERT ... ON CONFLICT (id) DO NOTHING. SQLite remains
  the local source of truth so the stack runs with zero external infra.
"""
import hashlib
import json
import logging
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS {table} (
    id BIGINT PRIMARY KEY,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    tx_hash TEXT,
    status TEXT,
    payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS {table}_tx_hash_idx ON {table} (tx_hash);
"""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    tx_hash TEXT,
    status TEXT,
    payload TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_ledger_tx_hash ON ledger_entries (tx_hash);
CREATE INDEX IF NOT EXISTS idx_ledger_event_type ON ledger_entries (event_type);
"""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class HashChainedLedger:
    """Append-only hash-chained ledger stored in SQLite (Postgres mirror optional)."""

    def __init__(self, db_path: str = "data/ledger.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._head = self._load_head()

        # Optional Postgres mirror (B7): never blocks or fails the local write.
        self._mirror_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._mirror_thread: Optional[threading.Thread] = None
        self._mirror_mutex = threading.Lock()
        self._mirror_stats = {"queued": 0, "mirrored": 0, "failed": 0, "last_error": None}

    # ------------------------------------------------------------------ #
    # Postgres mirror (B7) - async drain, fail-soft, retry with backoff.
    # ------------------------------------------------------------------ #
    def _maybe_start_mirror(self) -> None:
        if self._mirror_thread is not None:
            return
        with self._mirror_mutex:
            if self._mirror_thread is not None:
                return
            from app.core.config import settings
            if not settings.postgres_url:
                return
            self._mirror_table = getattr(settings, "postgres_ledger_table", "ledger_entries")
            self._mirror_thread = threading.Thread(target=self._mirror_worker, daemon=True, name="ledger-pg-mirror")
            self._mirror_thread.start()
            logger.info(f"B7: Postgres ledger mirror started (table={self._mirror_table})")

    def _pg_connect(self):
        import psycopg2
        from app.core.config import settings
        url = settings.postgres_url.get_secret_value()
        return psycopg2.connect(url, connect_timeout=5)

    def _ensure_pg_table(self, conn) -> None:
        from psycopg2 import sql
        conn.cursor().execute(sql.SQL(_PG_SCHEMA).format(table=sql.Identifier(self._mirror_table)))
        conn.commit()

    def _mirror_worker(self) -> None:
        backoff = 1.0
        while True:
            entry = self._mirror_queue.get()
            try:
                conn = self._pg_connect()
                try:
                    self._ensure_pg_table(conn)
                    from psycopg2 import sql
                    insert = sql.SQL(
                        "INSERT INTO {t} (id, created_at, event_type, tx_hash, status, payload, prev_hash, entry_hash)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING"
                    ).format(t=sql.Identifier(self._mirror_table))
                    conn.cursor().execute(insert, (
                        entry["id"], entry["created_at"], entry["event_type"],
                        entry["tx_hash"], entry["status"], entry["payload_canonical"],
                        entry["prev_hash"], entry["entry_hash"],
                    ))
                    conn.commit()
                finally:
                    conn.close()
                self._mirror_stats["mirrored"] += 1
                backoff = 1.0
            except Exception as e:
                self._mirror_stats["failed"] += 1
                self._mirror_stats["last_error"] = str(e)[:300]
                logger.warning(f"B7: Postgres mirror insert failed, retrying in {backoff:.0f}s: {e}")
                self._mirror_queue.put(entry)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            finally:
                self._mirror_queue.task_done()

    def mirror_stats(self) -> Dict[str, Any]:
        return dict(self._mirror_stats)

    def _load_head(self) -> Optional[str]:
        row = self._conn.execute(
            "SELECT entry_hash FROM ledger_entries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def append(
        self,
        event_type: str,
        payload: Dict[str, Any],
        tx_hash: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Append an immutable, chained entry. Returns the stored entry."""
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        canonical = _canonical_json(payload or {})
        with self._lock:
            # BEGIN IMMEDIATE takes the SQLite write lock (WAL mode), serializing
            # appends across ALL processes so no two writers can fork the chain.
            # The head is re-read under that lock, never trusted from memory.
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                prev_row = self._conn.execute(
                    "SELECT entry_hash FROM ledger_entries ORDER BY id DESC LIMIT 1"
                ).fetchone()
                prev = prev_row[0] if prev_row else ""
                preimage = "|".join(
                    [prev, created_at, event_type, tx_hash or "", status or "", canonical]
                )
                entry_hash = hashlib.sha256(preimage.encode("utf-8")).hexdigest()
                self._conn.execute(
                    "INSERT INTO ledger_entries (created_at, event_type, tx_hash, status, payload, prev_hash, entry_hash)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (created_at, event_type, tx_hash, status, canonical, prev, entry_hash),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            self._head = entry_hash
            entry = {
                "id": self._conn.execute("SELECT last_insert_rowid()").fetchone()[0],
                "created_at": created_at,
                "event_type": event_type,
                "tx_hash": tx_hash,
                "status": status,
                "payload": payload,
                "prev_hash": prev,
                "entry_hash": entry_hash,
            }
            # B7: enqueue for the async Postgres mirror (never blocks/fails local write).
            try:
                self._maybe_start_mirror()
                if self._mirror_thread is not None:
                    self._mirror_queue.put({**entry, "payload_canonical": canonical})
                    self._mirror_stats["queued"] += 1
            except Exception as e:
                logger.warning(f"B7: ledger mirror enqueue failed: {e}")
            return entry

    def verify_chain(self) -> Dict[str, Any]:
        """Walk every row and recompute the chain. Returns (ok, checked, first_bad)."""
        rows = self._conn.execute(
            "SELECT id, created_at, event_type, tx_hash, status, payload, prev_hash, entry_hash"
            " FROM ledger_entries ORDER BY id ASC"
        ).fetchall()
        prev = ""
        checked = 0
        for row in rows:
            (rid, created_at, event_type, tx_hash, status, payload, prev_hash, entry_hash) = row
            preimage = "|".join([prev_hash, created_at, event_type, tx_hash or "", status or "", payload])
            recomputed = hashlib.sha256(preimage.encode("utf-8")).hexdigest()
            checked += 1
            if entry_hash != recomputed or prev_hash != prev:
                return {"ok": False, "checked": checked, "first_bad": rid}
            prev = entry_hash
        return {"ok": True, "checked": checked, "first_bad": None}

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, created_at, event_type, tx_hash, status, payload, prev_hash, entry_hash"
            " FROM ledger_entries ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        out = []
        for (rid, created_at, event_type, tx_hash, status, payload, prev_hash, entry_hash) in rows:
            out.append({
                "id": rid,
                "created_at": created_at,
                "event_type": event_type,
                "tx_hash": tx_hash,
                "status": status,
                "payload": json.loads(payload),
                "prev_hash": prev_hash,
                "entry_hash": entry_hash,
            })
        return out

    def by_tx_hash(self, tx_hash: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not tx_hash:
            return []
        rows = self._conn.execute(
            "SELECT id, created_at, event_type, tx_hash, status, payload, prev_hash, entry_hash"
            " FROM ledger_entries WHERE tx_hash = ? ORDER BY id DESC LIMIT ?",
            (tx_hash, limit),
        ).fetchall()
        return [
            {
                "id": rid,
                "created_at": created_at,
                "event_type": event_type,
                "tx_hash": tx_hash_,
                "status": status,
                "payload": json.loads(payload),
                "prev_hash": prev_hash,
                "entry_hash": entry_hash,
            }
            for (rid, created_at, event_type, tx_hash_, status, payload, prev_hash, entry_hash) in rows
        ]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM ledger_entries").fetchone()[0]


# Shared singleton used by the live store.
ledger = HashChainedLedger()
