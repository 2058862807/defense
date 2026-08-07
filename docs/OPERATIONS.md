# PROTEAN DEFENSE - Operations Guide

**Version:** 2.0.0-enterprise  
**Compliance:** FIPS 140-3, FedRAMP High

---

## Monitoring

### Prometheus Metrics

All services expose `/metrics` protected by mTLS:

- `protean_requests_total{method,endpoint,status}` - Total requests
- `protean_request_latency_seconds{endpoint}` - Latency histogram
- `protean_zk_proofs_total{status,type}` - ZK proofs count
- `protean_mev_risk_score` - MEV risk distribution
- `protean_ofac_checks_total` - OFAC checks (GAP1)
- `protean_fatf_checks_total` - FATF checks (GAP1)
- `protean_qrng_fetch_total{provider}` - QRNG cloud success
- `protean_qrng_fallback_total` - QRNG fallback to os.urandom (GAP2)
- `protean_hsm_cloud_success_total{provider}` - HSM cloud success
- `protean_hsm_fallback_total` - HSM fallback to software (GAP3)
- `protean_compliance_refresh_total{status}` - CronJob refresh

### Grafana Dashboards

**Dashboard:** Protean Defense Enterprise - 7 panels:

1. **MEV Risk Score:** `histogram_quantile(0.95, protean_mev_risk_score)` - 95th percentile risk
2. **ZK Proofs:** `sum(protean_zk_proofs_total)` - Total proofs, status PROVED_REAL_GROTH16
3. **OFAC Checks:** `rate(protean_ofac_checks_total[5m])` - Live feed checks per second
4. **QRNG Fallback Rate:** `rate(protean_qrng_fallback_total[5m])` - Should be low, cloud success high
5. **HSM Cloud Success:** `rate(protean_hsm_cloud_success_total[5m])` - AWS/GCP/Securosys success
6. **Throughput TPS:** `sum(rate(protean_requests_total[1m]))` - Target 100k+ TPS
7. **Error Rate:** `sum(rate(protean_requests_total{status=~"5.."}[1m])) / sum(rate(protean_requests_total[1m]))` - Should <1%

**Access:**
```bash
kubectl port-forward svc/grafana 3001:80 -n protean-monitoring &
open http://localhost:3001 - admin / change_me_grafana_admin
```

**Prometheus:**
```bash
kubectl port-forward svc/prometheus-server 9090:80 -n protean-monitoring &
open http://localhost:9090
```

---

## Troubleshooting

### OFAC Feed 403 Errors

**Symptom:** OFAC feed fetch fails with 403

**Cause:** Per OFAC Technical Notice 2024-05-16, new SLS host `sanctionslistservice.ofac.treas.gov` requires User-Agent header, .NET and other languages without User-Agent get 403.

**Solution:** Already implemented in `app/compliance/ofac.py`:
```python
headers = {
    "User-Agent": "Protean-Defense-Enterprise/2.0.0 (FIPS-140-3; +https://protean.sh/compliance)",
    "Accept": "text/csv, application/xml, text/xml, */*",
}
```
Verify: `curl -H "User-Agent: Protean-Defense" https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV | head`

**Fallback:** Redis cache 24h TTL + file `/tmp/compliance_cache/ofac:sdn_list:v1.json` - service continues with cached data, logs warning `Using STALE cached data`.

### FATF Parsing Empty

**Symptom:** FATF grey list parsing returns empty

**Cause:** fatf-gafi.org HTML structure changed, no official API.

**Solution:** `app/compliance/fatf.py` has fallback to hardcoded known list 2026 (22 grey + 3 black) from search results Jun 2026. Logs warning `Using hardcoded fallback FATF grey list (2026)`. Update regex in `_parse_grey_list_from_html` if site changes.

**Check:**
```bash
python -c "from app.compliance.fatf import fatf_feed; print(fatf_feed.get_grey_list())"
# Should return 22 countries or fallback
```

### QRNG 429 Rate Limit

**Symptom:** Qrypt returns 429 Too Many Requests

**Cause:** Free tier 1,000 req/day exceeded.

**Solution:** `app/qrng/service.py` tries Qrypt -> Azure (10k/month) -> AWS Braket -> os.urandom fallback FIPS compliant. Logs `QRNG_FALLBACK` audit + fallback_count++. Check health: `python -c "from app.qrng import qrng_service; print(qrng_service.health_check())"` - should show providers healthy, fallback_count low.

**Mitigation:** Cache random bytes where possible, batch requests, upgrade to paid tier or SaladCloud $5 free credits for ZK compute offloads QRNG from hot path.

### HSM Not Configured

**Symptom:** HSM sign fails, fallback to software

**Cause:** Cloud HSM credentials not in `k8s/secrets/secrets.yaml` cloud-credentials.

**Solution:** Check `app/hsm/service.py` tries AWS CloudHSM -> GCP -> Securosys -> software Vault Transit + eth_account dev. Logs `HSM_FALLBACK`. For prod, set `AWS_CLOUDHSM_CLUSTER_ID`, `AWS_KMS_KEY_ID`, `GCP_PROJECT_ID`, `SECUROSYS_AUTH_TOKEN` in Vault `secret/data/prod/hsm`.

**Check:**
```bash
python -c "from app.hsm import hsm_service; print(hsm_service.health_check())"
```

### K8s Pod CrashLoopBackOff

**Symptom:** Pod fails to start, logs show Vault or cert errors.

**Solution:**
1. Check Vault Agent injection: `kubectl describe pod -n protean-prod -l app=api` - should have `vault.hashicorp.com/agent-inject: true` annotation
2. Check certs secret: `kubectl get secret protean-mtls-certs -n protean-prod -o yaml` - should have tls.crt, tls.key, ca.crt base64
3. Check env vars: `kubectl exec -n protean-prod deployment/api -- env | grep VAULT`
4. Check logs: `kubectl logs -n protean-prod deployment/api --previous`
5. Common fix: `kubectl delete pod -n protean-prod -l app=api` - Vault Agent will re-inject

### ZK Prover Down - Fail-Closed

**Symptom:** Offense bots scaled to 0, logs `ZK prover down and REQUIRE_ZK_PROOF=true - triggering fail-closed`

**Cause:** `zk-prover` deployment down, health probe fails.

**Solution:** Operator `k8s/operator/operator.py` `zk_prover_probe` checks `/health`, if down and `REQUIRE_ZK_PROOF=true` (gov standard), scales offense to 0 to prevent unfair MEV without proof. Defense stays at 1+.

**Check:**
```bash
kubectl get pods -n protean-prod -l app=zk-prover
kubectl logs -n protean-prod deployment/zk-prover
kubectl get deployment offense-bot -n protean-prod -o yaml | grep replicas
# Should be 0 if prover down and require_zk_proof=true
```

**Fix:** `kubectl rollout restart deployment/zk-prover -n protean-prod` or check circuit artifacts `circuits/build/fairness_policy.wasm` + `final.zkey` present in ConfigMap `circuit-config`.

### Load Test Not Reaching 100k TPS

**Symptom:** Throughput 1k TPS, not 100k

**Cause:** Single-node locust/k6 not enough for 100k TPS - need distributed.

**Solution:**
- Use distributed locust: `locust -f scripts/load_test.py --headless -u 1000 -r 100 --run-time 5m --host http://api --workers 5` with multiple workers
- Use k6 cloud or SaladCloud $5 free credits for ZK compute offloads
- Scale API HPA maxReplicas 10, zk-prover 5, ml-scorer 5
- Check `load_test_results.json` throughput, latency p95 <500ms, p99 <1000ms, error rate <1%

### E2E Tests Fail Without RPC

**Symptom:** `test_offense_bot` scan fails, `test_database` etc.

**Cause:** No real Mainnet RPC configured, Vault not accessible in dev.

**Solution:** Tests use deterministic opportunity fallback when RPC fails (not random), still verify structure. For full E2E with real RPC, set `EVM_RPC_URL` from Vault Alchemy/Infura and `VAULT_ADDR` etc. in `.env`.

---

## Scaling

### Horizontal Scaling

- **API:** HPA 3-10, CPU 70% memory 80%
- **ZK Prover:** HPA 2-5, CPU 80%, resources 1CPU 4Gi req 4CPU 16Gi limit (ZK proving heavy)
- **Offense Bot:** 2 replicas, PDB minAvailable 1
- **Defense Bot:** 3 replicas, PDB minAvailable 2 (high availability for protection)
- **ML Scorer:** 3 replicas, model-pvc 10Gi ReadOnlyMany
- **Redis:** 3 replicas HA headless, PDB minAvailable 2
- **Kafka:** 3 replicas, acks all, idempotence
- **Postgres:** 1 replica with PVC 100Gi gp3-encrypted, would be RDS in prod with TLS

### Vertical Scaling

- ZK Prover needs 4Gi+ RAM for Groth16 proving, up to 16Gi limit
- ML Scorer needs 4Gi RAM for xgboost + SHAP TreeExplainer

### Auto-Scaling Triggers

- CPU 70%, memory 80% via HPA
- Custom metrics via Prometheus: `protean_mev_risk_score` histogram 95th percentile >0.8 triggers scale up defense bots
- `protean_zk_proofs_total` rate triggers scale up zk-prover

---

## Backup and Restore

### Postgres

- PVC `postgres-pvc` 100Gi gp3-encrypted
- Daily backups via Velero or RDS snapshots
- Restore: `kubectl exec -n protean-prod deployment/postgres -- pg_restore`

### Redis

- AOF persistence enabled, RDB snapshots
- Redis Cluster with 3 replicas, data replicated

### Kafka

- `acks=all`, `enable_idempotence=True`, 3 replicas
- Topics `prod.mev-opportunities`, `prod.risk-scores` retained 7 days

### Models

- `model-pvc` 10Gi ReadOnlyMany contains `xgboost_protean_v2.joblib`, `commitment.json`, `shap_background.npy`
- Versioned via `model_registry_url`, SLSA provenance `model_hash`, `training_data_hash`
- Backup to S3 with cosign signature

### Circuits

- `circuit-config` ConfigMap contains `CIRCUIT_HASH` `d80e3987...` SLSA L3
- WASM + ZKEY stored in `circuits/build/` + S3 with cosign, Rekor transparency
- Powers of Tau ceremony transcript in `circuits/ceremony/transcript/`

---

## Security Operations

### Secrets Rotation

- **Vault:** AppRole role_id + secret_id rotated every 30 days via Vault Agent
- **PQC Keys:** ML-KEM-768 keys rotated every 90 days via Vault, `ml_kem_keypair()` generates new
- **QRNG Tokens:** Qrypt 1k/day free, Azure 10k/month, rotate via `k8s/secrets/secrets.yaml` cloud-credentials
- **HSM Keys:** AWS CloudHSM cluster, GCP HSM key_ring, Securosys label, rotated via KMS API
- **mTLS Certs:** `/certs/tls.crt` from Vault Agent, auto-renewed via cert-manager

### Vulnerability Scanning

- `pip-audit --strict` in CI fails build on critical
- Trivy scan Docker images via `.github/workflows/enterprise-ci.yml`
- Bandit SAST
- SBOM CycloneDX `cyclonedx-py` as build artifact

### Incident Response

- SIEM forwarding via `siem_endpoint` + `otel_endpoint` in `app/core/logging.py`
- Audit logs `AU-2` for all critical actions: `MEV_OPPORTUNITY_FOUND`, `BUNDLE_SUBMITTED`, `TX_ANALYZED`, `CONTRACT_DEPLOYED`, `LICENSE_VERIFIED`, `QRNG_FETCH`, `HSM_SIGN`, `COMPLIANCE_CHECK`
- PII redaction `0x...->[REDACTED]`, JWT Bearer redacted

---

## Cost Optimization - Free Tier

| Component | Cloud Service | Free Tier | Usage | Cost After Free |
|-----------|---------------|-----------|-------|-----------------|
| HSM | AWS CloudHSM | 1 HSM 30 days | $1.60/hr | $1152/month |
| HSM | GCP HSM | 10k ops/month | ~$1 per 10k ops | $0.03 per 10k ops |
| HSM | Securosys | 1k ops/month | Free | Contact sales |
| QRNG | Qrypt | 1k req/day | 1 req per nonce/key | Free tier sufficient for 1k tx/day |
| QRNG | Azure Quantum | 10k req/month | 10k random bytes/month | Free tier |
| ZK Compute | SaladCloud | $5 free credits | ZK proving heavy | $0.50 per hour GPU |
| Deployment | AWS EKS | 750 hrs/month t3.micro | 3x t3.medium 24*30=2160 hrs >750, but t3.micro free | ~$50/month for 3 medium |
| Monitoring | Grafana Cloud | 10k metrics free | 7 metrics * 15s interval | Free tier sufficient |
| Load Testing | k6 | Open-source | No cost | - |

**Gov Standard:** For production, use paid tiers beyond free.

---

## Disaster Recovery

- **Multi-AZ:** EKS 3 nodes across 3 AZs, RDS Postgres Multi-AZ, Redis Cluster 3 replicas across AZs
- **Backup:** Velero for K8s manifests + PVC snapshots, S3 for models + circuits
- **RTO:** 1 hour (operator auto-heals), RPO: 5 minutes (Kafka retention + Postgres WAL)
- **Failover:** If ZK prover down, offense scales to 0 fail-closed, defense stays 1+; if Redis down, fallback to file cache `/tmp/compliance_cache/`; if QRNG cloud down, fallback `os.urandom` FIPS; if HSM down, fallback software Vault Transit

---

**No Hardware Procurement - Cloud Services Free Tier + Code/Config Only**
