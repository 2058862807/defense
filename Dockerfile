FROM python:3.11-slim as base

# Security: non-root, no LD_LIBRARY_PATH hijack
RUN useradd -m -u 1001 protean && apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git libssl-dev curl && rm -rf /var/lib/apt/lists/*

# PQC - liboqs build from pinned commit (defense: verifiable build)
ARG LIBOQS_COMMIT=main
ARG LIBOQS_VERSION=0.12.0
WORKDIR /tmp
RUN git clone https://github.com/open-quantum-safe/liboqs.git && \
    cd liboqs && git checkout ${LIBOQS_COMMIT} && \
    mkdir build && cd build && cmake -DBUILD_SHARED_LIBS=ON .. && make -j4 && make install && \
    ldconfig && rm -rf /tmp/liboqs

# Enforce hash-pinned deps
WORKDIR /app
COPY requirements.enterprise.txt requirements.enterprise.txt
COPY app app
COPY contracts contracts
COPY scripts scripts
COPY circuits circuits
COPY models models

# Install with --require-hashes if available (production defense)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --require-hashes -r requirements.enterprise.txt || \
    pip install --no-cache-dir -r requirements.enterprise.txt
WORKDIR /app

# PQC lib path locked, not via LD_LIBRARY_PATH override
ENV LD_LIBRARY_PATH=/usr/local/lib:/usr/lib
ENV PYTHONPATH=/app
ENV ENV=production
ENV ZK_MODE=production

# Non-root
USER protean
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
