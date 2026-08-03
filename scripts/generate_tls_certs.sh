#!/usr/bin/env bash
#
# Generate a local private PKI for PROTEAN DEFENSE (A2 TLS/mTLS):
#   certs/ca.crt        - root CA (cert only, private key is ca.key, kept secret)
#   certs/server.crt    - leaf cert for backend + gateway (SAN localhost/127.0.0.1)
#   certs/server.key    - server private key
#   certs/client.crt    - gateway client cert (clientAuth EKU) for backend mTLS
#   certs/client.key    - client private key
#
# Idempotent: refuses to overwrite an existing cert material unless --force.
#
# Usage:
#   scripts/generate_tls_certs.sh [--force]
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/certs"
mkdir -p "$DIR"

if [ "${1:-}" = "--force" ] || [ ! -f "$DIR/ca.crt" ]; then
  : # regenerate below
else
  echo "[tls] certs already present in $DIR (use --force to regenerate)"
  exit 0
fi

cd "$DIR"

# --- Root CA ---
openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
  -keyout ca.key -out ca.crt \
  -subj "/C=US/O=Protean Defense/CN=Protean Root CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  >/dev/null 2>&1

# --- Server leaf (backend + gateway) ---
openssl req -newkey rsa:2048 -sha256 -nodes \
  -keyout server.key -out server.csr \
  -subj "/C=US/O=Protean Defense/CN=protean.local" >/dev/null 2>&1

openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days 397 -sha256 -out server.crt \
  -extfile <(printf "subjectAltName=DNS:localhost,DNS:protean.local,IP:127.0.0.1,IP:0.0.0.0\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n") \
  >/dev/null 2>&1

# --- Client leaf (gateway -> backend mTLS) ---
openssl req -newkey rsa:2048 -sha256 -nodes \
  -keyout client.key -out client.csr \
  -subj "/C=US/O=Protean Defense/CN=protean-gateway" >/dev/null 2>&1

openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days 397 -sha256 -out client.crt \
  -extfile <(printf "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth\n") \
  >/dev/null 2>&1

chmod 600 ca.key server.key client.key
rm -f server.csr client.csr ca.srl

echo "[tls] generated PKI in $DIR"
ls -1 "$DIR"
