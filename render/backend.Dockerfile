# Render free-tier backend image: FastAPI control plane with real ML, ZK,
# compliance. Runs with ENV=dev (no Vault/HSM) so free tier can boot without
# external secrets - real xgboost model + real WASM/ZKEY Groth16 proofs still
# work because the artifacts and model are committed to the repo.
#
# Requirements lock is compiled for CPython 3.11 (uv pip compile --python-version 3.11),
# so the base image MUST stay python:3.11. Do not bump to 3.12/3.13.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Node + npm so snarkjs (real Groth16 proving) can run, plus build tools in
# case any pinned hash falls back to an sdist instead of a manylinux wheel.
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm curl build-essential libssl-dev \
    && npm install -g snarkjs@0.7.5 \
    && rm -rf /var/lib/apt/lists/*

# Hash-pinned dependencies (--hash= for every package).
COPY requirements.enterprise.txt ./
RUN pip install --upgrade pip && pip install -r requirements.enterprise.txt

# Application, model, and ZK artifacts (all committed to git).
COPY app ./app
COPY models ./models
COPY circuits ./circuits
COPY contracts ./contracts
COPY scripts ./scripts

# Writable runtime state (durable ledger, audit trail, compliance cache).
RUN mkdir -p data

EXPOSE 8080

# Render injects PORT; single worker keeps free-tier 512MB RAM usable.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
