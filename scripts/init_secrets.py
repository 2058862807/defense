#!/usr/bin/env python3
"""
Initialize or update the local encrypted secrets store (data/secrets.enc).

AES-256-GCM at rest, unlocked by SECRETS_MASTER_KEY (>=16 chars). This gives a
single-node / air-gapped deployment the same secret-handling contract as Vault
without the Vault SaaS dependency: app.core.secrets_store.resolve_secret tries
Vault first, then this store.

Usage:
  SECRETS_MASTER_KEY='...' ENV=dev PYTHONPATH=/path/to/defense_v2 venv/bin/python scripts/init_secrets.py

Secrets are taken from env vars:
  EVM_PRIVATE_KEY       -> secret/data/prod/evm-signer    {private_key}
  FLASHBOTS_SIGNING_KEY -> secret/data/prod/flashbots-auth {signing_key}

You may also pass --plaintext-file=secrets.json with a JSON map of
kv_path -> {key: value} to import arbitrary secrets:
  {
    "secret/data/prod/evm-signer":    {"private_key": "0x..."},
    "secret/data/prod/flashbots-auth": {"signing_key": "0x..."}
  }
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.secrets_store import SecretsStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Init/update local encrypted secrets store")
    parser.add_argument("--plaintext-file", help="Optional JSON file: kv_path -> {key: value}")
    parser.add_argument("--store-path", default="data/secrets.enc")
    args = parser.parse_args()

    master = os.getenv("SECRETS_MASTER_KEY")
    if not master or len(master) < 16:
        print("[!] SECRETS_MASTER_KEY must be set and >= 16 characters")
        return 1

    store = SecretsStore(path=args.store_path, master_key=master)

    imported = {}
    if args.plaintext_file:
        with open(args.plaintext_file) as f:
            imported = json.load(f)

    added = 0
    for path, secret in imported.items():
        store.set(path, secret)
        added += 1

    evm_key = os.getenv("EVM_PRIVATE_KEY")
    if evm_key:
        store.set("secret/data/prod/evm-signer", {"private_key": evm_key})
        added += 1
        evm_key = None  # don't keep plaintext reference

    flashbots_key = os.getenv("FLASHBOTS_SIGNING_KEY")
    if flashbots_key:
        store.set("secret/data/prod/flashbots-auth", {"signing_key": flashbots_key})
        added += 1

    print(f"Secrets store updated at {args.store_path}: {added} secret(s) imported")
    print(f"Paths present: {store.list_paths()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
