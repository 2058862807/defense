#!/usr/bin/env python3
"""
Rotate EVM / Flashbots signer keys across every secret store this stack uses.

Rotation contract (never prints key material; addresses and fingerprints only):
  1. Generate a fresh keypair via eth_account.Account.create() (CSPRNG).
  2. ENCRYPTED ARCHIVE of the retired key FIRST - written to the AES-256-GCM
     local secrets store (data/secrets.enc under SECRETS_MASTER_KEY) at
     secret/rotate/archive/<field>/<utc_timestamp>. A rotation that cannot
     archive the old key fails closed and touches nothing.
  3. Plaintext backup of data/local_secrets.env (0600) for rollback.
  4. Rewrite data/local_secrets.env (EVM_PRIVATE_KEY / FLASHBOTS_SIGNING_KEY),
     preserving comments and unrelated lines.
  5. Update the pilot credential store (pilot/credentials) so runtime
     resolution that falls through to the encrypted store sees the new key.
  6. Optional Vault update (--vault) at secret/data/prod/flashbots-auth and
     secret/data/prod/evm-signer.
  7. Append a SIGNER_ROTATE entry to the hash-chained proof ledger
     (old_address -> new_address; never key material).

Safety guards:
  - EVM key rotation is REJECTED unless --accept-evm-timing is passed. The
    EVM key currently owns the live FairnessRegistry and is its authorized
    submitter; rotating it before the governance migration would break the
    migration's old-registry freeze and de-authorize the bot. Run the
    migration first with --submitter <new address>, THEN rotate.
    If --rpc-url and --registry are given, the tool verifies on-chain
    ownership and only then allows --rotate-evm without the override.
  - The Flashbots signing key is split from the EVM gas wallet: the new
    Flashbots address is asserted different from the EVM key address. This
    is off-chain relay auth (X-Flashbots-Signature) with no on-chain state,
    so it can be rotated any time.

Usage:
  # Dry run (validates, prints plan, writes nothing):
  python scripts/rotate_signer_keys.py --rotate-flashbots --dry-run

  # Rotate the Flashbots signing key (live):
  python scripts/rotate_signer_keys.py --rotate-flashbots --yes

  # Rotate both (requires the timing override - only post-migration):
  python scripts/rotate_signer_keys.py --rotate-flashbots --rotate-evm \
      --accept-evm-timing --yes

Master key for the encrypted store comes from SECRETS_MASTER_KEY or
data/.secrets_master_key (0600, git-ignored, sourced by start_stack.sh).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
LOCAL_SECRETS = ROOT / "data" / "local_secrets.env"
MASTER_KEY_FILE = ROOT / "data" / ".secrets_master_key"
STORE_PATH = ROOT / "data" / "secrets.enc"
DEFAULT_BACKUP_DIR = ROOT / "data" / "rotations"

FIELD_FLASHBOTS = "flashbots_signing_key"
FIELD_EVM = "evm_private_key"
FLASHBOTS_KV = "secret/data/prod/flashbots-auth"
EVM_KV = "secret/data/prod/evm-signer"


def _log(msg: str) -> None:
    print(msg, flush=True)


def resolve_master_key() -> str:
    master = os.getenv("SECRETS_MASTER_KEY")
    if master:
        return master
    if MASTER_KEY_FILE.exists():
        return MASTER_KEY_FILE.read_text().strip()
    return ""


def load_env_file(path: Path) -> dict:
    data = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                data[k.strip()] = v.strip()
    return data


def write_env_file(path: Path, updates: dict, reason: str) -> None:
    """Rewrite an env file, preserving comments/order, updating given keys."""
    text = path.read_text() if path.exists() else ""
    lines = text.splitlines() if text else []
    replaced = set()
    out = []
    for line in lines:
        stripped = line.strip()
        matched = None
        for key in updates:
            if stripped.startswith(key + "=") or stripped == key:
                matched = key
                break
        if matched:
            out.append(f"{matched}={updates[matched]}")
            replaced.add(matched)
        else:
            out.append(line)
    for key, val in updates.items():
        if key not in replaced:
            if out and out[-1].strip() != "":
                out.append("")
            out.append(f"{key}={val}")
    path.write_text("\n".join(out) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    _log(f"  local_secrets.env: updated {sorted(updates)} ({reason})")


def account_from_key(key: str):
    from eth_account import Account

    key = key.strip()
    if not key.startswith("0x"):
        key = "0x" + key
    if len(key) != 66:
        raise ValueError("private key must be 32 bytes hex (0x + 64 chars)")
    return Account.from_key(key)


def vault_kv_write(path: str, payload: dict) -> None:
    """Update a HashiCorp Vault KV v2 secret. Raises on any failure."""
    from app.core.security import get_vault_client

    vault_addr = os.getenv("VAULT_ADDR")
    role_id = os.getenv("VAULT_ROLE_ID")
    secret_id = os.getenv("VAULT_SECRET_ID")
    if not (vault_addr and role_id and secret_id):
        raise RuntimeError("VAULT_ADDR/VAULT_ROLE_ID/VAULT_SECRET_ID not set")
    client = get_vault_client(vault_addr, role_id, secret_id)
    mount, _, kv_key = path.partition("secret/data/")
    client.secrets.kv.v2.create_or_update_secret(
        path=kv_key, secret=payload, mount_point="secret"
    )
    _log(f"  vault: updated {path}")


def onchain_owner(rpc_url: str, registry: str) -> str:
    """Return the current owner of the FairnessRegistry, or raise."""
    from web3 import Web3

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        raise RuntimeError(f"RPC not reachable: {rpc_url}")
    # owner() is the 0th function of the inherited Ownable ABI.
    abi = [{
        "constant": True,
        "inputs": [],
        "name": "owner",
        "outputs": [{"name": "", "type": "address"}],
        "type": "function",
    }]
    contract = w3.eth.contract(address=Web3.to_checksum_address(registry), abi=abi)
    return contract.functions.owner().call()


def append_ledger(payload: dict) -> None:
    from app.core.ledger import ledger

    ledger.append("SIGNER_ROTATE", payload, status="SUCCESS")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rotate-flashbots", action="store_true", help="rotate the Flashbots relay auth signing key")
    ap.add_argument("--rotate-evm", action="store_true", help="rotate the EVM gas wallet / tx signer key")
    ap.add_argument("--accept-evm-timing", action="store_true",
                    help="bypass the EVM pre-migration guard (only after governance migration)")
    ap.add_argument("--dry-run", action="store_true", help="validate + print plan, write nothing")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    ap.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR), help="dir for the plaintext env backup")
    ap.add_argument("--vault", action="store_true", help="also update HashiCorp Vault")
    ap.add_argument("--rpc-url", default=os.getenv("MAINNET_RPC_URL"), help="RPC for on-chain ownership check")
    ap.add_argument("--registry", default=os.getenv("FAIRNESS_REGISTRY_ADDRESS"), help="registry address for ownership check")
    ap.add_argument("--out", default=str(ROOT / "data" / "signer_rotation.json"), help="addresses-only result JSON")
    args = ap.parse_args()

    want_evm = args.rotate_evm
    want_fb = args.rotate_flashbots
    if not want_evm and not want_fb:
        _log("Nothing to do: pass --rotate-evm and/or --rotate-flashbots.")
        return 1

    master = resolve_master_key()
    if not master:
        _log("FATAL: SECRETS_MASTER_KEY not set and no data/.secrets_master_key found - "
             "cannot archive the retired key. Rotation aborted (fail-closed).")
        return 1

    from app.core.secrets_store import SecretsStore
    from eth_account import Account

    store = SecretsStore(path=str(STORE_PATH), master_key=master)
    if not store.health()["ok"]:
        _log(f"FATAL: encrypted secrets store {STORE_PATH} not decryptable with the master key. "
             "Cannot archive the retired key. Rotation aborted (fail-closed).")
        return 1

    env = load_env_file(LOCAL_SECRETS)
    old_evm = env.get("EVM_PRIVATE_KEY")
    old_fb = env.get("FLASHBOTS_SIGNING_KEY")
    if want_evm and not old_evm:
        _log("FATAL: EVM_PRIVATE_KEY not found in local_secrets.env")
        return 1
    if want_fb and not old_fb:
        _log("FATAL: FLASHBOTS_SIGNING_KEY not found in local_secrets.env")
        return 1

    old_evm_addr = account_from_key(old_evm).address if old_evm else None
    old_fb_addr = account_from_key(old_fb).address if old_fb else None

    # Optional on-chain ownership guard for EVM rotation.
    if want_evm and args.rpc_url and args.registry:
        try:
            owner = onchain_owner(args.rpc_url, args.registry)
        except Exception as e:
            _log(f"WARN: on-chain ownership check failed ({e}); not treating it as a green light.")
            owner = None
        if owner is not None:
            moved = owner.lower() != old_evm_addr.lower()
            _log(f"registry owner now: {owner} (current EVM key {old_evm_addr}) -> "
                 f"{'ownership moved, EVM rotation is safe' if moved else 'still owns registry'}")
            if moved:
                args.accept_evm_timing = True

    if want_evm and not args.accept_evm_timing:
        _log(
            "REFUSING EVM KEY ROTATION.\n"
            "  The EVM key currently owns the live FairnessRegistry and is its authorized\n"
            "  submitter. Rotating it before the governance migration would break the\n"
            "  migration's old-registry freeze (setPaused is owner-only) and de-authorize\n"
            "  the bot. Sequence:\n"
            "    1. Run scripts/migrate_registry_governance.py --execute\n"
            "       --submitter <new-address> with the OLD key still in place.\n"
            "    2. Once the new registry is owned by the timelock and the old registry is\n"
            "       frozen, re-run with --rotate-evm --accept-evm-timing.\n"
            "  If --rpc-url + --registry are provided and on-chain ownership has already\n"
            "  moved off the current key, the guard is bypassed automatically.\n"
        )
        return 1

    # ---- generate new keys ----
    new_evm = Account.create() if want_evm else None
    new_fb = Account.create() if want_fb else None
    if new_evm and old_evm_addr and new_evm.address.lower() == old_evm_addr.lower():
        _log("FATAL: generated EVM key is identical to the current one; aborting (retry).")
        return 1
    if new_fb and old_fb_addr and new_fb.address.lower() == old_fb_addr.lower():
        _log("FATAL: generated Flashbots key is identical to the current one; aborting (retry).")
        return 1
    # Split identity: Flashbots auth signer must never be the gas wallet.
    if new_fb is not None:
        evm_ref = new_evm.address if new_evm is not None else old_evm_addr
        if evm_ref and new_fb.address.lower() == evm_ref.lower():
            _log("FATAL: Flashbots signing key would collide with the EVM gas wallet address; "
                 "split identity violated. Aborting (retry).")
            return 1

    updates = {}
    if new_evm is not None:
        updates["EVM_PRIVATE_KEY"] = "0x" + new_evm.key.hex()
    if new_fb is not None:
        updates["FLASHBOTS_SIGNING_KEY"] = "0x" + new_fb.key.hex()

    _log(f"local secrets source : {LOCAL_SECRETS}")
    if old_evm_addr:
        _log(f"EVM key        old : {old_evm_addr}")
    if old_fb_addr:
        _log(f"Flashbots key  old : {old_fb_addr}")
    if new_evm is not None:
        _log(f"EVM key        new : {new_evm.address}")
    if new_fb is not None:
        _log(f"Flashbots key  new : {new_fb.address}")
    _log(f"backup dir         : {args.backup_dir}")
    _log(f"vault update       : {args.vault}")

    if args.dry_run:
        _log("\nDRY RUN - nothing was written; prospective addresses shown above.")
        return 0

    if not args.yes:
        if input("Type YES to rotate these keys: ") != "YES":
            _log("aborted")
            return 1

    # ---- 1. encrypted archive of retired keys (fail-closed if it errors) ----
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    archives = []
    for field, old_key, kv_path in (
        (FIELD_EVM, old_evm if new_evm is not None else None, EVM_KV),
        (FIELD_FLASHBOTS, old_fb if new_fb is not None else None, FLASHBOTS_KV),
    ):
        if old_key is None:
            continue
        arc_path = f"secret/rotate/archive/{field}/{ts}"
        store.set(arc_path, {
            "private_key": old_key,
            "rotated_at": ts,
            "address": account_from_key(old_key).address,
            "rotated_from": kv_path,
            "reason": f"signer key rotation {ts}",
        })
        archives.append(arc_path)
        _log(f"  archived retired {field} key -> {arc_path} (AES-256-GCM)")

    # ---- 2. plaintext env backup for rollback ----
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"local_secrets_{ts}.env"
    if LOCAL_SECRETS.exists():
        backup_path.write_text(LOCAL_SECRETS.read_text())
        os.chmod(backup_path, 0o600)
        _log(f"  backed up local_secrets.env -> {backup_path}")

    # ---- 3. rewrite local_secrets.env ----
    write_env_file(LOCAL_SECRETS, updates, "rotation")

    # ---- 4. pilot credential store ----
    try:
        from app.core.pilot_secrets import PilotSecretsStore
        pstore = PilotSecretsStore(store=store)
        if new_evm is not None:
            pstore.set(FIELD_EVM, "0x" + new_evm.key.hex())
            _log(f"  pilot store: {FIELD_EVM} updated")
        if new_fb is not None:
            pstore.set(FIELD_FLASHBOTS, "0x" + new_fb.key.hex())
            _log(f"  pilot store: {FIELD_FLASHBOTS} updated")
    except Exception as e:
        _log(f"WARN: pilot store update failed (rollback): {e}")
        write_env_file(LOCAL_SECRETS, {k: v for k, v in
                       (("EVM_PRIVATE_KEY", old_evm), ("FLASHBOTS_SIGNING_KEY", old_fb)) if v},
                       "rollback")
        _log("Rolled back local_secrets.env to the pre-rotation state.")
        return 1

    # ---- 5. optional Vault ----
    if args.vault:
        try:
            if new_evm is not None:
                vault_kv_write(EVM_KV, {"private_key": "0x" + new_evm.key.hex()})
            if new_fb is not None:
                vault_kv_write(FLASHBOTS_KV, {"signing_key": "0x" + new_fb.key.hex()})
        except Exception as e:
            _log(f"WARN: Vault update failed: {e}. local stores were updated; if the app "
                 "resolves from Vault at runtime, re-run with --vault once Vault is reachable.")
    else:
        _log("  vault: skipped (pass --vault to update HashiCorp Vault)")

    # ---- 6. ledger ----
    result = {
        "trigger": "manual",
        "rotated": {
            "evm_private_key": {"old_address": old_evm_addr, "new_address": new_evm.address} if new_evm else None,
            "flashbots_signing_key": {"old_address": old_fb_addr, "new_address": new_fb.address} if new_fb else None,
        },
        "archive_paths": archives,
        "stores": ["local_secrets.env", "pilot/credentials"] + (["vault"] if args.vault else []),
        "utc_timestamp": ts,
    }
    try:
        append_ledger(result)
        _log("  ledger: SIGNER_ROTATE appended (addresses only)")
    except Exception as e:
        _log(f"WARN: ledger append failed: {e}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    os.chmod(out, 0o600)
    _log(f"\nRotation complete. Addresses-only report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
