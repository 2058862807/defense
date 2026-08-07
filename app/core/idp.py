"""
In-process IdP (JWKS + RS256 token issuance) - removes the dependency on an
external, dead `auth.protean.sh` JWKS endpoint so auth works self-contained.

- RSA-2048 signing key, generated on first use and persisted at rest encrypted
  with AES-256-GCM via the SecretsStore (SECRETS_MASTER_KEY).
- Publishes a standard JWKS at /auth/.well-known/jwks.json.
- Issues short-lived RS256 JWTs (sub + role claims) for registered API keys.
- Verification never accepts HS256/'none'.

Government standard: asymmetric signatures only; keys at rest encrypted; expiry
enforced; RBAC via the `role` claim.
"""

import base64
import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

import jwt as pyjwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

logger = logging.getLogger(__name__)

_IDP_KEY_PATH = "internal/idp-signing-key"
_IDP_CLIENTS_PATH = "internal/idp-clients"
_ISSUER_PREFIX = "https://auth.protean.sh"


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class LocalIdP:
    def __init__(self, audience: str = "protean-api", issuer: str = _ISSUER_PREFIX, ttl: int = 3600):
        self.audience = audience
        self.issuer = issuer
        self.ttl = ttl
        self._key: Optional[rsa.RSAPrivateKey] = None
        self._kid: Optional[str] = None
        self._load_or_create_key()
        self._clients: Dict[str, Dict[str, str]] = self._load_clients()

    # --- key management (at rest encrypted) ---
    def _store(self):
        from app.core.secrets_store import _load_store
        try:
            return _load_store()
        except RuntimeError:
            return None

    def _load_or_create_key(self) -> None:
        from app.core.config import settings

        store = self._store()
        if store is not None:
            secret = store.get(_IDP_KEY_PATH)
            if secret and secret.get("private_key_pem") and secret.get("kid"):
                from cryptography.hazmat.primitives.serialization import load_pem_private_key
                self._key = load_pem_private_key(secret["private_key_pem"].encode(), password=None)
                self._kid = secret["kid"]
                return
        elif settings.is_production():
            raise RuntimeError(
                "FAIL-CLOSED: IdP signing key requires SECRETS_MASTER_KEY in production "
                "(local encrypted store) - set SECRETS_MASTER_KEY"
            )

        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._kid = "idp-" + hashlib.sha256(
            self._key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        ).hexdigest()[:16]
        if store is not None:
            pem = self._key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
            store.set(_IDP_KEY_PATH, {"private_key_pem": pem, "kid": self._kid, "created_utc": time.time()})
            logger.info("IDP: generated new RSA-2048 signing key (persisted encrypted)")
        else:
            logger.warning("IDP: generated ephemeral RSA-2048 signing key (in-memory only - tokens invalidate on restart)")

    def _load_clients(self) -> Dict[str, Dict[str, str]]:
        store = self._store()
        if store is None:
            return {}
        secret = store.get(_IDP_CLIENTS_PATH)
        return (secret or {}).get("clients", {})

    def register_client(self, api_key: str, sub: str, role: str) -> None:
        store = self._store()
        if store is None:
            self._clients[api_key] = {"sub": sub, "role": role}
            return
        secret = store.get(_IDP_CLIENTS_PATH) or {}
        clients = secret.setdefault("clients", {})
        clients[api_key] = {"sub": sub, "role": role}
        store.set(_IDP_CLIENTS_PATH, secret)
        self._clients = clients

    # --- JWKS ---
    def jwks(self) -> Dict[str, Any]:
        pub = self._key.public_key()
        numbers = pub.public_numbers()

        def _n_bytes(n: int) -> int:
            return max((n.bit_length() + 7) // 8, 1)
        n = _b64u(numbers.n.to_bytes(_n_bytes(numbers.n), "big"))
        e = _b64u(numbers.e.to_bytes(_n_bytes(numbers.e), "big"))
        return {"keys": [{"kty": "RSA", "kid": self._kid, "use": "sig", "alg": "RS256", "n": n, "e": e}]}

    # --- issuance ---
    def issue_token(self, sub: str, role: str) -> str:
        now = int(time.time())
        payload = {
            "sub": sub,
            "role": role,
            "exp": now + self.ttl,
            "iat": now,
            "nbf": now,
            "aud": self.audience,
            "iss": self.issuer,
        }
        return pyjwt.encode(payload, self._key, algorithm="RS256", headers={"kid": self._kid})

    def token_for_api_key(self, api_key: str) -> Optional[str]:
        client = self._clients.get(api_key)
        if not client:
            return None
        return self.issue_token(client["sub"], client["role"])

    # --- verification (strict RS256, in-process key) ---
    def verify(self, token: str, audience: Optional[str] = None, issuer: Optional[str] = None) -> Dict[str, Any]:
        payload = pyjwt.decode(
            token,
            self._key.public_key(),
            algorithms=["RS256"],
            audience=audience or self.audience,
            issuer=issuer or self.issuer,
            options={
                "require": ["exp", "iat", "aud", "iss", "sub"],
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
                "verify_nbf": True,
            },
        )
        if "sub" not in payload:
            raise pyjwt.InvalidTokenError("Missing sub claim")
        return payload


def get_idp() -> LocalIdP:
    """Cached LocalIdP singleton."""
    from app.core.config import settings
    global _idp
    if _idp is None:
        _idp = LocalIdP(audience=settings.jwt_aud, issuer=settings.jwt_issuer, ttl=settings.jwt_ttl)
    return _idp


_idp: Optional[LocalIdP] = None
