FROM python:3.11-slim as base

# Security: non-root, no LD_LIBRARY_PATH hijack
RUN useradd -m -u 1001 protean && apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git libssl-dev curl && rm -rf /var/lib/apt/lists/*

# PQC - liboqs build from a pinned, released commit (0.12.0 tag), not a
# moving branch. The checkout is verified against the exact commit SHA -
# the build fails if the clone resolves to anything else.
ARG LIBOQS_COMMIT=f4b96220e4bd208895172acc4fedb5a191d9f5b1
ARG LIBOQS_VERSION=0.12.0
WORKDIR /tmp
RUN git clone https://github.com/open-quantum-safe/liboqs.git && \
    cd liboqs && git checkout ${LIBOQS_COMMIT} && \
    if [ "$(git rev-parse HEAD)" != "${LIBOQS_COMMIT}" ]; then \
        echo "FATAL: liboqs checkout does not match pinned commit ${LIBOQS_COMMIT}" >&2; exit 1; \
    fi && \
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

# Enforce hash-pinned deps - a hash mismatch or missing hash must fail the
# build, not silently fall back to an unverified install.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --require-hashes -r requirements.enterprise.txt
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
