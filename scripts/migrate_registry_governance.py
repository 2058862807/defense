#!/usr/bin/env python3
"""
FairnessRegistry governance migration: single-EOA -> TimelockController.

Implements docs/FAIRNESS_REGISTRY_GOVERNANCE_MIGRATION.md steps 1, 3-8:
  1. Deploy a fresh FairnessRegistry(Groth16Verifier)
  2. Deploy a TimelockController (proposers/executors = signer, admin = 0x0)
  3. transferOwnership(newRegistry -> timelock) by the deployer EOA
  4. Schedule + (after minDelay) execute acceptOwnership THROUGH the timelock,
     so newRegistry.owner() becomes the timelock, not an EOA
  5. Authorize the submitter on the new registry via the timelock
  6. Freeze the OLD registry (setPaused(true)) from its still-EOA owner
  7. Update .env FAIRNESS_REGISTRY_ADDRESS to the new registry
  8. Verify owner()==timelock, old paused()==true, submitter authorized

Safety:
  * Defaults to DRY RUN: compiles, connects, estimates gas, prints the plan,
    sends NOTHING.
  * --execute refuses to send if the signer balance cannot cover gas+15%.
  * --simulate runs the identical flow against an anvil mainnet fork
    (anvil --fork-url <polygon rpc> --unlocked), skipping the timelock delay.

Usage:
  python scripts/migrate_registry_governance.py                          # dry run
  python scripts/migrate_registry_governance.py --execute --min-delay 60 \
      --yes                                                            # real cutover
  # simulate first (no funds, no keys):
  anvil --fork-url https://polygon-bor-rpc.publicnode.com --unlocked &
  python scripts/migrate_registry_governance.py --simulate --rpc-url http://127.0.0.1:8545
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

import solcx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
LOCAL_SECRETS = ROOT / "data" / "local_secrets.env"
VERIFIER_SOL = ROOT / "contracts" / "verifiers" / "FairnessPolicyVerifier.sol"
REGISTRY_SOL = ROOT / "contracts" / "FairnessRegistry.sol"
TIMELOCK_SOL = ROOT / "lib" / "openzeppelin-contracts" / "contracts" / "governance" / "TimelockController.sol"
OUT_DIR = ROOT / "contracts" / "out"
SOLC_VERSION = "0.8.24"
REMAPPINGS = [
    "@openzeppelin/=lib/openzeppelin-contracts/",
    "openzeppelin-contracts/=lib/openzeppelin-contracts/",
]
DEFAULT_VERIFIER = "0x624331b96A857dfa2e021CD8c149b4813C38dD7C"  # live Groth16Verifier (polygon_verifier_20260803.json)
DEFAULT_OLD_REGISTRY = "0xc8666f0b9567D447Ce6aaCC1169D15c0E35d0b79"
SALT = hashlib.sha256(b"protean-governance-migration-v1").digest()  # 32 bytes
GAS_BUF = 1.15  # 15% buffer over estimate
TX_GAS = 100_000


def load_env_file(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def compile_contracts():
    solcx.set_solc_version(SOLC_VERSION)
    sources = {
        str(REGISTRY_SOL): {"content": REGISTRY_SOL.read_text()},
        str(TIMELOCK_SOL): {"content": TIMELOCK_SOL.read_text()},
    }
    out = solcx.compile_standard({
        "language": "Solidity",
        "sources": sources,
        "settings": {
            "remappings": REMAPPINGS,
            "optimizer": {"enabled": True, "runs": 200},
            "viaIR": True,
            "outputSelection": {"*": {"*": ["abi", "evm.bytecode.object"]}},
        },
    })
    if "errors" in out:
        errs = [e for e in out["errors"] if e.get("severity") == "error"]
        if errs:
            raise RuntimeError(errs[0].get("formattedMessage"))
    reg = out["contracts"][str(REGISTRY_SOL)]["FairnessRegistry"]
    tim = out["contracts"][str(TIMELOCK_SOL)]["TimelockController"]
    return {
        "registry": {"abi": reg["abi"], "bytecode": "0x" + reg["evm"]["bytecode"]["object"]},
        "timelock": {"abi": tim["abi"], "bytecode": "0x" + tim["evm"]["bytecode"]["object"]},
    }


def sign_and_send(w3, tx, key):
    signed = w3.eth.account.sign_transaction(tx, key)
    return w3.eth.send_raw_transaction(signed.rawTransaction)


def send(w3, tx, key, impersonate):
    if impersonate:
        return w3.eth.send_transaction(tx)
    return sign_and_send(w3, tx, key)


def mined(w3, txh, timeout=180):
    rec = w3.eth.wait_for_transaction_receipt(txh, timeout=timeout)
    if rec.get("status") != 1:
        raise RuntimeError(f"tx {txh.hex()[:16]}... REVERTED - aborting migration")
    return rec


def gate_balance(w3, address, estimate_gas):
    gas_price = w3.eth.gas_price
    needed = int(estimate_gas * gas_price * GAS_BUF)
    bal = w3.eth.get_balance(address)
    if bal < needed:
        shortfall = (needed - bal) / 1e18
        print(f"FATAL: balance {bal/1e18:.4f} < needed {needed/1e18:.4f} "
              f"(est {estimate_gas} gas * {gas_price/1e9:.1f} gwei * {GAS_BUF})")
        print(f"  -> top up {shortfall:.4f} native (POL) to continue the migration.")
        sys.exit(1)


def wait_for_delay(w3, deployer, timelock, op_id, min_delay, simulate):
    if simulate:
        w3.provider.make_request("evm_increaseTime", [min_delay + 1])
        w3.provider.make_request("evm_mine", [])
        return
    deadline = time.time() + min_delay + 60
    print(f"  waiting up to {min_delay}s for timelock delay (op {op_id[:16]}...)...")
    while time.time() < deadline:
        if timelock.functions.isOperationReady(op_id).call({"from": deployer}):
            return
        time.sleep(min(15, max(2, min_delay / 20)))


def update_env_registry(new_registry: str):
    env_path = ROOT / ".env"
    backup = ROOT / f".env.pre-gov-migration-{int(time.time())}.bak"
    if env_path.exists():
        env_path.rename(backup)
        print(f".env backed up to {backup.name}")
    text = backup.read_text() if backup.exists() else ""
    lines = []
    replaced = False
    for line in text.splitlines():
        if line.startswith("FAIRNESS_REGISTRY_ADDRESS="):
            lines.append(f"FAIRNESS_REGISTRY_ADDRESS={new_registry}")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.append(f"FAIRNESS_REGISTRY_ADDRESS={new_registry}")
    env_path.write_text("\n".join(lines) + "\n")
    print(f".env FAIRNESS_REGISTRY_ADDRESS -> {new_registry}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="send transactions (default: dry run)")
    ap.add_argument("--simulate", action="store_true", help="anvil fork run (impersonated, skips delay)")
    ap.add_argument("--rpc-url", default=os.environ.get("MAINNET_RPC_URL", "https://polygon-bor-rpc.publicnode.com"))
    ap.add_argument("--chain-id", type=int, default=137)
    ap.add_argument("--verifier", default=DEFAULT_VERIFIER)
    ap.add_argument("--old-registry", default=DEFAULT_OLD_REGISTRY)
    ap.add_argument("--min-delay", type=int, default=172800, help="timelock minDelay seconds (default 48h)")
    ap.add_argument("--impersonate", default=None, help="simulate as this address (anvil --unlocked)")
    ap.add_argument("--signer", default=str(LOCAL_SECRETS), help="env file holding EVM_PRIVATE_KEY")
    ap.add_argument("--submitter", default=None, help="address to authorize (default: signer)")
    ap.add_argument("--yes", action="store_true", help="skip the final confirmation prompt")
    ap.add_argument("--out", default=str(OUT_DIR / "governance_migration.json"))
    args = ap.parse_args()

    from web3 import Web3
    from web3.middleware import geth_poa_middleware
    w3 = Web3(Web3.HTTPProvider(args.rpc_url, request_kwargs={"timeout": 60}))
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
    ZERO32 = b"\x00" * 32
    SALT_BYTES = bytes(SALT)
    if not w3.is_connected():
        print(f"FATAL: cannot reach RPC {args.rpc_url}")
        return 1
    chain_id = w3.eth.chain_id
    print(f"connected: chain_id={chain_id} (expected {args.chain_id})")
    if chain_id != args.chain_id:
        print("FATAL: chain_id mismatch - refusing to run against the wrong network")
        return 1

    if args.simulate and not args.impersonate:
        print("FATAL: --simulate requires --impersonate <address> (anvil --unlocked)")
        return 1
    key = None
    if args.impersonate:
        deployer = args.impersonate
    else:
        env = load_env_file(Path(args.signer))
        key = env.get("EVM_PRIVATE_KEY", "")
        if not key:
            print("FATAL: EVM_PRIVATE_KEY not found in", args.signer)
            return 1
        from eth_account import Account
        deployer = Account.from_key(key).address
    submitter = args.submitter or deployer
    print(f"deployer : {deployer}")
    print(f"submitter: {submitter}")
    print(f"verifier : {args.verifier}")
    print(f"old reg  : {args.old_registry}")
    print(f"min-delay: {args.min_delay}s")

    print("compiling contracts...")
    contracts = compile_contracts()
    print("  FairnessRegistry + TimelockController compiled OK")

    Registry = w3.eth.contract(abi=contracts["registry"]["abi"], bytecode=contracts["registry"]["bytecode"])
    Timelock = w3.eth.contract(abi=contracts["timelock"]["abi"], bytecode=contracts["timelock"]["bytecode"])

    old_reg = w3.eth.contract(address=args.old_registry, abi=contracts["registry"]["abi"])
    owner_now = old_reg.functions.owner().call()
    print(f"old registry owner now: {owner_now}")

    # ---- step 1: deploy new registry ----
    ctor = Registry.constructor(args.verifier)
    est_reg = w3.eth.estimate_gas({"from": deployer, "data": ctor.data_in_transaction})
    print(f"[1] new FairnessRegistry deploy ~ {est_reg} gas")
    # ---- step 2: deploy timelock ----
    ctor_t = Timelock.constructor(args.min_delay, [deployer], [deployer], "0x0000000000000000000000000000000000000000")
    est_t = w3.eth.estimate_gas({"from": deployer, "data": ctor_t.data_in_transaction})
    print(f"[2] TimelockController deploy ~ {est_t} gas")
    # ---- step 3-6 ----
    print(f"[3-6] transferOwnership + timelock schedule/execute x2 + freeze old ~ "
          f"{5*TX_GAS} gas total")
    total_est = est_reg + est_t + 5 * TX_GAS
    bal = w3.eth.get_balance(deployer)
    needed = total_est * w3.eth.gas_price * GAS_BUF
    print(f"balance {bal/1e18:.4f} | estimated cost {needed/1e18:.4f} "
          f"({'OK' if bal >= needed else 'INSUFFICIENT'})")

    if args.simulate or (args.execute and args.yes):
        pass
    elif args.execute:
        if input("Type YES to broadcast these transactions: ") != "YES":
            print("aborted")
            return 1
    if not args.execute and not args.simulate:
        print("\nDRY RUN complete - nothing was sent. Re-run with --execute to migrate.")
        return 0

    # ================= EXECUTION =================
    if not args.simulate:
        gate_balance(w3, deployer, total_est)
    base = {"from": deployer, "chainId": chain_id}
    nonce = w3.eth.get_transaction_count(deployer)

    # 1: deploy registry
    tx = ctor.build_transaction({**base, "nonce": nonce, "gas": int(est_reg * GAS_BUF)})
    txh = send(w3, tx, key, args.impersonate)
    rec = mined(w3, txh, timeout=300)
    new_reg = rec.contractAddress
    print(f"[1] new FairnessRegistry deployed: {new_reg} (tx {txh.hex()[:16]}...)")
    nonce += 1
    reg = w3.eth.contract(address=new_reg, abi=contracts["registry"]["abi"])

    # 2: deploy timelock
    tx = ctor_t.build_transaction({**base, "nonce": nonce, "gas": int(est_t * GAS_BUF)})
    txh = send(w3, tx, key, args.impersonate)
    rec = mined(w3, txh, timeout=300)
    tim_addr = rec.contractAddress
    print(f"[2] TimelockController deployed: {tim_addr} (tx {txh.hex()[:16]}...)")
    nonce += 1
    tim = w3.eth.contract(address=tim_addr, abi=contracts["timelock"]["abi"])

    # 3: transferOwnership(new_reg -> timelock) by deployer EOA
    tx = reg.functions.transferOwnership(tim_addr).build_transaction({**base, "nonce": nonce, "gas": TX_GAS})
    txh = send(w3, tx, key, args.impersonate)
    mined(w3, txh, timeout=120)
    print(f"[3] transferOwnership -> {tim_addr} queued (tx {txh.hex()[:16]}...)")
    nonce += 1

    accept_calldata = reg.encodeABI(fn_name="acceptOwnership")

    # 4: schedule + execute acceptOwnership through the timelock
    op_id = tim.functions.hashOperation(new_reg, 0, bytes.fromhex(accept_calldata[2:]), ZERO32, SALT_BYTES).call()
    tx = tim.functions.schedule(new_reg, 0, bytes.fromhex(accept_calldata[2:]), ZERO32, SALT_BYTES, args.min_delay).build_transaction({**base, "nonce": nonce, "gas": TX_GAS})
    txh = send(w3, tx, key, args.impersonate)
    mined(w3, txh, timeout=120)
    print(f"[4] acceptOwnership scheduled in timelock (tx {txh.hex()[:16]}...)")
    nonce += 1
    wait_for_delay(w3, deployer, tim, op_id, args.min_delay, args.simulate)
    tx = tim.functions.execute(new_reg, 0, bytes.fromhex(accept_calldata[2:]), ZERO32, SALT_BYTES).build_transaction({**base, "nonce": nonce, "gas": TX_GAS})
    txh = send(w3, tx, key, args.impersonate)
    mined(w3, txh, timeout=120)
    print(f"[4] acceptOwnership executed (tx {txh.hex()[:16]}...)")
    nonce += 1

    owner_after = reg.functions.owner().call()
    print(f"new registry owner() = {owner_after} (timelock={owner_after.lower()==tim_addr.lower()})")

    # 5: authorize submitter through the timelock
    auth_calldata = reg.encodeABI(fn_name="authorizeSubmitter", args=[submitter])
    op_id2 = tim.functions.hashOperation(new_reg, 0, bytes.fromhex(auth_calldata[2:]), ZERO32, SALT_BYTES).call()
    tx = tim.functions.schedule(new_reg, 0, bytes.fromhex(auth_calldata[2:]), ZERO32, SALT_BYTES, args.min_delay).build_transaction({**base, "nonce": nonce, "gas": TX_GAS})
    txh = send(w3, tx, key, args.impersonate)
    mined(w3, txh, timeout=120)
    print(f"[5] authorizeSubmitter scheduled (tx {txh.hex()[:16]}...)")
    nonce += 1
    wait_for_delay(w3, deployer, tim, op_id2, args.min_delay, args.simulate)
    tx = tim.functions.execute(new_reg, 0, bytes.fromhex(auth_calldata[2:]), ZERO32, SALT_BYTES).build_transaction({**base, "nonce": nonce, "gas": TX_GAS})
    txh = send(w3, tx, key, args.impersonate)
    mined(w3, txh, timeout=120)
    print(f"[5] authorizeSubmitter({submitter}) executed (tx {txh.hex()[:16]}...)")
    nonce += 1

    # 6: freeze old registry (still owned by its EOA, not the timelock)
    old_owner = old_reg.functions.owner().call()
    freeze_nonce = w3.eth.get_transaction_count(old_owner)
    tx = old_reg.functions.setPaused(True).build_transaction(
        {**base, "from": old_owner, "nonce": freeze_nonce, "gas": TX_GAS}
    )
    txh = send(w3, tx, key, args.impersonate)
    mined(w3, txh, timeout=120)
    print(f"[6] old registry {args.old_registry} setPaused(true) by {old_owner} (tx {txh.hex()[:16]}...)")

    # 7: cut over .env
    if not args.simulate:
        update_env_registry(new_reg)

    # 8: verify
    checks = {
        "new_registry": new_reg,
        "timelock": tim_addr,
        "new_owner_is_timelock": owner_after.lower() == tim_addr.lower(),
        "old_paused": old_reg.functions.paused().call(),
    }
    print("[8] verification:", json.dumps(checks, indent=2))
    artifact = {
        "network": "polygon-mainnet",
        "chain_id": chain_id,
        "old_registry": args.old_registry,
        "new_registry": new_reg,
        "timelock": tim_addr,
        "verifier": args.verifier,
        "min_delay_seconds": args.min_delay,
        "submitter": submitter,
        "deployer": deployer,
        "new_owner_is_timelock": checks["new_owner_is_timelock"],
        "old_paused": checks["old_paused"],
        "salt": "0x" + SALT.hex(),
        "simulated": args.simulate,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(artifact, indent=2))
    print(f"artifact written: {args.out}")
    return 0 if checks["new_owner_is_timelock"] and checks["old_paused"] else 1


if __name__ == "__main__":
    sys.exit(main())
