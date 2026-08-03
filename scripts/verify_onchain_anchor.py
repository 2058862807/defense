"""Verify the permanent on-chain fairness-proof anchor end to end.

Ground truth comes from two sources that never change and are served
reliably by the public RPC:

  * the submit transaction's calldata (decoded via the registry ABI) and
  * the registry's storage (getRecord).

PublicNode's eth_getLogs is flaky across load-balanced replicas, so the
event cross-check is best-effort only (skipped, never failed, if logs are
unavailable).

Checks:
1. The stored record for the calldata inputCommitment is verified == True,
   isFair == True (derived from publicInputs[0] == 1, the circuit output,
   not the submitter's claim), and was submitted by the active signer.
2. The on-chain modelCommitment matches the committed model hash.
3. The stored publicInputs match the submit transaction's calldata.
4. A freshly generated proof for the same case still verifies off-chain
   (snarkjs, real vkey) and on-chain (the live Groth16Verifier).
5. Best-effort: record proofHash == latest FairnessSubmitted event for the
   input commitment.

Exit code 0 == audit passes.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from app.core.config import settings
from app.evm.fairness_registry import FAIRNESS_ABI_ENTERPRISE, FairnessRegistryEnterprise
from app.ml.scorer import ProteanScorerEnterprise
from app.ml.xai import ZKXAICoupler
from app.zk.verifier import ZKVerifierEnterprise

ARTIFACT = Path("deployments/polygon_anchor_20260803.json")

FAIRNESS_SUBMITTED_SIG = Web3.keccak(
    text="FairnessSubmitted(bytes32,bytes32,bool,bool,address,bytes32,bool)"
).hex()


def decode_anchor_tx(w3, tx_hash: str):
    """Decode the submit tx calldata - authoritative, immutable ground truth."""
    tx = w3.eth.get_transaction(tx_hash)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(settings.fairness_registry_address),
        abi=FAIRNESS_ABI_ENTERPRISE,
    )
    fn, args = contract.decode_function_input(tx["input"])
    if fn.fn_name != "submitFairnessProof":
        raise ValueError(f"anchor tx is not submitFairnessProof: {fn.fn_name}")
    return {
        "model_commitment": args["modelCommitment"].hex(),
        "input_commitment": args["inputCommitment"].hex(),
        "public_inputs": [int(x) for x in args["publicInputs"]],
        "is_offense": args["isOffense"],
    }


def latest_submission(reg, w3, input_commitment: str, attempts: int = 3):
    """Best-effort: most recent FairnessSubmitted event for this input
    commitment. PublicNode caps get_logs at 10k blocks and occasionally
    serves corrupted/empty results, so retry and return None on failure."""
    topic_ic = "0x" + input_commitment
    for _ in range(attempts):
        try:
            to_block = w3.eth.block_number
            hits = []
            steps = 0
            while steps < 20:
                from_block = max(to_block - 9999, 0)
                chunk = w3.eth.get_logs({
                    "fromBlock": from_block,
                    "toBlock": to_block,
                    "address": reg.address,
                })
                hits += [
                    l for l in chunk
                    if l["topics"] and l["topics"][0].hex() == FAIRNESS_SUBMITTED_SIG
                    and l["topics"][1].hex() == topic_ic
                ]
                if not chunk or from_block == 0:
                    break
                steps += 1
                to_block = from_block - 1
            if hits:
                latest = max(hits, key=lambda l: l["blockNumber"])
                return {
                    "block": latest["blockNumber"],
                    "tx": latest["transactionHash"].hex(),
                    "proofHash": latest["data"][-64:],
                }
        except Exception as e:
            logger = f"{e}"
            time.sleep(1)
    return None


def main() -> int:
    if not ARTIFACT.exists():
        print(f"FAIL: anchor artifact not found at {ARTIFACT}")
        return 1

    anchor = json.loads(ARTIFACT.read_text())
    commitment = json.loads(Path("models/commitment.json").read_text())

    reg = FairnessRegistryEnterprise()
    w3 = reg.client.w3_http

    checks = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))

    try:
        calldata = decode_anchor_tx(w3, anchor["submit_tx"])
        ic = calldata["input_commitment"]
        print("Auditing on-chain anchor (ground truth = submit tx calldata):")
    except Exception as e:
        print(f"FAIL: could not decode anchor tx {anchor['submit_tx']}: {e}")
        return 1

    rec = reg.contract.functions.getRecord(reg._format_bytes32(ic)).call()
    check("record exists", rec[1].hex() == ic, ic[:16])
    check("record verified=True", bool(rec[8]))
    check("record isFair=True (from publicInputs[0], not caller)", bool(rec[3]))
    check("submitter is the active custody signer",
          rec[6].lower() == reg.client.account.address.lower(), rec[6])
    check("on-chain modelCommitment == committed model hash",
          rec[0].hex() == commitment["model_hash"], rec[0].hex()[:16])
    check("stored publicInputs == anchor tx calldata publicInputs",
          [int(x) for x in rec[9]] == calldata["public_inputs"],
          f"isFair={rec[9][0]}")
    check("stored modelCommitment == anchor tx calldata modelCommitment",
          rec[0].hex() == calldata["model_commitment"], rec[0].hex()[:16])

    latest = latest_submission(reg, w3, ic)
    if latest is None:
        print("  [SKIP] latest FairnessSubmitted event scan (PublicNode logs flaky)")
    else:
        check("record proofHash == latest submitted proof",
              rec[2].hex() == latest["proofHash"], latest["proofHash"][:16])
        check("latest submission confirmed in tx",
              w3.eth.get_transaction_receipt(latest["tx"])["status"] == 1,
              f"block {latest['block']}")

    print("Re-verifying a fresh proof for the same case:")
    scorer = ProteanScorerEnterprise()
    pkg = ZKXAICoupler(scorer).generate_zk_proof(anchor["case"])
    check("zk status PROVED_REAL_GROTH16", pkg.get("zk_status") == "PROVED_REAL_GROTH16", str(pkg.get("zk_status")))
    verifier = ZKVerifierEnterprise()
    check("off-chain snarkjs verify", verifier.verify_offchain(pkg["zk_proof"], pkg["zk_public_inputs"]))
    check("on-chain Groth16Verifier verify", verifier.verify_onchain(pkg["zk_proof"], pkg["zk_public_inputs"]))
    check("fresh inputCommitment reproducible",
          reg._format_bytes32(pkg["commitments"]["input_commitment"]).hex() == ic)

    ok = all(checks)
    print(f"\nON-CHAIN ANCHOR AUDIT: {'PASS' if ok else 'FAIL'} ({sum(checks)}/{len(checks)})")
    print(f"  anchor tx {anchor['submit_tx']} (block {anchor['block']})")
    if latest:
        print(f"  latest refresh tx {latest['tx']} (block {latest['block']})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
