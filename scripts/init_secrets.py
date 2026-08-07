#!/usr/bin/env python3
"""
Initialize or update the local encrypted secrets store (data/secrets.enc).

AES-256-GCM at rest, unlocked by SECRETS_MASTER_KEY (>=16 chars). This gives a
single-node / air-gapped deployment the same secret-handling contract as Vault
without the Vault SaaS dependency: app.core.secrets_store.resolve_secret tries
Vault first, then this store.

Usage:
  SECRETS_MASTER_KEY='...' ENV=dev PYTHONPATH=/path/to/defense_v2 venv/bin/python scripts/init_secrets.py

  # Fresh bootstrap for a bank pilot (generates a key, replaces a stale store):
  venv/bin/python scripts/init_secrets.py --fresh --write-key-file

Secrets are taken from env vars:
  EVM_PRIVATE_KEY       -> secret/data/prod/evm-signer    {private_key}
  FLASHBOTS_SIGNING_KEY -> secret/data/prod/flashbots-auth {signing_key}

You may also pass --plaintext-file=secrets.json with a JSON map of
kv_path -> {key: value} to import arbitrary secrets:
  {
    "secret/data/prod/evm-signer":    {"private_key": "0x..."},
    "secret/data/prod/flashbots-auth": {"signing_key": "0x..."}
  }

Options:
  --fresh           Replace an existing store even if the current key cannot
                    decrypt it (stale file from an old/unknown key). Without
                    --fresh, an undecryptable store is an error.
  --write-key-file  Persist the master key to <store-dir>/.secrets_master_key
                    (0600, git-ignored) so scripts/start_stack.sh can source it.
                    For production, prefer injecting SECRETS_MASTER_KEY via
                    env / Vault / systemd EnvironmentFile instead.
"""
import argparse
import json
import os
import secrets as _secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.secrets_store import SecretsStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Init/update local encrypted secrets store")
    parser.add_argument("--plaintext-file", help="Optional JSON file: kv_path -> {key: value}")
    parser.add_argument("--store-path", default="data/secrets.enc")
    parser.add_argument("--fresh", action="store_true", help="Replace an undecryptable/stale store")
    parser.add_argument("--write-key-file", action="store_true",
                        help="Persist the master key next to the store (0600) for the local stack")
    args = parser.parse_args()

    master = os.getenv("SECRETS_MASTER_KEY")
    if not master or len(master) < 16:
        if args.fresh:
            master = _secrets.token_hex(24)
            print("[i] No SECRETS_MASTER_KEY provided; generated a fresh one.")
        else:
            print("[!] SECRETS_MASTER_KEY must be set and >= 16 characters (or pass --fresh)")
            return 1

    store = SecretsStore(path=args.store_path, master_key=master)
    store.touch()

    store_path = Path(args.store_path)
    if store_path.exists():
        probe = SecretsStore(path=args.store_path, master_key=master)
        if not probe.health()["ok"]:
            if not args.fresh:
                print(f"[!] Existing store {args.store_path} is not decryptable with this key. "
                      "Pass --fresh to replace it (any old credentials are lost).")
                return 1
            print(f"[!] Existing store is stale/undecryptable - recreating it (--fresh).")
            store_path.unlink()

    if args.write_key_file:
        key_file = store_path.parent / ".secrets_master_key"
        key_file.write_text(master + "\n")
        os.chmod(key_file, 0o600)
        print(f"[i] Master key written to {key_file} (0600, git-ignored) - start_stack.sh sources it")

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
