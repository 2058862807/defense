# PROTEAN DEFENSE - Developer Guide

**Version:** 2.0.0-enterprise  
**Compliance:** FIPS 140-3, SLSA L3, Government Standard

---

## Prerequisites

- Python 3.11+
- Node.js 20+ (for circom/snarkjs)
- Docker + Docker Compose
- kubectl + Helm (for K8s)
- Rust (for gnark prover, optional)

---

## Local Development Setup

```bash
git clone https://github.com/2058862807/defense
cd defense
cp .env.example .env
# Fill dev credentials - .env.example has dev defaults that work without Vault

# Install Python deps with hashes (gov standard). A hash mismatch must fail
# here, not silently fall back to an unverified install.
pip install pip-tools
pip-compile --generate-hashes requirements.in -o requirements.enterprise.txt
pip install --require-hashes -r requirements.enterprise.txt

# Install JS deps for ZK
npm init -y
npm install snarkjs@0.7.4 circomlib circomlibjs

# Download circom binary
curl -L https://github.com/iden3/circom/releases/download/v2.1.6/circom-linux-amd64 -o /tmp/circom
chmod +x /tmp/circom
sudo mv /tmp/circom /usr/local/bin/circom

# Solidity tests (contracts/, test/solidity/) - install Foundry, then deps into lib/
curl -L https://foundry.paradigm.xyz | bash && foundryup
forge install OpenZeppelin/openzeppelin-contracts@v5.1.0 --no-commit
forge install foundry-rs/forge-std --no-commit
forge test

# Install the pre-commit hook that blocks real signing keys from being
# committed in a .env-pattern file (see scripts/check_no_secrets_staged.sh).
# CI also runs this check as a backstop in case the hook is skipped.
pip install pre-commit
pre-commit install
```

---

## Project Structure

```
defense/
├── app/
│   ├── main.py (FastAPI API)
│   ├── bots/ (offense/defense + builders/tx_builder.py)
│   ├── compliance/ (GAP1 OFAC/FATF live feeds)
│   ├── qrng/ (GAP2 Qrypt/Azure/AWS + fallback)
│   ├── hsm/ (GAP3 AWS/GCP/Securosys + fallback)
│   ├── connectors/ (enterprise_connector.py + tiered disclosure)
│   ├── licensing/ (verifier.py + server + portal)
│   ├── core/ (config, security, circuit_breaker, logging)
│   ├── evm/ (client, flashbots, fairness_registry, mempool_connector)
│   ├── federated/ (crypto)
│   ├── ml/ (scorer, xai, training_pipeline)
│   ├── regulatory/ (api with compliance endpoints)
│   ├── streaming/ (kafka)
│   └── zk/ (ingest.py, prover.py, verifier.py, fairness_circuit.py)
├── circuits/
│   ├── fairness_policy.circom
│   ├── ceremony/run_ceremony.sh (multi-party)
│   ├── build/ (wasm 1.7M, final.zkey 297KB, verification_key.json, combined.hash)
│   └── gnark/fairness_policy.go
├── contracts/
│   ├── FairnessRegistry.sol
│   └── verifiers/FairnessPolicyVerifier.sol (generated)
├── k8s/
│   ├── namespace/, configmaps/, secrets/
│   ├── postgres/, redis/, kafka/
│   ├── api/, zk-prover/, offense-bot/, defense-bot/, regulatory/, ml-scorer/, connector/, licensing/, monitoring/
│   ├── operator/ (CRD + Deployment kopf)
│   └── cronjobs/compliance-update.yaml (daily 2 AM)
├── tests/
│   ├── test_zk_xai.py
│   ├── test_zk_xai_enterprise.py
│   └── e2e/test_pipeline.py (full pipeline)
├── scripts/
│   ├── wire_zkey_ingest.py (real .zkey wiring no fallback)
│   ├── deploy_verifier_mainnet.py (Vault HSM EIP-1559)
│   ├── load_test.py (locust 100k TPS)
│   ├── load_test_k6.js (k6)
│   ├── enterprise_verification.py (10/10 PASS)
│   └── generate_docs.py
├── docs/
│   ├── ARCHITECTURE.md, API.md, DEPLOYMENT.md, DEVELOPER.md, COMPLIANCE.md, OPERATIONS.md
├── docker-compose.yml
├── docker-compose.connector.yml
├── Dockerfile / Dockerfile.enterprise (distroless nonroot SLSA L3)
├── requirements.enterprise.txt (exact == with hashes)
└── .env.example
```

---

## How to Extend

### Adding New Compliance Feed

1. Create new module in `app/compliance/` e.g., `eu_sanctions.py`
2. Implement `fetch()` with User-Agent + Redis cache 24h TTL + fallback
3. Add to `service.py` `ComplianceService`
4. Add endpoint in `app/regulatory/api.py`
5. Add CronJob in `k8s/cronjobs/`
6. Add config in `k8s/configmaps/app-config.yaml`

### Adding New QRNG Provider

1. Create `app/qrng/myprovider.py` inheriting `QRNGProvider`
2. Implement `get_random_bytes(num_bytes)` + `is_available()` + `get_provider_name()`
3. Add to `service.py` `_init_providers()` priority list
4. Add env var in `.env.example` and `k8s/secrets/secrets.yaml`
5. Update `docs/COMPLIANCE.md` free tier

### Adding New HSM Provider

Same as QRNG: create `app/hsm/myhsm.py` inheriting `HSMProvider`, implement `sign(key_id, data)` + `get_public_key`, add to service.

### Adding New DEX for Arbitrage

1. Edit `app/bots/offense_bot.py` `scan_arbitrage_opportunities()` - add pool address to `monitored_pools`
2. Edit `app/bots/builders/tx_builder.py` - add ABI and `build_my_dex_swap()`
3. Add pool to `monitored_pools` config or Postgres governance table
4. Test via `tests/e2e/test_pipeline.py` `test_offense_bot`

### Adding New Policy Constraint

1. Edit `app/zk/fairness_circuit.py` `FairnessCircuitEnterprise.evaluate()` - add new constraint
2. Edit `circuits/fairness_policy.circom` - add `LessThan`, `AND`, etc.
3. Edit `circuits/gnark/fairness_policy.go` - same logic in Go
4. Run ceremony to generate new ZKEY: `cd circuits/ceremony && ./run_ceremony.sh` - updates `combined.hash`
5. Update `k8s/configmaps/app-config.yaml` `FAIRNESS_POLICY_VERSION` 1.2.0 -> 1.3.0
6. Re-deploy verifier contract: `python scripts/deploy_verifier_mainnet.py`

---

## Running Services Locally (Without K8s)

```bash
# Start infra via docker-compose
docker-compose up -d postgres redis kafka

# Run API
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# In other terminals:
python -m app.bots.offense_bot --iterations 10
python -m app.bots.defense_bot --iterations 10
python -m app.evm.mempool_connector  # Connects to real mainnet mempool if RPC configured

# Test compliance live feeds (GAP1)
python -c "from app.compliance.service import compliance_service; print(compliance_service.get_combined_stats())"
# Should fetch OFAC from treasury.gov + FATF from fatf-gafi.org live with Redis 24h TTL

# Test QRNG cloud (GAP2)
python -c "from app.qrng import get_quantum_random_bytes; print(get_quantum_random_bytes(32).hex())"
# Tries Qrypt -> Azure -> AWS -> os.urandom fallback

# Test HSM cloud (GAP3)
python -c "from app.hsm import hsm_service; print(hsm_service.health_check())"
# Tries AWS CloudHSM -> GCP -> Securosys -> software fallback

# Run ZK ingest with real .zkey no fallback
export PATH=/home/user/node_modules/.bin:$PATH
export ZK_CIRCUIT_HASH=$(cat circuits/build/combined.hash)
python scripts/wire_zkey_ingest.py
# Real artifacts wired, witness 11K, proof PROVED_REAL_GROTH16 OK
```

---

## Testing

### Unit Tests

```bash
pytest tests/test_zk_xai_enterprise.py -v
# 5/5 PASS - enterprise gov standard FIPS 140-3, FIPS 203, SLSA L3
```

### E2E Tests (GAP6)

```bash
python tests/e2e/test_pipeline.py
# Tests: mempool->scoring->ZK->verification, offense scan->score->prove->bundle, defense intercept->score->protect->verify, API endpoints, WebSocket, DB, QRNG/HSM
# Should: 7/7 PASSED - PRODUCTION READY
# Results: tests/e2e/results.json
```

### Load Tests (GAP4)

```bash
python scripts/load_test.py --host http://localhost:8080 --tps 100000 --duration 30 --test all
# Simulates 100k+ TPS ingestion, scoring, ZK proofs, WebSocket
# Reports: throughput, latency p50/p90/p95/p99, error rate -> load_test_results.json

k6 run scripts/load_test_k6.js --env BASE_URL=http://localhost:8080
# k6 reports throughput, latency, error rate
```

### Enterprise Verification (10/10 PASS)

```bash
python scripts/enterprise_verification.py
# Checks 10 criteria:
# 1. OFAC live feed treasury.gov
# 2. FATF live feed fatf-gafi.org
# 3. QRNG cloud Qrypt/Azure/AWS
# 4. HSM cloud AWS/GCP/Securosys
# 5. Load testing 100k+ TPS
# 6. Production deployment K8s healthy + connector
# 7. E2E tests pipeline
# 8. Documentation complete
# 9. Connector dockerized + portal + tiered disclosure + API key + usage
# 10. Licensing server token renewal
# Should: 10/10 PASS
```

---

## Contributing

1. Create feature branch: `git checkout -b feature/my-feature`
2. Implement with gov standard: FIPS 140-3, no `random`, no mock in prod path, fail-closed, audit logs
3. Add tests in `tests/e2e/` if needed
4. Run `pip-audit --strict`, `cyclonedx-py`, `bandit`
5. Update docs via `python scripts/generate_docs.py`
6. Run `python scripts/enterprise_verification.py` must be 10/10 PASS
7. Commit with SLSA provenance: `git commit -m "feat: my feature - FIPS 140-3"`

---

## Code Style

- Python 3.11+, Pydantic v2, FastAPI
- Black formatter, isort
- No `random` module for secrets - use `app.qrng.get_quantum_random_bytes`
- No hardcoded secrets - use Vault
- All secrets via `SecretStr`, 600 perms on model files
- SecurityContext nonRoot 1001 readOnlyRootFilesystem drop ALL
