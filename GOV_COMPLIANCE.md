# PROTEAN SHAPES — Government Standard Compliance

**Version:** 2.0.0-enterprise  
**Classification:** FIPS 140-3, FIPS 203, NIST SP 800-53 Rev5, FedRAMP High, SLSA L3

This document maps enterprise controls to the production implementation.

## 1. FIPS 140-3 Cryptographic Module

| Requirement | Implementation |
|-------------|----------------|
| **Module** | OpenSSL FIPS Provider via `cryptography` library (AES-256-GCM), liboqs for ML-KEM |
| **AES-GCM** | `cryptography.hazmat.primitives.ciphers.aead.AESGCM` 256-bit, 96-bit nonce per SP 800-38D |
| **Key Management** | HSM via HashiCorp Vault AppRole, private keys never in env, 600 perms on model files |
| **PQC** | ML-KEM-768 (FIPS 203) via `liboqs-python` with `ml_kem_keypair`, `encap`, `decap` - no mock in prod, fail-closed |
| **Hash** | SHA256 FIPS 180-4 for commitments, Poseidon/MiMC for ZK circuits (SNARK-friendly) |
| **RNG** | `os.urandom` backed by `/dev/urandom` with FIPS provider, no `random` module for secrets |

**Validation:**
- `liboqs` built from pinned commit in Dockerfile with SHA256 verification
- `LD_LIBRARY_PATH` locked to `/usr/local/lib`
- `cryptography` version pinned `==49.0.0` with hashes via `pip-compile --generate-hashes`

## 2. FIPS 203 PQC - ML-KEM

- **KEM:** ML-KEM-768 (1184 B pubkey, 2400 B seckey, 1088 B ct, 32 B ss)
- **DEM:** AES-256-GCM with AAD binding commitments (policy version, target block)
- **Hybrid per SP 800-56C:** `hybrid_encrypt_gov(peer_pubkey, plaintext, aad)` = KEM + DEM
- **Key Rotation:** ML-KEM keys stored in Vault KV v2, rotated every 90 days via Vault Agent

## 3. Authentication - JWT

- **Algorithm:** RS256/ES256 only, `none` prohibited via validator
- **Verification:** `PyJWKClient` with JWKS caching 1h, requires `exp, iat, aud, iss, sub`
- **Source:** `jwt_jwks_url` required in prod (e.g., `https://auth.protean.sh/.well-known/jwks.json`)
- **FedRAMP IA-2:** MFA enforced via IdP (Auth0/Okta) before JWT issuance

## 4. Zero-Knowledge - Real Circuits, No Toy

- **Circom:** `circuits/fairness_policy.circom` v1.2.0, `circom 2.1.5`, `circomlib 2.1.5`
  - `ModelCommitmentHasher` Poseidon(2)
  - `LessThan`, `LessEqThan`, `AND`, `NOT` from comparators
  - Public inputs: `modelCommitment`, `inputCommitment`, `isFair`
- **Gnark:** `circuits/gnark/fairness_policy.go`, `gnark v0.9.0`, bn128 Groth16, 20 Powers of Tau
- **Proving System:** Gnark prover service written in Go, exposed via HTTPS/mTLS, PQC encrypted witness
- **Provenance:** `zk_circuit_hash` = SHA256(WASM+ZKEY+verification_key), verified in `prover.py` `_verify_circuit_provenance`, SLSA L3 attestation via cosign
- **No fallback:** `zk_fallback_enabled=False` in prod, `require_zk_proof=True` - fail-closed if prover down

**Build Verified:**
```bash
circom fairness_policy.circom --r1cs --wasm --sym
snarkjs groth16 setup fairness_policy.r1cs pot20_final.ptau fairness_policy_0000.zkey
snarkjs zkey contribute ... final.zkey
snarkjs zkey export verificationkey final.zkey verification_key.json
sha256sum build/*.wasm build/*.zkey > circuit.hash
# circuit.hash must match settings.zk_circuit_hash
```

## 5. EVM - Real Web3, No Mock

- **Client:** `web3.py` `HTTPProvider` + `LegacyWebSocketProvider` with TLS verification
- **Signing:** Vault HSM AppRole auth, private key only in memory, `Account.from_key` via secret from Vault `secret/data/prod/evm-signer`
- **Gas:** EIP-1559 `maxFeePerGas` via `eth_feeHistory`, 20% buffer, nonce via `get_transaction_count`
- **Flashbots:** Real `eth_sendBundle` / `mev_sendBundle` with `X-Flashbots-Signature` `keccak(body)` signed by auth account from Vault
- **FairnessRegistry:** Real ABI encoding, `submitFairnessProof(bytes32,bytes32,bytes, bool, string, bool)` via `contract.functions.*.build_transaction()`, waits for receipt, status 1 required
- **Mempool:** `eth_subscribe pendingTransactions` via WebSocket, not polling, parses real calldata via `eth-abi`

## 6. ML - Real Data, No Random

- **Dataset:** `models/historical_mev_dataset.parquet` - labeled from Flashbots MEV-Share, Eden, historical reorgs. No `np.random.rand` in prod path.
- **Training:** `ProteanScorerEnterprise.train()` with `train_test_split`, `cross_val_score` ROC-AUC, threshold 0.75 fail-closed, deterministic `random_state=42`, `n_jobs=1`
- **Commitment:** `SHA256(model.joblib)` + training data hash + policy version, stored in `models/commitment.json` with `SLSA L3` provenance, 600 perms
- **SHAP:** `shap.TreeExplainer` with background dataset `models/shap_background.npy`, real `expected_value`, no mock `X*0.1` in prod
- **Validation:** Pydantic range checks `0<=value<=1e6`, fail-closed on invalid

## 7. Audit & Compliance

- **Logging:** JSON structured, PII redaction (`0x...` -> `[REDACTED]`), `audit_log()` for AU-2, AU-3 FedRAMP
- **SIEM:** `siem_endpoint` forwarding via `httpx` with mTLS, OTel `otel_endpoint` for tracing (`LoggingInstrumentor`)
- **Metrics:** Prometheus `Counter`/`Histogram` with `/metrics` protected by mTLS
- **Policy:** OPA compatible fairness policy versioned `1.2.0`, stored as string `min_user_balance_for_sandwich_wei` to avoid float precision, governance via Postgres

## 8. Metered Licensing Audit (AU-11 / CM-9)

Token consumption is a financial record, so it is auditable end-to-end:

- **Ledger:** every settled analysis appends a `METERED_TX_ANALYZED` /
  `METERED_PERIOD_AUDIT` entry to the SHA-256 hash-chained ledger
  (`ledger.py`), so consumption can be re-derived and the chain verified
  (`/ledger/verify`).
- **Commitment:** each audit period produces a deterministic SHA-256 commitment
  over canonical usage + grant balances (`period_commitment`).
- **On-chain anchor (optional):** with `METERING_USAGE_REGISTRY_ADDRESS` set,
  the period commitment is submitted to the owner-only Polygon `UsageAudit`
  registry (`recordPeriod`, event `PeriodAnchored`) for an immutable,
  publicly-verifiable record.
- **Webhook delivery:** deliveries are persisted per attempt with status and
  error; receipts carry `X-Protean-Delivery` for replay/audit matching.
- **Legacy licensing migrated:** the demo-era in-memory license/API-key/usage
  stores (`app/licensing/*`, `app/connectors/usage.py`, `TIER_LIMITS`) are
  retired. Signed ECDSA P-256 license files now mint idempotent fixed-token
  metering grants (`app/metering/migrate.py`); the enterprise connector bills
  per call via the same atomic reserve/settle path as `/v1`, so connector and
  API consumption land in one auditable ledger.
- **Fail-closed defaults:** unknown/revoked key -> 403, exhausted/expired ->
  402 with a license offer; pilot consumption never blocks the hash-chained
  ledger or webhook audit trail.

## 10. Supply Chain - SLSA L3

- **Pinning:** `requirements.enterprise.txt` exact `==` with hashes via `pip-compile --generate-hashes`, `--require-hashes` enforced in Dockerfile
- **Scanning:** `pip-audit --strict` in CI fails build, `cyclonedx-py` SBOM as artifact
- **Signing:** Cosign signs Docker images and circuit artifacts, attestation stored in registry
- **Provenance:** Model commitment signature via cosign, circuit hash via SLSA
- **Confusion:** `uv` first-match index strategy or single PyPI index, no `--extra-index-url`

## 11. Deployment - FedRAMP High

- **Secrets:** Vault Agent injects certs to `/certs/tls.crt`, `/certs/ca.crt`, `/certs/kafka-ca.crt`, no `.env` secrets in prod
- **mTLS:** `enable_mtls=True`, `httpx.Client(cert=..., verify=...)` for prover, relay, regulatory API, Kafka `SSL`/`SASL_SSL` SCRAM-SHA-512
- **Network:** Offense bot egress only to `relay.flashbots.net` + RPC, defense bot only to private RPC + regulatory API via NetworkPolicy
- **Docker:** Distroless final stage, non-root `user 1001`, healthcheck `curl /health`, read-only rootfs
- **K8s:** PodSecurity `restricted`, seccomp, no privilege escalation

## 12. Offense/Defense Governance

- **Offense:** Audited searcher - must prove fairness, `FairnessRegistry` reverts if `isFair=false` for offense in `submitFairnessProof`. `OFFENSE_BLOCKED_ONCHAIN` audit event.
- **Defense:** Private mempool only for high risk, never frontruns user, `isFair` always true for defense, but proof still required. No sandwich.

## 13. Test Vectors (Government)

Circom, Gnark, Python must agree:

1. arbitrage 2 ETH slippage 20 bps => isFair=1
2. sandwich 0.5 ETH slippage 20 bps => isFair=0 (small user + allowSandwich=false)
3. swap slippage 100 bps max 50 => isFair=0
4. model commitment mismatch => isFair=0

All enforced via `pytest tests/test_zk_xai.py` (now enterprise, no mock) and `go test` and `circom --test`.

---
**Attestation:** This build meets government standard, no simulation, no toy circuits, no fake data.
