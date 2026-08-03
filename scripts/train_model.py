"""
Retrain the enterprise XGBoost model on the REAL Polygon MEV dataset.

Pipeline (all steps real, no random):
1. Load models/historical_mev_dataset.parquet (real Uniswap V3 Swap events)
   via DatasetLoader.
2. Normalize with the canonical normalize_features() scale - the SAME scale the
   scorer applies at inference (train/serve scale agreement).
3. Deterministic train/test split + 3-fold CV; production gate AUC >= 0.75.
4. Verify the pilot-critical protection cases still score >= threshold.
5. Save model (chmod 600), shap_background.npy, commitment.json with honest
   metrics (not self-attested placeholders).
6. Sign the commitment digest via the custody signer -> models/commitment.sig
   (real ECDSA over the canonical commitment JSON, custody-audited).

Run:  venv/bin/python scripts/train_model.py
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ml.scorer import DatasetLoader, ProteanScorerEnterprise, normalize_features
from app.core.config import settings

PILOT_CASES = [
    {
        "name": "defense_protect_high_slippage_small_user",
        "tx": {"type": "swap", "value_eth": 0.5, "gas_price_gwei": 50,
               "slippage_bps": 300, "pool_liquidity_eth": 500,
               "is_protected_user": 1},
        "min_score": 0.7,
    },
]


def main():
    # Load real dataset
    loader = DatasetLoader()
    X_raw, y = loader.load_historical_mev_labels()
    X = np.array([normalize_features(*row) for row in X_raw])
    y = np.array(y)
    print(f"Loaded {len(X)} rows, positives={int(y.sum())} ({y.mean():.1%})")

    # Train via the enterprise scorer (retrains, regenerates commitment.json).
    # In production load_or_train refuses to auto-train, so train explicitly.
    scorer = ProteanScorerEnterprise()
    scorer.train()

    # Regenerate SHAP background from the same normalized training matrix.
    from sklearn.model_selection import train_test_split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)
    bg = Path(settings.shap_background_path)
    bg.parent.mkdir(parents=True, exist_ok=True)
    np.save(bg, X_train)
    os.chmod(bg, 0o600)
    print(f"SHAP background saved {bg} shape={X_train.shape}")

    # Validate pilot-critical protection cases.
    for case in PILOT_CASES:
        score, _ = scorer.score(case["tx"])
        status = "PASS" if score >= case["min_score"] else "FAIL"
        print(f"[{status}] {case['name']}: score={score:.3f} "
              f"(>= {case['min_score']})")
        if score < case["min_score"]:
            raise SystemExit(1)

    # Honest provenance: attach the training matrix fingerprint used for the
    # reported metrics so the commitment isn't a self-attestation only.
    metrics = json.loads(scorer.commitment_path.read_text())
    metrics["training_data_hash"] = hashlib.sha256(X.tobytes() + y.tobytes()).hexdigest()
    metrics["signature_algorithm"] = "ECDSA-secp256k1"
    with open(scorer.commitment_path, "w") as f:
        json.dump(metrics, f, indent=2)
        f.write("\n")
    scorer.commitment = metrics
    os.chmod(scorer.commitment_path, 0o600)

    # Sign the canonical commitment digest via the custody signer.
    from app.evm.client import EVMClientEnterprise
    evm = EVMClientEnterprise()
    if not evm.account:
        raise RuntimeError("no custody signer available to sign the model commitment")
    canonical = json.dumps(metrics, sort_keys=True, separators=(",", ":")).encode()
    signed = evm.account.sign_message(canonical)
    sig_path = Path(settings.model_signature_path)
    sig = {
        "commitment_sha256": hashlib.sha256(canonical).hexdigest(),
        "message_hash": signed.message_hash.hex(),
        "signature": signed.signature.hex(),
        "signer_address": evm.account.address,
        "custody": evm.account.custody_source.value,
        "payload_canonical_json": canonical.decode(),
    }
    sig_path.write_text(json.dumps(sig, indent=2) + "\n")
    os.chmod(sig_path, 0o600)

    # Verify the signature recovers the signer (v is EIP-191 27/28; eth_keys wants 0/1).
    from eth_keys import keys
    v = signed.v - 27 if signed.v >= 27 else signed.v
    recovered = keys.Signature(vrs=(v, signed.r, signed.s)).recover_public_key_from_msg_hash(
        bytes(signed.message_hash)).to_checksum_address()
    ok = recovered == evm.account.address
    print(f"Commitment signed: {sig_path} signer={evm.account.address} "
          f"recover={recovered} verified={ok}")

    print(f"\nModel: {scorer.model_path} hash={metrics['model_hash'][:20]}...")
    print(f"Commitment: {scorer.commitment_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
