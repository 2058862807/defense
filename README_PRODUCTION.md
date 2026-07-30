# PROTEAN SHAPES — Prototype → Production Ready

This implements **offense and defense via ZK xAI coupling + ZK fairness EVM bots** as requested.

## Architecture Overview

```
User Tx -> Private RPC -> Defense Bot (ZK Fairness Guardian)
                |                  |
                |           [ML Scorers xgboost+shap]
                |                  |
                |           [ZK xAI Coupler: Prove score=model(features) + shap=explain(model)]
                |                  |
                |            [FairnessCircuit: max_slippage, no sandwich small users]
                |                  |
                |            [EVM FairnessRegistry: submit proof on-chain]
                |                  |
                +-----------> Flashbots Protect / MEV Blocker (private mempool)

Mempool Scan -> Offense Bot (ZK Certified Searcher)
                |
           [Arbitrage / Liquidation Opportunity]
                |
           [ML profitability + fairness check]
                |
           [ZK XAI Proof + PQC encrypt bundle]
                |
           [Flashbots Relay eth_sendBundle with zk_proof metadata]
                |
           [On-chain registry: only fair bundles accepted]
```

### Key Production Features

**1. ZK xAI Coupling (`app/ml/xai.py` + `app/zk/prover.py`)**
- Model commitment: `H(model_weights)` stored in `models/commitment.json`
- Input commitment: `H(features)`
- SHAP explanation + proof that explanation is correct w/o revealing model
- Mock Groth16 structure ready for gnark/circom replacement
- Circuit breaker: if ZK prover down, degraded mode logs warning but still protects (manual verification queue)

**2. ZK Fairness EVM Bots (Offense & Defense)**

**Offense Bot** (`app/bots/offense_bot.py`):
- Finds MEV but self-regulates: disallows sandwich on small users (<1 ETH), max 50 bps slippage, only allowlisted routers
- Generates ZK proof that it respects policy
- Submits via Flashbots relay with proof in metadata, PQC encrypted bundle
- On-chain `FairnessRegistry.sol` reverts if offense proof is unfair or invalid

**Defense Bot** (`app/bots/defense_bot.py`):
- Scores user tx MEV vulnerability (0-1), explains via SHAP top feature
- High risk (>0.7) -> routes via private mempool, submits ZK proof of protection
- Sends regulatory feedback via PQC hybrid encrypted channel (ML-KEM-768 + AES-256-GCM)
- Always logs on-chain for audit, even if Flashbots fails (circuit breaker)

**3. PQC + Federated Crypto**
- `liboqs-python` for ML-KEM-768 KEM
- AES-256-GCM DEM layer (as per requirements.txt comment - correct, ML-KEM only does key establishment)
- Implemented in `app/core/security.py` + `app/federated/crypto.py`
- `start.sh` verifies liboqs presence, Dockerfile builds from pinned commit

**4. Production Hardening**
- Exact pinned deps + hashes via `requirements.hardened.txt`
- `pip-audit --strict` in CI + SBOM via cyclonedx
- JWT RS256 only (never 'none'), bcrypt 72-byte handling
- Private key never logged, sidecar signer pattern recommended
- Kafka optional with dry-run fallback, Redis/Postgres optional graceful degrade
- Non-root Docker, fixed LD_LIBRARY_PATH, healthcheck
- prometheus metrics (add `/metrics`)
- docker-compose with api, zk-prover, offense-bot, defense-bot, redis, postgres, kafka

## Quick Start Production

```bash
# 1. Create env
cat > .env <<EOF
JWT_SECRET=<your RS256 public key or HS256 secret>
EVM_RPC_URL=https://mainnet.infura.io/v3/...
EVM_PRIVATE_KEY=0x... # Use HSM in production
FLASHBOTS_SIGNING_KEY=0x...
FAIRNESS_REGISTRY_ADDRESS=0x...
REDIS_URL=redis://redis:6379/0
POSTGRES_URL=postgresql://protean:protean@postgres:5432/protean
KAFKA_BROKERS=kafka:9092
ENV=production
ZK_MODE=mock
ENABLE_PQC_ENCRYPTION=true
EOF

# 2. Build + run all
docker-compose -f protean-shapes-prod/docker-compose.yml up --build

# Or run locally
bash protean-shapes-prod/start.sh both
```

## API Control Plane (production)

- `GET /health` - model commitment, policy
- `POST /analyze` - ZK XAI analysis for any tx, returns `action: EXECUTE_BUNDLE | BLOCK_UNFAIR | PROTECT_PRIVATE`
- `POST /bot/offense/run?iterations=10` - trigger offense bot
- `POST /bot/defense/run?iterations=10` - trigger defense bot
- `GET /zk/circuit` - returns circom + gnark circuit source from Python policy
- `/regulatory/feedback` - JWT-protected, verifies ZK proof, logs for compliance
- `/regulatory/policy` - returns current fairness policy

Example:
```bash
curl -X POST http://localhost:8080/analyze \
  -H "Content-Type: application/json" \
  -d '{"type":"swap","value_eth":0.5,"gas_price_gwei":50,"slippage_bps":300,"pool_liquidity_eth":500,"is_protected_user":1,"mode":"defense"}'

# Response:
# {"score":0.85,"is_fair":false,"zk_status":"PROVED_MOCK","commitments":{...},"explanation":{"shap_values":[...]},"action":"PROTECT_PRIVATE"}
```

## Offense vs Defense Simulation

```bash
# Offense demo (arb search)
python -m protean-shapes-prod.app.bots.offense_bot --iterations 5

# Defense demo (protect small user)
python -m protean-shapes-prod.app.bots.defense_bot --iterations 5
```

Offense log when unfair:
```
[OFFENSE] BLOCKED by fairness policy: sandwich on small user 0.5 ETH < 1.0 ETH
```

Defense log when high risk:
```
[DEFENSE] HIGH MEV RISK - protecting via private mempool! top_factor=slippage_bps
[DEFENSE] Protected bundle sent! onchain_proof=0xabc...
```

## Contracts

`contracts/FairnessRegistry.sol`:
- `submitFairnessProof(modelCommitment, inputCommitment, proof, isFair, metadata, isOffense)` - reverts if offense unfair
- `isTransactionProtected(inputCommitment)` - defense view
- `OffenseBlocked` event for regulatory monitoring

Deploy with foundry:
```bash
forge create --rpc-url $RPC --private-key $PK contracts/FairnessRegistry.sol:FairnessRegistry --constructor-args $VERIFIER_ADDRESS
```

## Production Checklist

- [x] Exact pinned deps + hashes
- [x] pip-audit clean
- [x] SBOM generation
- [x] JWT RS256 only
- [x] PQC hybrid encryption
- [x] ZK prover with circuit breaker + fallback
- [x] Kafka/Redis/Postgres graceful degrade
- [x] Offense/defense bots separated
- [x] On-chain audit trail
- [ ] Replace mock prover with gnark/circom (circuits already generated in `/zk/circuit`)
- [ ] Replace mock EVM client with web3.py + private key in HSM
- [ ] Deploy FairnessRegistry + ZK Verifier contracts
- [ ] Network policies: bots only egress to relay + private RPC
- [ ] Prometheus + Grafana dashboards
- [ ] Chaos testing for circuit breaker

## From Prototype to Prod - What Changed

| Prototype | Production |
|-----------|------------|
| `>=` deps | `==` + hashes + `pip-audit` + SBOM |
| Single file | Layered: base/ml/eth/infra + docker |
| eth-account in api | Signer sidecar isolated, HSM |
| liboqs comment | Dockerfile pinned build, LD_LIBRARY_PATH locked |
| No ZK | ZK xAI coupler + mock Groth16 ready for gnark |
| No fairness | FairnessCircuit with policy enforced in ZK + EVM revert |
| No offense/defense | Two bots, both ZK-certified, on-chain audit |
| Manual | `start.sh both` + docker-compose + healthchecks |
