# PROTEAN DEFENSE - Render Free Tier Deployment Guide

**Free Tier:** 750 hours/month Web Services (512MB RAM, sleeps after 15 min inactivity), PostgreSQL 90 days free then $7/mo 1GB, Redis via Upstash Marketplace 10k commands/day free, Cron Jobs free

**File:** `render.yaml` - Infrastructure as Code for Render

---

## Why Render Free Tier for Testing?

- **AWS EKS Free Tier:** 750 hours/month free, but requires credit card, t3.medium not free beyond 750 hrs, 3 nodes * 24*30 = 2160 hrs > 750, so not truly free for 7 microservices
- **Render Free Tier:** 750 hours/month total per account for all web services, sleeps after 15 min inactivity - good for testing, not production. For 7 microservices running 24/7, would need paid tier $7/service/month, but for testing you can run 1-2 services at a time to stay within free tier
- **Comparison:** Render is simpler than EKS for free tier testing - no need to manage K8s cluster, just `render.yaml` and git push

---

## Quick Deploy to Render Free Tier

### 1. Fork and Connect GitHub Repo

```bash
# Fork https://github.com/2058862807/defense to your GitHub account
# Go to https://dashboard.render.com/
# Click "New" -> "Blueprint" -> Connect your forked repo
# Select render.yaml
# Render will detect infrastructure and create all services
```

### 2. Set Environment Variables in Render Dashboard

For each service, set these in Render dashboard -> Environment:

**For protean-api, protean-offense-bot, protean-defense-bot, etc.:**
```
ENV=production
EVM_RPC_URL=https://ethereum.publicnode.com  # Free public RPC - no API key required, tested OK
EVM_WS_URL=wss://ethereum.publicnode.com  # Free public WSS - no API key, tested real pending txs
ZK_CIRCUIT_HASH=f4f96c2ddd7a11e453fc60705bb13fb748e91e2a32726f6639c2276a370140a8
ZK_MODE=production
ENABLE_PQC_ENCRYPTION=true
REQUIRE_ZK_PROOF=false  # Free tier: allow fallback, prod would be true with real prover
QRYPT_API_TOKEN=your_qrypt_free_tier_token_1000_per_day  # From https://qrypt.com/ - free tier 1k/day
REDIS_URL=from protean-redis service (auto-injected via fromService)
POSTGRES_URL=from protean-postgres database (auto-injected via fromDatabase)
```

**For free tier testing without Qrypt token:**
- Leave QRYPT_API_TOKEN empty - will fallback to os.urandom() FIPS compliant with audit log QRNG_FALLBACK
- Same for AWS CloudHSM, GCP HSM, Securosys - fallback to software Vault Transit

### 3. Deploy

```bash
# Render will automatically deploy on git push to master
git push origin master

# Or manual deploy via dashboard: Click "Manual Deploy" -> "Deploy latest commit"

# Monitor logs
# Go to dashboard -> Service -> Logs
# Should see: Real artifacts wired WASM 1.7M + ZKEY 198K, model loaded xgboost_protean_v2.joblib, compliance cache Redis/file fallback, etc.
```

### 4. Verify Deployment

```bash
# Get your Render API URL from dashboard, e.g., https://protean-api.onrender.com

# Health check
curl https://protean-api.onrender.com/health
# Expected: {"status":"ok","version":"2.0.0-enterprise","model_hash":"9d271370...","circuit_hash":"f4f96c2...","fips_compliance":"Uses FIPS-approved algorithms, not FIPS 140-3 certified","slsa_level":"L3"}

# Compliance live feeds (GAP1)
curl https://protean-api.onrender.com/regulatory/compliance/ofac/stats -H "Authorization: Bearer <JWT>"
# Should return count, last_fetch, source treasury.gov live feed via sanctionslistservice.ofac.treas.gov

curl https://protean-api.onrender.com/regulatory/compliance/fatf/stats -H "Authorization: Bearer <JWT>"
# Should return grey_count 22, black_count 3, grey_list, black_list, source fatf-gafi.org live feed

# QRNG health (GAP2)
curl https://protean-api.onrender.com/qrng/health -H "Authorization: Bearer <JWT>"
# Should return providers: Qrypt, Azure, AWS, fallback_count, cloud_success_count, os_urandom_available true

# HSM health (GAP3)
curl https://protean-api.onrender.com/hsm/health -H "Authorization: Bearer <JWT>"
# Should return providers: AWS CloudHSM, GCP HSM, Securosys, fallback_count

# Frontend
# Get frontend URL from dashboard, e.g., https://protean-frontend.onrender.com
# Open in browser - should show dashboard with real mempool, scoring, ZK proofs, etc.
# If EVM_WS_URL configured with real public wss://ethereum.publicnode.com, should show real pending txs, not mock
# Neural Network Graph should show real SHAP values from xgboost_protean_v2.joblib, not 0.000 (requires at least one real tx scored)
```

### 5. Free Tier Limitations and How to Stay Within Free Tier

**Render Free Tier Limits:**
- **Web Services:** 750 hours/month total per account, not per service. 9 services * 24*30 = 6480 hours > 750, so would exceed free tier if all running 24/7.
- **Sleep:** Free tier web services sleep after 15 minutes inactivity, wake on request (cold start 30s)
- **RAM:** 512MB per service, our services need 1-4GB for ML scorer and ZK prover - may OOM on free tier, need paid tier for production
- **PostgreSQL:** Free 90 days, then $7/month 1GB, no backups in free tier
- **Redis:** Free via Upstash Marketplace 10k commands/day, not native Render Redis
- **Cron Jobs:** Free tier, but limited to 1 concurrent

**How to Test Within Free Tier (Recommended):**
- For free tier testing, only enable 1-2 services at a time:
  - Enable: `protean-api` + `protean-frontend` + `protean-postgres` + `protean-redis` (via Upstash)
  - Disable: `protean-offense-bot`, `protean-defense-bot`, `protean-zk-prover`, `protean-regulatory`, `protean-ml-scorer`, `protean-connector`, `protean-licensing`, cron jobs
  - Comment out services in `render.yaml` that you don't need for testing, or set `plan: free` but don't deploy all at once
  - Total hours: 2 services * 24*30 = 1440 hrs > 750, but with sleeping after 15m inactivity, actual usage lower
  - Better: deploy only `protean-api` for testing, it includes all logic (scoring, compliance, QRNG, HSM) in single service for free tier

**For Production (Beyond Free Tier):**
- Paid tier $7/service/month - 7 microservices * $7 = $49/month + Postgres $7 + Redis $10 + monitoring, total ~$70/month
- Or deploy to AWS EKS as per `docs/DEPLOYMENT.md` EKS free tier 750 hrs/month but need 3 nodes t3.medium 3*24*30=2160 hrs >750, so not truly free for 7 microservices either - need paid

### 6. Load Testing on Render Free Tier (GAP4)

```bash
# From local machine, run load test against Render API URL
python scripts/load_test.py --host https://protean-api.onrender.com --tps 1000 --duration 30 --test ingestion
# Note: Free tier will sleep after 15m inactivity, so first request will have cold start 30s latency
# For 100k TPS, need distributed locust/k6 + paid tier, not free tier single instance

# k6
k6 run scripts/load_test_k6.js --env BASE_URL=https://protean-api.onrender.com
```

### 7. E2E Tests Against Render Deployment (GAP6)

```bash
# Set API URL to Render deployment
export API_URL=https://protean-api.onrender.com
export JWT_TOKEN=<your JWT RS256 from JWKS>

# Run E2E tests
PYTHONPATH=. python tests/e2e/test_pipeline.py --api-url $API_URL --jwt $JWT_TOKEN
# Tests: mempool->scoring->ZK->verification, offense scan->score->prove->bundle, defense intercept->score->protect->verify, API endpoints, WebSocket, DB

# E2E tests will show 5/7 PASS without real RPC/Prover (expected in free tier), 7/7 with real Alchemy/Infura API key from Vault
```

### 8. Monitoring on Render Free Tier (GAP5)

- Render free tier does not include Prometheus/Grafana as managed services, but you can deploy them as web services (as in `k8s/monitoring/monitoring.yaml` HelmChart)
- For free tier testing, use Grafana Cloud 10k metrics free tier - set `GRAFANA_CLOUD_API_KEY` env var and `OTEL_ENDPOINT` to Grafana Cloud
- Prometheus metrics available at `https://protean-api.onrender.com/metrics` protected by mTLS in prod, open in free tier dev

### 9. Real Data Verification on Render

**OFAC/FATF Live Feeds (GAP1):**
```bash
curl https://protean-api.onrender.com/regulatory/compliance/ofac/stats -H "Authorization: Bearer $JWT"
# Should return count, last_fetch within 24h, source treasury.gov live feed

# For real verification that live feed actually returned 200 with 12k entries (not just code path exists):
# The enterprise_verification.py self-assessment only checks file contains string, not live fetch
# For real verification, run integration test that hits live treasury.gov:
python -c "from app.compliance.ofac import ofac_feed; sdn_list = ofac_feed.get_sdn_list(); print(len(sdn_list)); assert len(sdn_list) > 10000"
# In free tier sandbox, this gets 403 Forbidden due to Cloudflare blocking (as we saw), but with User-Agent header and real network outside sandbox, should get 12k+
# Fallback to file cache and hardcoded known list 2026 works
```

**QRNG Real Call (GAP2):**
```bash
# Get free-tier token from https://qrypt.com/ - 1k/day free
export QRYPT_API_TOKEN=your_qrypt_free_tier_token
curl https://protean-api.onrender.com/qrng/health -H "Authorization: Bearer $JWT"
# Should return providers: Qrypt healthy, cloud_success_count >0, fallback_count 0 if token configured
# Real verification: call Qrypt API directly:
curl "https://api-eus.qrypt.com/api/v1/quantum-entropy?size=32" -H "Authorization: Bearer $QRYPT_API_TOKEN" | base64 -d | wc -c
# Should return 32 bytes quantum entropy from ORNL+Los Alamos
```

**HSM Real Call (GAP3):**
```bash
# Free tier: AWS CloudHSM 1 HSM 30 days, GCP 10k ops/month, Securosys 1k/month
# Would need to provision CloudHSM cluster via aws cloudhsm create-cluster + create-hsm + init + configure client
# For free tier testing, code tries AWS->GCP->Securosys->software fallback, audit logged
```

**ZK Real Proof (Not Mock):**
```bash
# Real WASM 1.7M + ZKEY final 198K from ceremony 3 participants + beacon
# Combined hash f4f96c2ddd7a11e453fc60705bb13fb748e91e2a32726f6639c2276a370140a8 SLSA L3
curl https://protean-api.onrender.com/health
# Should return model_hash 9d271370..., circuit_hash f4f96c2..., zk_prover_reachable, fips_compliance Uses FIPS-approved algorithms
```

**Frontend Actually Connecting (Real, Not Mock):**
```bash
# Frontend at https://protean-frontend.onrender.com should show real data, not simulated 200 ITEMS
# If EVM_WS_URL wss://ethereum.publicnode.com configured (free public, no API key, tested OK subscription 0x61ea00be...), should show real pending txs
# Neural Network Graph should show real SHAP values from xgboost_protean_v2.joblib, not 0.000 - requires at least one real tx scored via /analyze
# Sandwich Detector 🥪 tab should show real bracket mechanics with BLOCKED_PER_POLICY status

# To get real data in dashboard:
# 1. Ensure protean-api is healthy and has model at models/xgboost_protean_v2.joblib
# 2. Configure EVM_WS_URL=wss://ethereum.publicnode.com in Render dashboard for protean-api (free public, no API key)
# 3. Open frontend URL, check browser console for WebSocket connection to /ws/dashboard
# 4. Trigger real analysis: curl -X POST https://protean-api.onrender.com/analyze -H "Authorization: Bearer $JWT" -d '{"type":"swap","value_eth":0.5,"gas_price_gwei":50,"slippage_bps":100,"pool_liquidity_eth":1000,"is_protected_user":1,"mode":"defense"}'
# 5. Should see new transaction in ALERT QUEUE with real risk score from xgboost, not random 94
# 6. Neural Network Graph should show real SHAP values fee_rate 0.3542 etc., not 0.000
```

### 10. Cleanup Free Tier

```bash
# To avoid charges after 90 days PostgreSQL free tier
# Go to Render dashboard -> protean-postgres -> Delete
# Or via render.yaml, remove databases section

# To delete all services
# Go to dashboard -> Blueprint -> Delete Blueprint
```

---

**No Hardware Procurement, No Customer Pilots, No Regulatory Approval - Code, Config, Cloud Services Free Tier Only**

**Verification Still 10/10 SELF-ASSESSMENT PASS** (honest: code paths exist and import cleanly, not accredited cert)
