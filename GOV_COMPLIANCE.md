# PROTEAN SHAPES — Government Standard Compliance

**Version:** 2.0.0-enterprise

This document has two parts, kept deliberately separate:

1. **Implemented controls** — what is actually in this codebase today. Every claim here
   references a specific file or module you can go read. If a claim can't be traced to code,
   it does not belong in this section.
2. **Certification & assessment status** — what has and has not been independently assessed.
   Using FIPS-approved algorithms or SLSA-shaped tooling in an implementation is not the same
   as holding a certification for either, and this document does not conflate the two.

---

## Part 1: Implemented Controls

### 1.1 Cryptographic primitives (FIPS-approved algorithms)

| Control | Implementation | Reference |
|---|---|---|
| AES-256-GCM | `cryptography.hazmat.primitives.ciphers.aead.AESGCM`, 256-bit key, 96-bit nonce | `app/core/security.py`, `app/core/secrets_store.py` |
| ML-KEM-768 (FIPS 203) | `ml_kem_keypair` / `ml_kem_encapsulate` / `ml_kem_decapsulate` via `liboqs-python`; raises in prod if liboqs isn't installed (no silent mock) | `app/core/security.py:152-232` |
| Hybrid KEM+DEM (SP 800-56C shape) | `hybrid_encrypt_gov()` combines ML-KEM encapsulation with AES-256-GCM | `app/core/security.py:268` |
| Hashing | SHA-256 for commitments; Poseidon/MiMC inside the ZK circuit | `app/core/ledger.py`, `circuits/fairness_policy.circom` |
| RNG | `os.urandom` for secrets, never the `random` module | `app/core/secrets_store.py`, `app/core/security.py`, `app/qrng/*` |
| `cryptography` version pin | `==49.0.0`, hash-pinned via `pip-compile`/`uv pip compile --generate-hashes` | `requirements.in`, `requirements.enterprise.txt` |

**Note on the "FIPS 140-3" label:** this codebase uses FIPS-approved algorithms (AES-256-GCM,
SHA-256, ML-KEM per FIPS 203) through the `cryptography` and `liboqs-python` libraries. That is
not the same as running inside a FIPS 140-3 *validated cryptographic module* — that requires a
NIST CMVP certificate for the specific build artifact, which does not exist for this project. See
Part 2.

### 1.2 Authentication — JWT

| Control | Implementation | Reference |
|---|---|---|
| RS256/ES256 only, `none` rejected | `verify_jwt_gov()` explicitly rejects `none` and restricts algorithms | `app/core/security.py:44-111` |
| JWKS verification | `PyJWKClient` with a 1h key cache | `app/core/security.py:47-50` |
| HS256 rejected in production | Enforced by both the JWT verifier and `Settings` validation (`jwt_algorithm in ("RS256","ES256")`) | `app/core/security.py`, `app/core/config.py:275`, tested in `tests/unit/test_auth.py` |
| Fail-closed with no token in prod | `test_production_fail_closed_no_token` | `tests/unit/test_auth.py`, `app/core/auth_deps.py` |

**Not verifiable in this codebase:** MFA enforcement is a property of whatever external IdP
(Auth0/Okta/etc.) issues the JWT before this app ever sees it. Nothing in this repo can confirm
or deny that MFA is configured on that IdP — don't cite this as a control this codebase enforces.

### 1.3 Zero-Knowledge circuit

| Control | Implementation | Reference |
|---|---|---|
| Circom circuit, not a toy | `fairness_policy.circom` — Poseidon hasher, `LessThan`/`AND`/`NOT` comparators, public inputs `modelCommitment`/`inputCommitment`/`isFair` | `circuits/fairness_policy.circom` |
| Gnark circuit (Go, bn128 Groth16) | `fairness_policy.go` | `circuits/gnark/fairness_policy.go` |
| Circuit hash verification | Ingests and checks SHA-256 of WASM+ZKEY against `settings.zk_circuit_hash` | `app/zk/ingest.py:68 (_verify_hash)` |
| Fail-closed if prover unavailable | `zk_fallback_enabled=False`, `require_zk_proof=True`, asserted in prod | `app/core/config.py:44-45,271-272` |
| Python enforces the same policy the circuit does | `tests/test_zk_xai.py`, `tests/test_zk_xai_enterprise.py` | — |

**Gap, not yet true:** there is no automated cross-check that the Circom circuit, the Gnark
circuit, and the Python pre-check agree on the same test vectors. `circuits/gnark/fairness_policy.go`
has no companion `_test.go`, and there is no `circom --test`/`circom_tester` harness in this repo.
Only the Python side (`tests/test_zk_xai*.py`) is enforced by CI today. If you need circom/gnark
parity guarantees, that tooling needs to be built — it doesn't exist yet.

### 1.4 EVM / Web3

| Control | Implementation | Reference |
|---|---|---|
| Real `web3.py` client, TLS-verified HTTP + WS | `Web3.HTTPProvider(..., request_kwargs={"verify": True})`, `LegacyWebSocketProvider` | `app/evm/client.py` |
| EIP-1559 gas via `eth_feeHistory` | — | `app/evm/client.py:83` |
| Real mempool subscription | `eth_subscribe newPendingTransactions` over WebSocket, not polling | `app/evm/mempool_connector.py` |
| `FairnessRegistry.submitFairnessProof` real ABI call | `contract.functions.submitFairnessProof(...).build_transaction()`, waits for a receipt | `app/evm/fairness_registry.py` |
| Flashbots bundle submission with signed auth header | `X-Flashbots-Signature` = signer over `keccak(body)` | `app/evm/flashbots.py` |
| Custody fail-closed for signing | `hsm_require_hardware` defaults `True`; production refuses to sign unless custody resolves to PKCS#11 HSM or Vault Transit | `app/hsm/custody.py:build_signing_backend()`, `tests/unit/test_custody.py` |

### 1.5 ML model

| Control | Implementation | Reference |
|---|---|---|
| Real dataset, not synthetic in prod path | `models/historical_mev_dataset.parquet` | — |
| Deterministic training | `train_test_split(..., random_state=42)`, `n_jobs=1`, `cross_val_score` ROC-AUC | `app/ml/scorer.py:215-234`, `app/ml/training_pipeline.py:308-332` |
| Fail-closed on low AUC | `if auc < 0.75 and settings.is_production(): raise` | `app/ml/scorer.py:241-242` |
| Model commitment | SHA-256 of the model file + training data hash, `models/commitment.json`, `0o600` perms | `app/ml/scorer.py:247`, `app/ml/training_pipeline.py:357,387,394` |
| Real SHAP explanations | `shap.TreeExplainer` against `models/shap_background.npy` | `app/ml/xai.py` |

**Not found in this repo (see Task 6 below for the full search):** no labels table, ground-truth
validation pipeline, or retrain-data-provenance tracking exists in this codebase. If that exists,
it's in a different system — don't assume it from this document.

### 1.6 Audit logging & observability

| Control | Implementation | Reference |
|---|---|---|
| Structured JSON logs, PII redaction | Regex redaction for addresses, private keys, JWTs, passwords | `app/core/logging.py:18-22` |
| `audit_log()` used for security-relevant events | — | `app/core/logging.py:108`, called throughout `app/main.py` |
| OTel tracing, SIEM forwarding | Both optional, enabled via `otel_endpoint`/`siem_endpoint` config | `app/core/logging.py:64-77,130-134` |
| Prometheus metrics | `/metrics` ASGI mount, `Counter`/`Histogram` | `app/main.py:37-40,87-88` |
| Metrics endpoint mTLS | Enforced at the scrape layer (Prometheus client cert config), not in application code | `k8s/monitoring/monitoring.yaml:124-126` |

**Correction from the prior version of this doc:** fairness policy is a hardcoded dict in
`Settings.fairness_policy` (`app/core/config.py`), current version `1.3.0`. There is no
Postgres-backed policy governance table in this codebase — the earlier claim of "governance via
Postgres" was not backed by any code and has been removed.

### 1.7 Metered licensing audit trail

| Control | Implementation | Reference |
|---|---|---|
| SHA-256 hash-chained ledger | `HashChainedLedger.append()`/`verify_chain()` | `app/core/ledger.py` |
| `/ledger/verify` endpoint | Role-gated (`gov-admin`/`operator`/`auditor`) | `app/main.py:972-977` |
| Per-period commitment | `period_commitment()` | `app/metering/service.py:75` |
| Optional on-chain anchor | `UsageAuditAnchor.recordPeriod` against `UsageAudit.sol` | `app/metering/usage_anchor.py` |
| Fail-closed metering | Unknown/revoked key → 403, exhausted/expired → 402 | `app/metering/*` |

### 1.8 Supply chain

| Control | Implementation | Reference |
|---|---|---|
| Hash-pinned dependencies | `requirements.in` → `requirements.enterprise.txt` compiled with `uv pip compile --generate-hashes` (or `pip-compile --generate-hashes`), every package hash-pinned | `requirements.in`, `requirements.enterprise.txt` |
| `--require-hashes` enforced with no fallback | A hash mismatch fails the build in every Dockerfile that installs Python deps | `Dockerfile`, `Dockerfile.enterprise`, `Dockerfile.connector`, `Dockerfile.licensing`, `start.sh` |
| CI drift check | Recompiles `requirements.in` and diffs against the committed lock file; fails on drift instead of silently regenerating | `.github/workflows/enterprise-ci.yml` ("verify requirements.enterprise.txt matches requirements.in") |
| `liboqs` pinned to a released commit, verified | `ARG LIBOQS_COMMIT=f4b96220e4bd208895172acc4fedb5a191d9f5b1` (tag `0.12.0`); build asserts `git rev-parse HEAD` matches before compiling | `Dockerfile`, `Dockerfile.enterprise`, `.github/workflows/enterprise-ci.yml` |
| `pip-audit --strict` in CI | Fails the build on known vulnerabilities | `.github/workflows/enterprise-ci.yml` |
| SBOM | CycloneDX SBOM generated from the same lock file | `.github/workflows/enterprise-ci.yml`, `start.sh` |
| Artifact signing | `cosign sign-blob` over the SBOM and the circuit verification key (no silent `|| true` on failure) | `.github/workflows/enterprise-ci.yml` |

**Correction:** the Docker *image* itself is not cosign-signed — only the SBOM and the circuit
verification key are. The `docker build --provenance=true` flag attaches SLSA provenance
metadata, which is a related but different guarantee than an image signature. If image signing
is required, that step needs to be added (`cosign sign` against the built image digest).

### 1.9 Deployment hardening

| Control | Implementation | Reference |
|---|---|---|
| Distroless final stage, non-root | `gcr.io/distroless/python3-debian12:nonroot`, `USER nonroot:nonroot` | `Dockerfile.enterprise` |
| Non-root in the standard image | `USER protean` (uid 1001) | `Dockerfile`, `Dockerfile.connector`, `Dockerfile.licensing` |
| Per-pod `seccompProfile`/`allowPrivilegeEscalation: false` | Set on individual Deployments | `k8s/api/api.yaml`, `k8s/defense-bot/defense-bot.yaml`, others |
| Fail-closed TLS/mTLS material check | Refuses to boot without required cert material when `enable_mtls`/`require_tls` are set | `app/main.py:50` (see comment "Fail-closed TLS/mTLS material check (A2)") |
| Vault Agent cert injection | `vault.hashicorp.com/agent-inject` annotations | `k8s/*/*.yaml` |

**Not implemented (previously claimed, now corrected):**
- No `kind: NetworkPolicy` object exists anywhere in `k8s/`. The claim that offense-bot egress is
  restricted to `relay.flashbots.net` + RPC via NetworkPolicy is aspirational text in
  `k8s/operator/operator.py`'s docstring, not an enforced control. (Also note: offense-bot's
  deployment now lives in the separate `protean-offense-tools` repo, not here — see the pilot
  readiness fix history.)
- No namespace carries a Pod Security Admission `restricted` label. Individual pods set
  restricted-*shaped* fields (no privilege escalation, seccomp), but there's no cluster-enforced
  policy tying them together.

### 1.10 Offense/defense governance

| Control | Implementation | Reference |
|---|---|---|
| `FairnessRegistry` reverts on unfair offense proofs | `require(isFairFromProof)`, `isFair` derived from verified public inputs, not a caller-supplied bool | `contracts/FairnessRegistry.sol` |
| Offense/sandwich code physically separated from this pilot-facing repo | Split into `protean-offense-tools` (private, access-restricted), loaded only via explicit `PROTEAN_OFFENSE_TOOLS_PATH` opt-in | `app/bots/offense_loader.py` |
| `hsm_require_hardware` fail-closed for signing | Refuses production software/env-key custody unless explicitly disabled | `app/hsm/custody.py`, `tests/unit/test_custody.py` |

---

## Part 2: Certification & Assessment Status

None of the following are self-declared as certified. Each requires an independent, third-party
assessment process that has not happened for this codebase:

| Framework | Status | What it would actually require |
|---|---|---|
| FIPS 140-3 | **Not certified.** Uses FIPS-approved algorithms via `cryptography`/`liboqs-python`, but no CMVP-validated module | A specific build submitted to and validated by NIST's Cryptographic Module Validation Program |
| FIPS 203 (ML-KEM) | **Algorithm implemented, no independent validation** | Same CMVP-style process, once available for PQC modules |
| NIST SP 800-53 Rev5 | **Partial control mapping only** (this document, Part 1) | A System Security Plan (SSP) and independent assessment (3PAO or equivalent) against the full control catalog |
| FedRAMP High | **Not authorized.** No sponsoring agency, no 3PAO assessment, no ATO | A 3PAO assessment, a sponsoring federal agency, and an Authority to Operate |
| SLSA L3 | **Some L3-shaped CI controls exist** (hash-pinned deps, pip-audit, SBOM, cosign-signed SBOM/circuit artifacts) but there is no SLSA provenance verification pipeline consuming these attestations, and the Docker image itself isn't signed | A verifier that actually checks provenance/signatures before deployment, plus a hermetic, fully reproducible build |

**Roadmap, if pursuing certification:**
1. FIPS 140-3: either adopt an already-validated cryptographic module (e.g., a FIPS-validated
   OpenSSL build) end-to-end, or budget for a CMVP submission — this is a multi-month, paid
   process, not a configuration change.
2. FedRAMP High: requires a sponsoring agency relationship before a 3PAO engagement is even
   possible. Not something to promise a pilot customer on a specific timeline without that
   sponsor identified.
3. SLSA L3: close the gap between "generates attestations" and "a deployment pipeline that
   verifies them before running anything" — currently nothing in this repo consumes the cosign
   signatures it produces.

---

## Appendix: verified against commit history

This document was last reconciled against the codebase on 2026-08-05, checking each claim
against the referenced file rather than trusting prior versions of this document or commit
messages. This repo's history includes multiple "make it real" commits that turned out to be
incomplete — treat any future edit to this document the same way: don't add a claim without
being able to point at the code that backs it.
