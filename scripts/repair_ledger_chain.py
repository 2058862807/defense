#!/usr/bin/env python3
"""
Repair the hash-chained ledger after concurrent-writer forks.

Root cause (now fixed in app/core/ledger.py): appends previously trusted an
in-memory head loaded once at startup, so two processes appending at once
(e.g. live server + e2e test, Aug 3 2026) forked the chain. This script
re-links every row in id order into one canonical chain. No row content
changes - only prev_hash/entry_hash are recomputed. A backup of the DB is
written first, and a REPAIR_LEDGER_CHAIN entry documents the action.

Usage:
  python scripts/repair_ledger_chain.py            # repair data/ledger.db
  python scripts/repair_ledger_chain.py --db PATH  # repair a specific db
"""
import argparse
import hashlib
import shutil
import sqlite3
import sys
import time
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/ledger.db")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"FATAL: {db_path} not found")
        return 1

    backup = str(db_path) + f".pre-repair-{int(time.time())}.bak"
    shutil.copy2(db_path, backup)
    print(f"backup written: {backup}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    rows = conn.execute(
        "SELECT id, created_at, event_type, tx_hash, status, payload, entry_hash"
        " FROM ledger_entries ORDER BY id ASC"
    ).fetchall()

    prev = ""
    changed = 0
    total = len(rows)
    for idx, (rid, created_at, event_type, tx_hash, status, payload, entry_hash) in enumerate(rows):
        preimage = "|".join([prev, created_at, event_type, tx_hash or "", status or "", payload])
        new_hash = hashlib.sha256(preimage.encode("utf-8")).hexdigest()
        if new_hash != entry_hash:
            conn.execute(
                "UPDATE ledger_entries SET prev_hash = ?, entry_hash = ? WHERE id = ?",
                (prev, new_hash, rid),
            )
            changed += 1
            if changed % 500 == 0:
                conn.commit()
                print(f"  ...{changed} rows re-chained (row id {rid})", flush=True)
        prev = new_hash
        if idx and idx % 100000 == 0:
            print(f"  ...scanned {idx}/{total}", flush=True)
    conn.commit()

    # Append a documented repair event (uses the re-linked tail as its head).
    repair_payload = {
        "action": "rechain",
        "rows_rechained": changed,
        "backup": backup,
        "reason": "concurrent-writer forks Aug 3 2026 (bug fixed in app/core/ledger.py)",
    }
    head = conn.execute(
        "SELECT entry_hash FROM ledger_entries ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    import json as _json
    canonical = _json.dumps(repair_payload, sort_keys=True, separators=(",", ":"))
    preimage = "|".join([head, created_at, "REPAIR_LEDGER_CHAIN", "", "SUCCESS", canonical])
    entry_hash = hashlib.sha256(preimage.encode("utf-8")).hexdigest()
    conn.execute(
        "INSERT INTO ledger_entries (created_at, event_type, tx_hash, status, payload, prev_hash, entry_hash)"
        " VALUES (?, 'REPAIR_LEDGER_CHAIN', NULL, 'SUCCESS', ?, ?, ?)",
        (created_at, canonical, head, entry_hash),
    )
    conn.commit()
    print(f"rows re-chained: {changed}")
    print(f"repair event:     {entry_hash[:16]}...")
    conn.close()

    print("repair complete - run 'python -m app.core.ledger --verify' or the"
          " unit suite to re-verify the chain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
