"""
Durable, atomic token metering ledger backed by SQLite (WAL).

Every customer, pilot grant, API key, token reservation and usage event is
persisted in a single SQLite database (data/metering.db). SQLite is the local
source of truth so the stack runs with zero external infrastructure; when
settings.postgres_url is set, usage events are mirrored to Postgres with
INSERT ... ON CONFLICT DO NOTHING (fail-soft, never blocks the local write).

Correctness properties (production):
  * Atomic consumption - a reservation atomically increments the grant's
    reserved count inside one transaction, so two concurrent requests can
    never overspend the fixed pilot pool.
  * Settlement - a successful analysis moves reserved tokens to consumed and
    writes an immutable usage event (chained into the audit ledger upstream).
  * Release - a failed analysis returns reserved tokens to the pool.
  * Fail-closed - expired grants, exhausted pools and revoked keys raise typed
    EntitlementError subclasses that map to HTTP 402/403/401.
"""
import hashlib
import json
import logging
import queue
import secrets
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class EntitlementError(PermissionError):
    """Base class for token/license entitlement failures (maps to HTTP 402/403)."""

    http_status = 402

    def __init__(self, message: str, grant: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.grant = grant or {}


class NoEntitlementError(EntitlementError):
    """No active grant for the key (expired, revoked, or never issued)."""

    http_status = 403


class OutOfTokensError(EntitlementError):
    """Grant is active but the fixed token pool is exhausted."""

    http_status = 402


class InsufficientTokensError(EntitlementError):
    """Not enough remaining tokens for the requested cost."""

    http_status = 402


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_key(secret: str) -> str:
    """SHA-256 of the raw API key - plaintext is never stored."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    org_type TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grants (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    tier TEXT NOT NULL,
    token_pool INTEGER NOT NULL,
    tokens_consumed INTEGER NOT NULL DEFAULT 0,
    tokens_reserved INTEGER NOT NULL DEFAULT 0,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    price_per_token_mills INTEGER NOT NULL DEFAULT 0,
    purchase_order TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grants_customer ON grants (customer_id);

CREATE TABLE IF NOT EXISTS api_keys (
    key_hash TEXT PRIMARY KEY,
    key_prefix TEXT NOT NULL,
    grant_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    name TEXT NOT NULL,
    permissions TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_api_keys_grant ON api_keys (grant_id);

CREATE TABLE IF NOT EXISTS reservations (
    id TEXT PRIMARY KEY,
    grant_id TEXT NOT NULL,
    api_key_hash TEXT NOT NULL,
    tokens INTEGER NOT NULL,
    state TEXT NOT NULL,
    endpoint TEXT,
    tx_hash TEXT,
    created_at TEXT NOT NULL,
    settled_at TEXT,
    released_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_reservations_grant ON reservations (grant_id, state);

CREATE TABLE IF NOT EXISTS usage_events (
    id TEXT PRIMARY KEY,
    grant_id TEXT NOT NULL,
    api_key_hash TEXT NOT NULL,
    reservation_id TEXT,
    event_type TEXT NOT NULL,
    endpoint TEXT,
    tx_hash TEXT,
    decision TEXT,
    score REAL,
    tokens INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    ledger_entry_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_grant_time ON usage_events (grant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_tx_hash ON usage_events (tx_hash);

CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    url TEXT NOT NULL,
    secret TEXT NOT NULL,
    events TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id TEXT PRIMARY KEY,
    webhook_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wh_deliveries_webhook ON webhook_deliveries (webhook_id);
"""


class MeteringStore:
    """Atomic token metering store. One instance per process (thread-safe)."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or settings.metering_db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        self._mirror_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._mirror_thread: Optional[threading.Thread] = None
        self._mirror_mutex = threading.Lock()
        self._mirror_stats = {"queued": 0, "mirrored": 0, "failed": 0, "last_error": None}

    # ------------------------------------------------------------------ #
    # Postgres mirror (fail-soft) - usage events only.
    # ------------------------------------------------------------------ #
    def _maybe_start_mirror(self) -> None:
        if self._mirror_thread is not None:
            return
        with self._mirror_mutex:
            if self._mirror_thread is not None:
                return
            if not settings.postgres_url:
                return
            self._mirror_thread = threading.Thread(
                target=self._mirror_worker, daemon=True, name="metering-pg-mirror"
            )
            self._mirror_thread.start()
            logger.info(f"Postgres metering mirror started (table={settings.postgres_usage_table})")

    def _mirror_worker(self) -> None:
        import psycopg2
        from psycopg2 import sql

        backoff = 1.0
        while True:
            ev = self._mirror_queue.get()
            try:
                conn = psycopg2.connect(settings.postgres_url.get_secret_value(), connect_timeout=5)
                try:
                    conn.cursor().execute(sql.SQL(
                        "CREATE TABLE IF NOT EXISTS {t} ("
                        " id TEXT PRIMARY KEY, grant_id TEXT, api_key_hash TEXT, reservation_id TEXT,"
                        " event_type TEXT, endpoint TEXT, tx_hash TEXT, decision TEXT, score REAL,"
                        " tokens INTEGER, created_at TEXT, ledger_entry_hash TEXT)"
                    ).format(t=sql.Identifier(settings.postgres_usage_table)))
                    conn.cursor().execute(sql.SQL(
                        "INSERT INTO {t} (id, grant_id, api_key_hash, reservation_id, event_type, endpoint,"
                        " tx_hash, decision, score, tokens, created_at, ledger_entry_hash)"
                        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING"
                    ).format(t=sql.Identifier(settings.postgres_usage_table)), (
                        ev["id"], ev["grant_id"], ev["api_key_hash"], ev["reservation_id"],
                        ev["event_type"], ev["endpoint"], ev["tx_hash"], ev["decision"],
                        ev["score"], ev["tokens"], ev["created_at"], ev["ledger_entry_hash"],
                    ))
                    conn.commit()
                finally:
                    conn.close()
                self._mirror_stats["mirrored"] += 1
                backoff = 1.0
            except Exception as e:
                self._mirror_stats["failed"] += 1
                self._mirror_stats["last_error"] = str(e)[:300]
                logger.warning(f"Metering Postgres mirror insert failed, retrying in {backoff:.0f}s: {e}")
                self._mirror_queue.put(ev)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
            finally:
                self._mirror_queue.task_done()

    def mirror_stats(self) -> Dict[str, Any]:
        return dict(self._mirror_stats)

    # ------------------------------------------------------------------ #
    # Customers / grants
    # ------------------------------------------------------------------ #
    def register_customer(
        self,
        name: str,
        email: Optional[str] = None,
        org_type: str = "credit_union",
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        cid = customer_id or f"cus_{secrets.token_hex(8)}"
        created = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO customers (id, name, email, org_type, status, created_at)"
                " VALUES (?, ?, ?, ?, 'active', ?)",
                (cid, name, email, org_type, created),
            )
            self._conn.commit()
        return {"id": cid, "name": name, "email": email, "org_type": org_type, "status": "active"}

    def get_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT id, name, email, org_type, status, created_at FROM customers WHERE id = ?",
            (customer_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "name": row[1], "email": row[2],
            "org_type": row[3], "status": row[4], "created_at": row[5],
        }

    def get_customer_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up the most recently registered customer with the given name."""
        row = self._conn.execute(
            "SELECT id, name, email, org_type, status, created_at FROM customers"
            " WHERE name = ? ORDER BY created_at DESC LIMIT 1",
            (name,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "name": row[1], "email": row[2],
            "org_type": row[3], "status": row[4], "created_at": row[5],
        }

    def issue_grant(
        self,
        customer_id: str,
        token_pool: int,
        expires_at: str,
        kind: str = "pilot",
        tier: str = "pilot",
        currency: str = "USD",
        price_per_token_mills: int = 0,
        purchase_order: Optional[str] = None,
    ) -> Dict[str, Any]:
        gid = f"grant_{secrets.token_hex(8)}"
        created = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO grants (id, customer_id, kind, tier, token_pool, tokens_consumed,"
                " tokens_reserved, issued_at, expires_at, status, currency, price_per_token_mills,"
                " purchase_order, created_at) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?, 'active', ?, ?, ?, ?)",
                (gid, customer_id, kind, tier, token_pool, created, expires_at, currency,
                 price_per_token_mills, purchase_order, created),
            )
            self._conn.commit()
        return self.get_grant(gid)

    def issue_pilot_grant(
        self,
        customer_id: str,
        token_pool: Optional[int] = None,
        months: Optional[int] = None,
        tier: str = "pilot",
    ) -> Dict[str, Any]:
        pool = token_pool if token_pool is not None else settings.metering_pilot_token_pool
        months = months if months is not None else settings.metering_pilot_months
        expires = datetime.now(timezone.utc) + timedelta(days=months * 30)
        return self.issue_grant(
            customer_id=customer_id,
            token_pool=pool,
            expires_at=expires.isoformat(),
            kind="pilot",
            tier=tier,
        )

    def get_grant(self, grant_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT id, customer_id, kind, tier, token_pool, tokens_consumed, tokens_reserved,"
            " issued_at, expires_at, status, currency, price_per_token_mills, purchase_order, created_at"
            " FROM grants WHERE id = ?",
            (grant_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "customer_id": row[1], "kind": row[2], "tier": row[3],
            "token_pool": row[4], "tokens_consumed": row[5], "tokens_reserved": row[6],
            "issued_at": row[7], "expires_at": row[8], "status": row[9],
            "currency": row[10], "price_per_token_mills": row[11],
            "purchase_order": row[12], "created_at": row[13],
        }

    def get_grant_by_purchase_order(self, purchase_order: str) -> Optional[Dict[str, Any]]:
        """Resolve a grant by its purchase_order reference (legacy license_id)."""
        row = self._conn.execute(
            "SELECT id FROM grants WHERE purchase_order = ?", (purchase_order,)
        ).fetchone()
        return self.get_grant(row[0]) if row else None

    def renew_grant(self, purchase_order: str, new_expires_at: str) -> Dict[str, Any]:
        """Extend a grant's expiry (license renewal). Fail-closed if missing."""
        grant = self.get_grant_by_purchase_order(purchase_order)
        if not grant:
            raise KeyError(f"no grant for license {purchase_order}")
        with self._lock:
            self._conn.execute(
                "UPDATE grants SET expires_at = ?, status = 'active' WHERE id = ?",
                (new_expires_at, grant["id"]),
            )
            self._conn.commit()
        return self.get_grant(grant["id"])

    def list_keys(self, customer_id: Optional[str] = None, grant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List active API keys (metadata only - hashes/prefixes, never plaintext)."""
        where, args = [], []
        if customer_id:
            where.append("customer_id = ?")
            args.append(customer_id)
        if grant_id:
            where.append("grant_id = ?")
            args.append(grant_id)
        sql = "SELECT key_hash, key_prefix, grant_id, customer_id, name, permissions, created_at, revoked_at FROM api_keys"
        if where:
            sql += " WHERE " + " AND ".join(where)
        rows = self._conn.execute(sql, tuple(args)).fetchall()
        return [
            {
                "key_hash": r[0][:16] + "...", "key_prefix": r[1], "grant_id": r[2],
                "customer_id": r[3], "name": r[4], "permissions": json.loads(r[5]),
                "created_at": r[6], "revoked_at": r[7],
            }
            for r in rows
        ]

    def list_grants(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if customer_id:
            rows = self._conn.execute(
                "SELECT id FROM grants WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT id FROM grants ORDER BY created_at DESC").fetchall()
        return [self.get_grant(r[0]) for r in rows]

    def grant_balance(self, grant_id: str) -> Dict[str, Any]:
        grant = self.get_grant(grant_id)
        if not grant:
            return {"error": "grant not found"}
        remaining = max(0, grant["token_pool"] - grant["tokens_consumed"] - grant["tokens_reserved"])
        return {
            "grant_id": grant_id,
            "customer_id": grant["customer_id"],
            "tier": grant["tier"],
            "status": grant["status"],
            "token_pool": grant["token_pool"],
            "tokens_consumed": grant["tokens_consumed"],
            "tokens_reserved": grant["tokens_reserved"],
            "tokens_remaining": remaining,
            "expires_at": grant["expires_at"],
            "expired": datetime.now(timezone.utc) > _parse_iso(grant["expires_at"]),
        }

    def mark_paid(self, grant_id: str, purchase_order: str, added_tokens: int = 0) -> Dict[str, Any]:
        """Transition a pilot grant to paid; optionally top up the token pool."""
        with self._lock:
            grant = self.get_grant(grant_id)
            if not grant:
                raise KeyError(f"grant {grant_id} not found")
            new_pool = grant["token_pool"] + added_tokens
            self._conn.execute(
                "UPDATE grants SET status = 'paid', purchase_order = ?, token_pool = ?, kind = 'paid'"
                " WHERE id = ?",
                (purchase_order, new_pool, grant_id),
            )
            self._conn.commit()
        return self.get_grant(grant_id)

    # ------------------------------------------------------------------ #
    # API keys
    # ------------------------------------------------------------------ #
    def create_api_key(
        self, customer_id: str, grant_id: str, name: str, permissions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        grant = self.get_grant(grant_id)
        if not grant or grant["customer_id"] != customer_id:
            raise ValueError("grant does not belong to customer")
        raw = f"pk_live_{secrets.token_urlsafe(32)}"
        prefix = raw[:16] + "..."
        key_hash = _hash_key(raw)
        perms = permissions or ["analyze", "compliance"]
        with self._lock:
            self._conn.execute(
                "INSERT INTO api_keys (key_hash, key_prefix, grant_id, customer_id, name, permissions,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (key_hash, prefix, grant_id, customer_id, name, json.dumps(perms), _now()),
            )
            self._conn.commit()
        return {"api_key": raw, "key_prefix": prefix, "grant_id": grant_id, "customer_id": customer_id}

    def verify_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        key_hash = _hash_key(api_key)
        row = self._conn.execute(
            "SELECT key_hash, key_prefix, grant_id, customer_id, name, permissions, created_at, revoked_at"
            " FROM api_keys WHERE key_hash = ?",
            (key_hash,),
        ).fetchone()
        if not row or row[7]:
            return None
        return {
            "key_hash": row[0], "key_prefix": row[1], "grant_id": row[2],
            "customer_id": row[3], "name": row[4], "permissions": json.loads(row[5]),
            "created_at": row[6], "revoked_at": row[7],
        }

    def revoke_api_key(self, key_prefix: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE key_prefix = ?", (_now(), key_prefix)
            )
            self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------ #
    # Reservations (atomic token consumption)
    # ------------------------------------------------------------------ #
    def _load_grant(self, grant_id: str) -> Optional[Dict[str, Any]]:
        return self.get_grant(grant_id)

    def authorize_reservation(
        self,
        api_key: str,
        endpoint: str,
        tokens: int = 1,
        tx_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically reserve `tokens` from the grant backing the API key.

        Raises NoEntitlementError (invalid/expired/revoked), OutOfTokensError
        (pool exhausted) or InsufficientTokensError (pool too small). Returns a
        reservation dict on success.
        """
        key = self.verify_api_key(api_key)
        if not key:
            raise NoEntitlementError("Unknown or revoked API key", {"status": "no_key"})

        with self._lock:
            grant = self.get_grant(key["grant_id"])
            if not grant or grant["status"] not in ("active", "paid"):
                raise NoEntitlementError("No active grant for this API key", grant or {})
            if datetime.now(timezone.utc) > _parse_iso(grant["expires_at"]):
                raise OutOfTokensError("Grant has expired", grant)

            # Zero-cost reservations are pure authentication (entitlement reads,
            # webhook management) - they never consume or block on exhaustion.
            if tokens > 0:
                used = grant["tokens_consumed"] + grant["tokens_reserved"]
                if used >= grant["token_pool"]:
                    raise OutOfTokensError("Token pool exhausted", grant)
                if used + tokens > grant["token_pool"]:
                    raise InsufficientTokensError("Insufficient tokens remaining", grant)

            rid = f"res_{secrets.token_hex(10)}"
            self._conn.execute(
                "UPDATE grants SET tokens_reserved = tokens_reserved + ? WHERE id = ?",
                (tokens, grant["id"]),
            )
            self._conn.execute(
                "INSERT INTO reservations (id, grant_id, api_key_hash, tokens, state, endpoint, tx_hash,"
                " created_at) VALUES (?, ?, ?, ?, 'reserved', ?, ?, ?)",
                (rid, grant["id"], key["key_hash"], tokens, endpoint, tx_hash, _now()),
            )
            self._conn.commit()
            refreshed = self.get_grant(grant["id"])

        return {
            "reservation_id": rid,
            "grant_id": grant["id"],
            "customer_id": key["customer_id"],
            "key_hash": key["key_hash"],
            "key_prefix": key["key_prefix"],
            "tier": grant["tier"],
            "tokens": tokens,
            "endpoint": endpoint,
            "tx_hash": tx_hash,
            "grant": refreshed,
            "tokens_remaining": max(0, refreshed["token_pool"] - refreshed["tokens_consumed"] - refreshed["tokens_reserved"]),
        }

    def settle_reservation(
        self,
        reservation_id: str,
        event_type: str = "tx_analysis",
        decision: Optional[str] = None,
        score: Optional[float] = None,
        ledger_entry_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Move a reservation to consumed and record the usage event."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, grant_id, api_key_hash, tokens, state FROM reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"reservation {reservation_id} not found")
            if row[4] != "reserved":
                return {"reservation_id": reservation_id, "state": row[4], "already": True}

            now = _now()
            self._conn.execute(
                "UPDATE reservations SET state = 'settled', settled_at = ? WHERE id = ?",
                (now, reservation_id),
            )
            self._conn.execute(
                "UPDATE grants SET tokens_consumed = tokens_consumed + ?, tokens_reserved = tokens_reserved - ?"
                " WHERE id = ?",
                (row[3], row[3], row[1]),
            )
            ev = {
                "id": f"evt_{secrets.token_hex(10)}",
                "grant_id": row[1],
                "api_key_hash": row[2],
                "reservation_id": reservation_id,
                "event_type": event_type,
                "endpoint": self._conn.execute(
                    "SELECT endpoint FROM reservations WHERE id = ?", (reservation_id,)
                ).fetchone()[0],
                "tx_hash": self._conn.execute(
                    "SELECT tx_hash FROM reservations WHERE id = ?", (reservation_id,)
                ).fetchone()[0],
                "decision": decision,
                "score": score,
                "tokens": row[3],
                "created_at": now,
                "ledger_entry_hash": ledger_entry_hash,
            }
            self._conn.execute(
                "INSERT INTO usage_events (id, grant_id, api_key_hash, reservation_id, event_type, endpoint,"
                " tx_hash, decision, score, tokens, created_at, ledger_entry_hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ev["id"], ev["grant_id"], ev["api_key_hash"], ev["reservation_id"], ev["event_type"],
                 ev["endpoint"], ev["tx_hash"], ev["decision"], ev["score"], ev["tokens"],
                 ev["created_at"], ev["ledger_entry_hash"]),
            )
            self._conn.commit()
            refreshed = self.get_grant(row[1])

        ev["tokens_remaining"] = max(
            0, refreshed["token_pool"] - refreshed["tokens_consumed"] - refreshed["tokens_reserved"]
        )
        try:
            self._maybe_start_mirror()
            if self._mirror_thread is not None:
                self._mirror_queue.put(ev)
                self._mirror_stats["queued"] += 1
        except Exception as e:
            logger.warning(f"Metering mirror enqueue failed: {e}")
        return ev

    def release_reservation(self, reservation_id: str) -> Dict[str, Any]:
        """Return reserved tokens to the pool (processing failed)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, grant_id, tokens, state FROM reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"reservation {reservation_id} not found")
            if row[3] != "reserved":
                return {"reservation_id": reservation_id, "state": row[3], "already": True}
            now = _now()
            self._conn.execute(
                "UPDATE reservations SET state = 'released', released_at = ? WHERE id = ?",
                (now, reservation_id),
            )
            self._conn.execute(
                "UPDATE grants SET tokens_reserved = tokens_reserved - ? WHERE id = ?",
                (row[2], row[1]),
            )
            self._conn.commit()
            refreshed = self.get_grant(row[1])
        return {
            "reservation_id": reservation_id,
            "state": "released",
            "tokens_returned": row[2],
            "tokens_remaining": max(0, refreshed["token_pool"] - refreshed["tokens_consumed"] - refreshed["tokens_reserved"]),
        }

    # ------------------------------------------------------------------ #
    # Webhook registrations
    # ------------------------------------------------------------------ #
    def register_webhook(
        self, customer_id: str, url: str, events: List[str], secret: Optional[str] = None
    ) -> Dict[str, Any]:
        wid = f"wh_{secrets.token_hex(8)}"
        wh_secret = secret or secrets.token_hex(32)
        with self._lock:
            self._conn.execute(
                "INSERT INTO webhooks (id, customer_id, url, secret, events, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, 'active', ?)",
                (wid, customer_id, url, wh_secret, json.dumps(events), _now()),
            )
            self._conn.commit()
        return {"id": wid, "customer_id": customer_id, "url": url, "events": events, "secret": wh_secret}

    def list_webhooks(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if customer_id:
            rows = self._conn.execute(
                "SELECT id, customer_id, url, events, status, created_at FROM webhooks"
                " WHERE customer_id = ? ORDER BY created_at DESC",
                (customer_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, customer_id, url, events, status, created_at FROM webhooks ORDER BY created_at DESC"
            ).fetchall()
        out = []
        for (wid, cid, url, events, status, created) in rows:
            out.append({"id": wid, "customer_id": cid, "url": url, "events": json.loads(events), "status": status, "created_at": created})
        return out

    def get_webhook(self, webhook_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT id, customer_id, url, secret, events, status, created_at FROM webhooks WHERE id = ?",
            (webhook_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": row[0], "customer_id": row[1], "url": row[2], "secret": row[3],
            "events": json.loads(row[4]), "status": row[5], "created_at": row[6],
        }

    def record_webhook_delivery(self, webhook_id: str, event_type: str, payload_hash: str, status: str, attempt: int, last_error: Optional[str] = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO webhook_deliveries (id, webhook_id, event_type, payload_hash, status,"
                " attempt, last_error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"whd_{secrets.token_hex(10)}", webhook_id, event_type, payload_hash, status, attempt, last_error, _now()),
            )
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Usage queries + audit commitment
    # ------------------------------------------------------------------ #
    def usage_for_grant(self, grant_id: str, since: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        if since:
            rows = self._conn.execute(
                "SELECT id, grant_id, api_key_hash, reservation_id, event_type, endpoint, tx_hash, decision,"
                " score, tokens, created_at, ledger_entry_hash FROM usage_events"
                " WHERE grant_id = ? AND created_at >= ? ORDER BY created_at DESC LIMIT ?",
                (grant_id, since, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, grant_id, api_key_hash, reservation_id, event_type, endpoint, tx_hash, decision,"
                " score, tokens, created_at, ledger_entry_hash FROM usage_events"
                " WHERE grant_id = ? ORDER BY created_at DESC LIMIT ?",
                (grant_id, limit),
            ).fetchall()
        return [
            {
                "id": r[0], "grant_id": r[1], "api_key_hash": r[2][:16] + "...", "reservation_id": r[3],
                "event_type": r[4], "endpoint": r[5], "tx_hash": r[6], "decision": r[7],
                "score": r[8], "tokens": r[9], "created_at": r[10], "ledger_entry_hash": r[11],
            }
            for r in rows
        ]

    def period_usage(self, since: str) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, grant_id, tokens, decision, score, created_at FROM usage_events WHERE created_at >= ?",
            (since,),
        ).fetchall()
        return [
            {"id": r[0], "grant_id": r[1], "tokens": r[2], "decision": r[3], "score": r[4], "created_at": r[5]}
            for r in rows
        ]

    def all_usage(self, since: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
        if since:
            rows = self._conn.execute(
                "SELECT id, grant_id, api_key_hash, reservation_id, event_type, endpoint, tx_hash, decision,"
                " score, tokens, created_at, ledger_entry_hash FROM usage_events"
                " WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
                (since, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, grant_id, api_key_hash, reservation_id, event_type, endpoint, tx_hash, decision,"
                " score, tokens, created_at, ledger_entry_hash FROM usage_events"
                " ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0], "grant_id": r[1], "api_key_hash": r[2][:16] + "...", "reservation_id": r[3],
                "event_type": r[4], "endpoint": r[5], "tx_hash": r[6], "decision": r[7],
                "score": r[8], "tokens": r[9], "created_at": r[10], "ledger_entry_hash": r[11],
            }
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# Shared singleton used across the API.
metering_store = MeteringStore()
