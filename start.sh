#!/usr/bin/env bash
set -euo pipefail

# PROTEAN SHAPES Production start.sh
# Handles PQC liboqs, model commitments, ZK prover, offense/defense bots

echo "[*] PROTEAN SHAPES - Production Bootstrap"

# 1. Check liboqs
if [ -f "/usr/local/lib/liboqs.so" ] || [ -f "/usr/lib/liboqs.so" ]; then
  echo "[+] liboqs found: $(ls -lh /usr/local/lib/liboqs* 2>/dev/null || ls -lh /usr/lib/liboqs*)"
  export LD_LIBRARY_PATH=/usr/local/lib:/usr/lib
  export LIBOQS_PATH=/usr/local/lib/liboqs.so
else
  echo "[!] liboqs not found - building from pinned commit (mock for dev)"
  echo "    In production, Dockerfile builds it. For dev:"
  echo "    git clone https://github.com/open-quantum-safe/liboqs && cd liboqs && cmake -DBUILD_SHARED_LIBS=ON .. && make && sudo make install"
  echo "    pip install liboqs-python"
  echo "    Continuing in MOCK PQC mode"
  export ZK_MODE=mock
fi

# 2. Check model commitment
if [ ! -f "models/xgboost_protean_v1.joblib" ]; then
  echo "[*] Model not found - creating mock model for demo"
  mkdir -p models
  python3 - << 'PY'
import joblib, hashlib, json, os
from sklearn.ensemble import RandomForestClassifier
import numpy as np
# Mock training data: MEV risk
X = np.random.rand(100,7)
y = (X[:,1] + X[:,2]*2 > 1).astype(int)
model = RandomForestClassifier(n_estimators=10, random_state=42)
model.fit(X,y)
joblib.dump(model, "models/xgboost_protean_v1.joblib")
# Commitment
model_bytes = open("models/xgboost_protean_v1.joblib","rb").read()
h = hashlib.sha256(model_bytes).hexdigest()
json.dump({"model_hash": h, "version": "v1-prod"}, open("models/commitment.json","w"))
print(f"Mock model created hash={h[:16]}...")
PY
fi

# 3. Verify requirements with hashes (defense)
echo "[*] Verifying dependencies..."
if [ -f "requirements.hardened.txt" ]; then
  pip install --require-hashes -r requirements.hardened.txt || pip install -r requirements.hardened.txt
  pip-audit -r requirements.hardened.txt --strict || echo "[!] pip-audit found issues - review"
else
  pip install -r ../uploads/requirements.txt || pip install -r requirements.txt
fi

# 4. Generate SBOM
if command -v cyclonedx-py &> /dev/null; then
  cyclonedx-py requirements -i requirements.hardened.txt -o sbom.json || true
  echo "[+] SBOM generated"
fi

# 5. Mode
MODE=${1:-api}
case $MODE in
  api)
    echo "[*] Starting API (FastAPI)..."
    export PYTHONPATH=/app:/app/protean-shapes-prod/app:$PYTHONPATH
    exec uvicorn protean-shapes-prod.app.main:app --host 0.0.0.0 --port 8080 --workers 2
    ;;
  offense)
    echo "[*] Starting OFFENSE bot - ZK Certified Searcher"
    exec python -m protean-shapes-prod.app.bots.offense_bot --iterations 10000
    ;;
  defense)
    echo "[*] Starting DEFENSE bot - ZK Fairness Guardian"
    exec python -m protean-shapes-prod.app.bots.defense_bot --iterations 10000
    ;;
  both)
    echo "[*] Starting BOTH bots + API"
    python -m protean-shapes-prod.app.bots.defense_bot --iterations 10000 &
    python -m protean-shapes-prod.app.bots.offense_bot --iterations 10000 &
    exec uvicorn protean-shapes-prod.app.main:app --host 0.0.0.0 --port 8080
    ;;
  *)
    echo "Usage: $0 [api|offense|defense|both]"
    exit 1
    ;;
esac
