#!/usr/bin/env python3
"""
Register an API client (API key -> subject + role) in the in-process IdP.

The API key authenticates to POST /auth/token, which returns a short-lived
RS256 JWT carrying the registered role (gov-admin / operator / auditor).
Tokens are verified in-process (local mode) or against the remote JWKS URL
(remote mode) - HS256/'none' are never accepted.

Usage:
  SECRETS_MASTER_KEY='...' ENV=dev PYTHONPATH=/path/to/defense_v2 \
    venv/bin/python scripts/register_api_client.py --api-key 'k_...' --sub 'alice' --role operator

The API key is stored encrypted (AES-256-GCM) in data/secrets.enc alongside the
IdP signing key. Without SECRETS_MASTER_KEY the registration is in-memory only
(dev mode) and invalidates on restart.
"""

import argparse
import secrets as pysecrets
import sys

from app.core.idp import get_idp
from app.core.config import settings

ROLES = ("gov-admin", "operator", "auditor")


def main() -> int:
    parser = argparse.ArgumentParser(description="Register an IdP API client")
    parser.add_argument("--api-key", help="Client API key (generated if omitted)")
    parser.add_argument("--sub", required=True, help="Subject (caller identity)")
    parser.add_argument("--role", required=True, choices=ROLES, help="RBAC role")
    args = parser.parse_args()

    api_key = args.api_key or f"k_{pysecrets.token_urlsafe(32)}"
    get_idp().register_client(api_key, args.sub, args.role)

    print(f"Registered {args.sub} as {args.role} (idp_mode={settings.idp_mode})")
    print(f"API key: {api_key}")
    print("Exchange at: curl -s -X POST http://localhost:8080/auth/token -H 'X-API-Key: <key>'")
    print("Then use: Authorization: Bearer <token>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
