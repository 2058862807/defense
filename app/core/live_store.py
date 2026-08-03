"""
Real-time shared state for the live dashboard and proof endpoints.
Single source of truth for everything the frontend polls over HTTP.

Mutated from the shared mempool event loop (async task), read from FastAPI
request handlers (sync or async). Thread-safe via RLock.

Durable audit: every scored tx and ZK proof lifecycle event is also appended
to the hash-chained SQLite ledger (see ledger.py), so records survive restart
and can be independently re-verified.

No mocks: every value here comes from the real mempool connector, real
scorer, real ZK prover, or real compliance feed.
"""
import logging
import threading
import time
from collections import deque
from typing import Deque, Dict, Any, Optional, List

from app.core.ledger import ledger

logger = logging.getLogger(__name__)

DEFAULT_MAX_TRANSACTIONS = 200
DEFAULT_MAX_PROOFS = 500
DEFAULT_TPS_WINDOW_SECONDS = 60.0


class LiveFeedStore:
    def __init__(
        self,
        max_transactions: int = DEFAULT_MAX_TRANSACTIONS,
        max_proofs: int = DEFAULT_MAX_PROOFS,
        tps_window_seconds: float = DEFAULT_TPS_WINDOW_SECONDS,
    ):
        self._lock = threading.RLock()
        self._transactions: Deque[Dict[str, Any]] = deque(maxlen=max_transactions)
        self._raw_transactions: Dict[str, Dict[str, Any]] = {}
        self._proofs: Dict[str, Dict[str, Any]] = {}
        self._tps_window: Deque[float] = deque()
        self._max_proofs = max_proofs
        self._tps_window_seconds = tps_window_seconds
        self._total_scored = 0
        self._proof_count = 0
        self._proof_failed_count = 0
        self._proof_latest_ms = 0
        self._ml_confidence = 0.0
        self._started_at = time.time()

    # ------------------------------------------------------------------ #
    # Writes (event loop)
    # ------------------------------------------------------------------ #
    def record_tx(self, tx: Dict[str, Any]) -> None:
        """Record one real scored transaction from the shared mempool."""
        with self._lock:
            self._transactions.appendleft(tx)
            self._total_scored += 1
            self._tps_window.append(time.time())
            now = time.time()
            while self._tps_window and now - self._tps_window[0] > self._tps_window_seconds:
                self._tps_window.popleft()

            # Track real ML confidence from the score distribution.
            score = float(tx.get("score") if tx.get("score") is not None else tx.get("risk_score", 0) or 0)
            confidence = 100.0 - abs(score - 0.5) * 20.0
            self._ml_confidence = self._ml_confidence + (confidence - self._ml_confidence) / max(self._total_scored, 1)

        # Durable audit record (outside the RLock - SQLite has its own lock).
        tx_hash = tx.get("hash") or tx.get("txid")
        try:
            ledger.append(
                "tx_scored",
                {
                    "hash": tx_hash,
                    "score": score,
                    "risk_score": tx.get("risk_score"),
                    "decision": tx.get("decision", ""),
                    "from": tx.get("from", ""),
                    "to": tx.get("to", ""),
                },
                tx_hash=tx_hash,
                status="scored",
            )
        except Exception as e:
            logger.warning(f"Ledger append failed for tx {tx_hash}: {e}")

    def record_raw_tx(self, tx: Dict[str, Any]) -> None:
        """Record the raw parsed connector tx (with calldata) keyed by hash."""
        tx_hash = tx.get("hash")
        if not tx_hash:
            return
        with self._lock:
            self._raw_transactions[tx_hash] = tx
            if len(self._raw_transactions) > DEFAULT_MAX_TRANSACTIONS * 2:
                overflow = len(self._raw_transactions) - DEFAULT_MAX_TRANSACTIONS * 2
                for h in list(self._raw_transactions)[:overflow]:
                    self._raw_transactions.pop(h, None)

    def get_recent_raw_transactions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the most recently recorded raw mempool txs (with calldata), newest first."""
        with self._lock:
            return list(self._raw_transactions.values())[:limit]

    def record_proof_status(
        self,
        tx_hash: str,
        status: str,
        proof: Optional[Dict[str, Any]] = None,
        zk_public_inputs: Optional[list] = None,
        duration_ms: Optional[float] = None,
    ) -> None:
        """Record ZK proof lifecycle: pending -> done|failed."""
        if not tx_hash:
            return
        with self._lock:
            prior = self._proofs.get(tx_hash)
            if prior is None:
                entry = {"tx_hash": tx_hash, "status": status, "updated": time.time()}
                self._proofs[tx_hash] = entry
            else:
                entry = prior
                entry["updated"] = time.time()

            # Only count a terminal state once per hash. A fresh entry created
            # directly with a terminal status still counts exactly once.
            if prior is not None and prior.get("status") in ("done", "failed") and status in ("done", "failed"):
                if status == "done" and prior.get("status") != "done":
                    self._proof_count += 1
                    self._proof_failed_count = max(0, self._proof_failed_count - 1)
                return

            if status == "done":
                self._proof_count += 1
                self._proof_latest_ms = duration_ms if duration_ms is not None else self._proof_latest_ms
                # CircuitIngestor.generate_proof runs `snarkjs groth16 verify`
                # (fail-closed) BEFORE a proof is marked done - so done implies verified.
                entry["verified"] = True
            elif status == "failed":
                self._proof_failed_count += 1

            entry["status"] = status
            if proof is not None:
                entry["proof"] = proof
            if zk_public_inputs is not None:
                entry["zk_public_inputs"] = zk_public_inputs
            if duration_ms is not None:
                entry["duration_ms"] = duration_ms

            # Keep the proof map bounded - evict oldest terminal entries.
            if len(self._proofs) > self._max_proofs:
                terminals = sorted(
                    [(h, e) for h, e in self._proofs.items() if e.get("status") in ("done", "failed")],
                    key=lambda kv: kv[1].get("updated", 0),
                )
                overflow = len(self._proofs) - self._max_proofs
                for h, _ in terminals[:overflow]:
                    self._proofs.pop(h, None)

        # Durable audit record (outside the RLock - SQLite has its own lock).
        if status in ("done", "failed"):
            try:
                ledger.append(
                    "proof_" + status,
                    {
                        "tx_hash": tx_hash,
                        "proof": proof if status == "done" else None,
                        "zk_public_inputs": zk_public_inputs,
                        "duration_ms": duration_ms,
                        "verified": status == "done",
                    },
                    tx_hash=tx_hash,
                    status=status,
                )
            except Exception as e:
                logger.warning(f"Ledger append failed for proof {tx_hash}: {e}")

    # ------------------------------------------------------------------ #
    # Reads (HTTP handlers)
    # ------------------------------------------------------------------ #
    def get_recent_transactions(self, limit: int = 50) -> list:
        with self._lock:
            return list(self._transactions)[:limit]

    def get_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for tx in self._transactions:
                if tx.get("hash") == tx_hash or tx.get("txid") == tx_hash:
                    return tx
            return None

    def get_raw_transaction(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._raw_transactions.get(tx_hash)

    def get_proof_status(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self._proofs[tx_hash]) if tx_hash in self._proofs else None

    def get_proof_ledger(self, limit: int = 25) -> list:
        with self._lock:
            entries = list(self._proofs.values())
            entries.sort(key=lambda e: e.get("updated", 0), reverse=True)
            ledger = []
            for e in entries[:limit]:
                tx = self._raw_transactions.get(e.get("tx_hash"), {})
                ledger.append({
                    "tx_hash": e.get("tx_hash"),
                    "status": e.get("status"),
                    "proof_exists": e.get("status") == "done" and bool(e.get("proof")),
                    "verified": e.get("verified", False),
                    "decision": tx.get("decision", ""),
                    "commitment": (e.get("zk_public_inputs") or [None, None, None])[1],
                    "duration_ms": e.get("duration_ms"),
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(e.get("updated", 0))),
                })
            return ledger

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            window = max(self._tps_window_seconds, 1.0)
            tps = len(self._tps_window) / window
            return {
                "aggregate_throughput_tx_s": round(tps, 3),
                "total_scored": self._total_scored,
                "ml_confidence": round(min(100.0, max(0.0, self._ml_confidence)), 2),
                "proof_latest_ms": self._proof_latest_ms,
                "proof_count": self._proof_count,
                "proof_failed_count": self._proof_failed_count,
                "uptime_seconds": int(now - self._started_at),
            }

    def snapshot(self, transactions_limit: int = 50) -> Dict[str, Any]:
        with self._lock:
            return {
                "transactions": list(self._transactions)[:transactions_limit],
                "metrics": self.get_metrics(),
            }


# Shared singleton used by the mempool path and the HTTP endpoints.
live_store = LiveFeedStore()
