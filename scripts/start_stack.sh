#!/usr/bin/env bash
#
# PROTEAN DEFENSE - autonomous stack supervisor (backend 8080 + frontend 3000)
#
# - Detached via setsid+nohup+</dev/null: immune to shell/terminal timeouts.
# - Supervises both processes forever, restarting either one if it dies.
# - Idempotent: already-running services are left untouched.
#
# Usage:
#   scripts/start_stack.sh --detach   # launch everything detached + supervised (returns immediately)
#   scripts/start_stack.sh            # run supervisor in foreground (ctrl-c to stop)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_LOG=/tmp/backend.log
FRONTEND_LOG=/tmp/frontend.log
SUPERVISOR_PIDFILE=/tmp/stack-supervisor.pid

# --- Secrets master key: prefer env/Vault injection; fall back to the 0600
#     local key file created by `scripts/init_secrets.py --fresh --write-key-file`.
if [ -z "${SECRETS_MASTER_KEY:-}" ] && [ -f "$ROOT/data/.secrets_master_key" ]; then
  SECRETS_MASTER_KEY="$(cat "$ROOT/data/.secrets_master_key")"
  export SECRETS_MASTER_KEY
fi

# --- Local signer keys (0600, git-ignored): EVM_PRIVATE_KEY / FLASHBOTS_SIGNING_KEY
#     are intentionally NOT in .env. Source the env-only file when present.
if [ -f "$ROOT/data/local_secrets.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/data/local_secrets.env"
  set +a
fi

# --- A2 TLS/mTLS ---
REQUIRE_TLS="${REQUIRE_TLS:-false}"
REQUIRE_MTLS_PEER="${REQUIRE_MTLS_PEER:-false}"
TLS_CERT="${TLS_CERT:-$ROOT/certs/server.crt}"
TLS_KEY="${TLS_KEY:-$ROOT/certs/server.key}"
TLS_CA="${TLS_CA:-$ROOT/certs/ca.crt}"
TLS_CLIENT_CERT="${TLS_CLIENT_CERT:-$ROOT/certs/client.crt}"
TLS_CLIENT_KEY="${TLS_CLIENT_KEY:-$ROOT/certs/client.key}"

tls_missing() {
  for f in "$TLS_CERT" "$TLS_KEY" "$TLS_CA"; do
    [ -f "$f" ] || return 0
  done
  if [ "$REQUIRE_MTLS_PEER" = "true" ]; then
    [ -f "$TLS_CLIENT_CERT" ] && [ -f "$TLS_CLIENT_KEY" ] || return 0
  fi
  return 1
}

if [ "$REQUIRE_TLS" = "true" ] && tls_missing; then
  echo "[stack] FAIL-CLOSED (A2): REQUIRE_TLS=true but cert material missing. Run scripts/generate_tls_certs.sh"
  exit 1
fi

is_alive() {
  pgrep -f "$1" >/dev/null 2>&1
}

is_supervisor_running() {
  [ -f "$SUPERVISOR_PIDFILE" ] && kill -0 "$(cat "$SUPERVISOR_PIDFILE")" 2>/dev/null
}

start_backend() {
  echo "[stack] starting backend -> ${BACKEND_LOG}"
  BACKEND_ARGS="--host 0.0.0.0 --port 8080"
  if [ "$REQUIRE_TLS" = "true" ]; then
    BACKEND_ARGS="$BACKEND_ARGS --ssl-certfile $TLS_CERT --ssl-keyfile $TLS_KEY"
    if [ "$REQUIRE_MTLS_PEER" = "true" ]; then
      BACKEND_ARGS="$BACKEND_ARGS --ssl-ca-certs $TLS_CA --ssl-cert-reqs 2"
    fi
  fi
  # shellcheck disable=SC2086
  setsid env ENV=dev PYTHONPATH="$ROOT" "$ROOT/venv/bin/uvicorn" app.main:app $BACKEND_ARGS \
    </dev/null >>"$BACKEND_LOG" 2>&1 &
  disown
}

start_frontend() {
  echo "[stack] starting frontend -> ${FRONTEND_LOG}"
  setsid env PORT=3000 REQUIRE_TLS="$REQUIRE_TLS" REQUIRE_MTLS_PEER="$REQUIRE_MTLS_PEER" \
    TLS_CERT="$TLS_CERT" TLS_KEY="$TLS_KEY" TLS_CA="$TLS_CA" \
    TLS_CLIENT_CERT="$TLS_CLIENT_CERT" TLS_CLIENT_KEY="$TLS_CLIENT_KEY" \
    "$ROOT/node_modules/.bin/tsx" server.ts \
    </dev/null >>"$FRONTEND_LOG" 2>&1 &
  disown
}

if [ "${1:-}" = "--detach" ]; then
  if is_supervisor_running; then
    echo "[stack] supervisor already running (pid $(cat "$SUPERVISOR_PIDFILE"))"
    exit 0
  fi
  setsid nohup bash "$0" </dev/null >/tmp/stack-supervisor.log 2>&1 &
  SUP_PID=$!
  echo "$SUP_PID" > "$SUPERVISOR_PIDFILE"
  echo "[stack] supervisor detached (pid $SUP_PID) - monitoring stack autonomously"
  exit 0
fi

if is_alive "venv/bin/uvicorn app.main:app"; then
  echo "[stack] backend already running - skipping"
else
  start_backend
fi

if is_alive "tsx server.ts"; then
  echo "[stack] frontend already running - skipping"
else
  start_frontend
fi

echo "[stack] supervising... (ctrl-c to stop)"
while true; do
  if ! is_alive "venv/bin/uvicorn app.main:app"; then
    echo "[stack] $(date -u +%FT%TZ) backend DOWN - restarting"
    start_backend
  fi
  if ! is_alive "tsx server.ts"; then
    echo "[stack] $(date -u +%FT%TZ) frontend DOWN - restarting"
    start_frontend
  fi
  sleep 10
done
