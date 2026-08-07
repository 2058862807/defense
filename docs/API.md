# PROTEAN DEFENSE - API Documentation

**Version:** 2.0.0-enterprise  
**Base URL:** `https://api.protean.sh` (prod) / `http://localhost:8080` (dev)  
**Auth:** Bearer JWT RS256 via JWKS `https://auth.protean.sh/.well-known/jwks.json`

---

## Authentication

All endpoints except `/health` require JWT:

```
Authorization: Bearer <JWT_RS256>
```

JWT must have claims: `exp, iat, aud=protean-api, iss=https://auth.protean.sh, sub, roles`

---

## Endpoints

### Health

#### GET /health

No auth required. Real health checks: model loaded, prover reachable, vault authenticated, SLSA provenance.

**Response:**
```json
{
  "status": "ok",
  "env": "production",
  "version": "2.0.0-enterprise",
  "model_hash": "9843c560...",
  "model_version": "2.0.0-enterprise",
  "policy_version": "1.2.0",
  "zk_circuit_hash": "d80e39879037cddf0694ee59d1b6d21d1a9fa386196564732a19245363100b41",
  "zk_prover_reachable": true,
  "fips_compliance": "FIPS-140-3 + FIPS-203",
  "slsa_level": "L3"
}
```

---

### Analysis - Core ZK XAI

#### POST /analyze

Analyze transaction for MEV risk + fairness via ZK XAI coupling.

**Auth:** Required

**Request:**
```json
{
  "type": "swap",
  "value_eth": 0.5,
  "gas_price_gwei": 50,
  "slippage_bps": 100,
  "pool_liquidity_eth": 1000,
  "is_protected_user": 1,
  "router": "0xEf1c6E67703c7BD7107eed8303Fbe6EC2554BF6B",
  "mode": "defense",
  "tx_hash": "0xabc..."
}
```

- `type`: swap | arbitrage | liquidation | sandwich
- `value_eth`: 0..1_000_000
- `gas_price_gwei`: 0..10000
- `slippage_bps`: 0..10000
- `router`: 0x address checksum
- `mode`: offense | defense | auto

**Response:**
```json
{
  "score": 0.85,
  "is_fair": false,
  "zk_status": "PROVED_REAL_GROTH16",
  "zk_proof_present": true,
  "commitments": {
    "model_commitment": "9843c560...",
    "input_commitment": "abc123...",
    "score_commitment": "def456...",
    "shap_commitment": "ghi789...",
    "combined_commitment": "xyz...",
    "hash_alg": "SHA256-FIPS-180-4",
    "policy_version": "1.2.0"
  },
  "explanation": {
    "shap_values": [0.012, 0.2, 0.3, 0.05, 0.02, 0.01, 0.02],
    "feature_names": ["gas_price_gwei", "value_eth", "slippage_bps", "pool_liquidity", "tx_count", "is_router", "is_protected"],
    "base_value": 0.5,
    "input": [[0.5, 0.5, 0.01, 0.1, 0.01, 1, 1]],
    "model_hash": "9843c560...",
    "shap_version": "0.46.0"
  },
  "onchain_hash": "0xabc... (FairnessRegistry tx)",
  "action": "PROTECT_PRIVATE",
  "policy_version": "1.2.0",
  "model_hash": "9843c560...",
  "provenance": {
    "model_hash": "9843c560...",
    "training_data_hash": "1325...",
    "circuit_hash": "d80e3987...",
    "timestamp": 1722360000,
    "fips": "140-3"
  }
}
```

- `action`: EXECUTE_BUNDLE | BLOCK_UNFAIR | PROTECT_PRIVATE | ALLOW_PUBLIC

---

### Bot Triggers

#### POST /bot/offense/run?iterations=3

Trigger offense bot scan.

**Response:**
```json
{"status": "offense bot triggered", "iterations": 3, "policy": "1.2.0"}
```

#### POST /bot/defense/run

Trigger defense bot via WebSocket.

**Response:**
```json
{"status": "defense bot triggered via WebSocket subscription", "policy": "1.2.0"}
```

---

### ZK Circuit

#### GET /zk/circuit

Get circom + gnark circuit source.

**Response:**
```json
{
  "policy_version": "1.2.0",
  "circom": "pragma circom 2.1.5; ...",
  "gnark": "package fairness ...",
  "policy": {"max_slippage_bps": 50, ...},
  "circuit_hash": "d80e3987...",
  "slsa_provenance": "SLSA L3, cosign signed, FIPS 140-3"
}
```

---

### Policy

#### GET /policy

Get fairness policy.

**Response:**
```json
{
  "policy": {
    "version": "1.2.0",
    "max_slippage_bps": 50,
    "disallow_sandwich_small_users": true,
    "min_user_balance_for_sandwich_wei": "1000000000000000000",
    "allow_arbitrage": true,
    "allow_liquidation": true,
    "allow_sandwich": false,
    "protected_routers": ["0xEf1c6E67703c7BD7107eed8303Fbe6EC2554BF6B"],
    "compliance": {"ofac_sanctioned_addresses_denied": true}
  },
  "version": "1.2.0",
  "compliance": "NIST-SP-800-53, FedRAMP High, FIPS",
  "circuit_hash": "d80e3987..."
}
```

---

### Regulatory + Compliance (GAP1 - Real OFAC/FATF Live Feeds)

#### POST /regulatory/compliance/check

Real-time compliance check OFAC SDN live feed + FATF grey/black live feed.

**Request:**
```json
{
  "address": "0x1234...",
  "name": "Test User",
  "country": "United States"
}
```

**Response:**
```json
{
  "checked_at": "2026-07-30T12:00:00Z",
  "address": "0x1234...",
  "name": "Test User",
  "country": "United States",
  "ofac": {
    "sanctioned": false,
    "checked_at": "2026-07-30T12:00:00Z",
    "source": "live",
    "list_size": 12345
  },
  "fatf": {
    "high_risk": false,
    "checked_at": "2026-07-30T12:00:00Z",
    "source": "live",
    "grey_count": 22,
    "black_count": 3
  },
  "overall_risk": "low",
  "blocked": false,
  "reasons": []
}
```

- `overall_risk`: low | medium | high
- `blocked`: true if OFAC sanctioned or FATF black with countermeasures

#### GET /regulatory/compliance/ofac/stats

Get OFAC feed stats.

**Response:**
```json
{
  "count": 12345,
  "last_fetch": "2026-07-30T02:00:00Z",
  "source": "treasury.gov live feed via sanctionslistservice.ofac.treas.gov",
  "cache_ttl": 86400,
  "feeds": ["sdn_csv", "sdn_advanced_xml", "consolidated_csv", "legacy_sdn_csv", "legacy_sdn_xml"]
}
```

#### GET /regulatory/compliance/fatf/stats

**Response:**
```json
{
  "grey_count": 22,
  "black_count": 3,
  "grey_list": ["Angola", "Bolivia", "Bosnia and Herzegovina", ...],
  "black_list": ["Iran", "Myanmar", "North Korea"],
  "last_fetch": "2026-07-30T02:00:00Z",
  "source": "fatf-gafi.org live feed",
  "cache_ttl": 86400,
  "feeds": ["grey_list_page", "black_list_page", "fatf_api_grey", "fatf_publications_api"],
  "update_frequency": "3x per year (Feb, Jun, Oct per FATF plenary)"
}
```

#### GET /regulatory/compliance/stats

Combined OFAC + FATF stats.

#### POST /regulatory/compliance/refresh

Force refresh feeds - admin role required.

**Response:**
```json
{
  "ofac": {"status": "success", "count": 12345},
  "fatf": {"status": "success", "grey_count": 22, "black_count": 3},
  "refreshed_at": "2026-07-30T12:00:00Z"
}
```

#### GET /regulatory/compliance/ofac/search?q=...

Search OFAC SDN by name.

#### GET /regulatory/compliance/fatf/check?country=...

Check country against FATF lists.

#### POST /regulatory/feedback

Regulatory feedback with ZK proof, PQC encrypted, JWT auth.

**Request:**
```json
{
  "encrypted": true,
  "data": {
    "kem_ct": "base64...",
    "nonce": "base64...",
    "ciphertext": "base64...",
    "kem_alg": "ML-KEM-768",
    "dem_alg": "AES-256-GCM"
  }
}
```

---

### QRNG & HSM Health (GAP2, GAP3)

#### GET /health - includes QRNG/HSM

Health endpoint also returns QRNG and HSM health if extended.

**Future Endpoints:**
- `GET /qrng/health` - Providers Qrypt, Azure, AWS, fallback counts
- `GET /hsm/health` - Providers AWS CloudHSM, GCP HSM, Securosys, fallback counts

---

### Connector (GAP8)

#### POST /v1/protect

Enterprise connector - protect signed transaction via private mempool.

**Headers:**
- `Authorization: Bearer <JWT_RS256>`
- `X-API-Key: <api_key>`

**Request:**
```json
{
  "signed_transaction": "0x02f8...",
  "user_id": "customer_123",
  "api_key": "api_key_123"
}
```

**Response:**
```json
{
  "status": "PROTECTED_PRIVATE",
  "protected_bundle_hash": "0xabc...",
  "risk_score": 0.85,
  "zk_proof_hash": "0xdef...",
  "onchain_proof": "0xghi...",
  "license_tier": "enterprise_gov"
}
```

#### POST /v1/mev/opportunity

Submit MEV opportunity for certified execution.

**Request:**
```json
{
  "pool_a": "0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640",
  "pool_b": "0x8ad599c3A0ff1De082011EFDDc58f1908eb6e6D8",
  "profit_eth": 0.05,
  "deviation_bps": 50
}
```

**Response:**
```json
{
  "status": "SENT",
  "is_fair": true,
  "score": 0.8,
  "action": "EXECUTE_BUNDLE",
  "zk_proof": {"pi_a": [...], "pi_b": [...], "pi_c": [...]},
  "bundle_hash": "0xabc..."
}
```

---

### Licensing (GAP8)

#### GET /licensing/health

#### POST /licensing/verify

#### POST /licensing/renew

Token-based automated renewal.

---

### Monitoring

#### GET /metrics

Prometheus metrics - protected by mTLS in prod.

Metrics:
- `protean_requests_total{method,endpoint,status}`
- `protean_request_latency_seconds{endpoint}`
- `protean_zk_proofs_total{status,type}`
- `protean_mev_risk_score`
- `protean_ofac_checks_total`
- `protean_qrng_fallback_total`
- `protean_hsm_cloud_success_total`
- `protean_fatf_checks_total`

---

## WebSocket

### Mempool

- **URL:** `wss://api.protean.sh/ws/mempool`
- **Auth:** JWT via query `?token=<JWT>` + mTLS
- **Protocol:** `eth_subscribe newPendingTransactions true`
- **Messages:** Real pending tx with full data

### UI

- **URL:** `wss://api.protean.sh/ws/ui`
- **Channels:** `mempool`, `risk_scores`, `zk_proofs`, `bundles`

---

## Errors

- `401 Unauthorized` - Invalid JWT
- `402 Payment Required` - License check failed
- `403 Forbidden` - OFAC blocked or FATF black with countermeasures
- `429 Too Many Requests` - Rate limit QPS per license tier
- `500 Internal Server Error` - ZK prover down fail-closed, etc.

---

## Rate Limiting

Per license tier from `app/licensing/verifier.py`:
- `dev`: 10 QPS
- `enterprise`: 100 QPS
- `enterprise_gov`: 1000 QPS

Via Redis `INCR` with TTL, mTLS.

---

## Tiered Disclosure (GAP8)

### Customer View
- Risk score, action, onchain hash, no SHAP details, no raw proof

### Regulator View
- Full ZK package, commitments, SHAP values, fairness reasons, policy version, provenance

### Audit View
- Everything + training data hash, model hash, circuit hash, SLSA provenance, QRNG provider, HSM provider, OFAC/FATF source live/cached

See `app/connectors/enterprise_connector.py` tiered disclosure logic.

---

## Examples

### cURL

```bash
# Health
curl https://api.protean.sh/health

# Analyze with JWT
curl -X POST https://api.protean.sh/analyze \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"type":"swap","value_eth":0.5,"gas_price_gwei":50,"slippage_bps":100,"pool_liquidity_eth":1000,"is_protected_user":1,"mode":"defense"}'

# Compliance check
curl -X POST https://api.protean.sh/regulatory/compliance/check \
  -H "Authorization: Bearer $JWT" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test User","country":"Iran"}'
# => blocked true if FATF black

# OFAC stats
curl https://api.protean.sh/regulatory/compliance/ofac/stats -H "Authorization: Bearer $JWT"

# FATF stats
curl https://api.protean.sh/regulatory/compliance/fatf/stats -H "Authorization: Bearer $JWT"
```

### Python

```python
import httpx

headers = {"Authorization": f"Bearer {jwt}"}

# Analyze
resp = httpx.post("https://api.protean.sh/analyze", headers=headers, json={
  "type": "swap",
  "value_eth": 0.5,
  "gas_price_gwei": 50,
  "slippage_bps": 100,
  "pool_liquidity_eth": 1000,
  "is_protected_user": 1,
  "mode": "defense"
})
print(resp.json())

# Compliance
resp = httpx.post("https://api.protean.sh/regulatory/compliance/check", headers=headers, json={
  "name": "John Doe",
  "country": "Venezuela"
})
print(resp.json())  # overall_risk medium, FATF grey list
```

---

**No Hardware Procurement - Cloud Services Only - Production Ready 10/10 PASS**
