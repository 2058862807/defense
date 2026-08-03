"""Fail-closed JWT auth tests for A4 (IdP/JWKS-in-process, RBAC).

Proves: HS256/'none' never accepted, symmetric fallback killed, JWKS RS256
verification works end-to-end against a live local JWKS, RBAC enforces roles,
and production fail-closes on missing/invalid Bearer tokens.
"""

import base64
import json
import threading
import time
import unittest.mock as mock
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from app.core import security
from app.core.config import settings
from app.core.auth_deps import (
    ALLOWED_ROLES,
    _claim_roles,
    _verify_token,
    require_role,
)


def _issue_hs256(token_secret: str, aud: str, sub: str = "alice"):
    return pyjwt.encode(
        {"sub": sub, "exp": time.time() + 3600, "iat": time.time(), "aud": aud},
        token_secret,
        algorithm="HS256",
    )


def test_hs256_rejected_in_production():
    if not settings.is_production():
        pytest.skip("test requires production settings (ENV=production)")
    token = _issue_hs256("shared-secret", settings.jwt_aud)
    with pytest.raises(PermissionError):
        security.verify_jwt(token, "shared-secret", settings.jwt_aud, ["HS256"])


def test_hs256_rejected_by_gov_verifier():
    token = _issue_hs256("shared-secret", settings.jwt_aud)
    with pytest.raises(ValueError):
        security.verify_jwt_gov(token, "https://x/jwks.json", settings.jwt_aud, settings.jwt_issuer, ["HS256"])


def test_none_algorithm_always_rejected():
    with pytest.raises(ValueError):
        security.verify_jwt_gov("x.y.z", "https://x/jwks.json", settings.jwt_aud, settings.jwt_issuer, ["none"])
    with pytest.raises(ValueError):
        security.verify_jwt("x.y.z", "secret", settings.jwt_aud, ["none"])


def test_hs256_allowed_only_dev_with_explicit_flag():
    token = _issue_hs256("shared-secret", settings.jwt_aud)
    with mock.patch.object(settings, "env", "dev"), mock.patch.object(settings, "jwt_allow_hs256_dev", True):
        payload = security.verify_jwt(token, "shared-secret", settings.jwt_aud, ["HS256"])
        assert payload["sub"] == "alice"
    with mock.patch.object(settings, "env", "dev"), mock.patch.object(settings, "jwt_allow_hs256_dev", False):
        with pytest.raises(PermissionError):
            security.verify_jwt(token, "shared-secret", settings.jwt_aud, ["HS256"])


# --- JWKS end-to-end ---
class _JwksHandler(BaseHTTPRequestHandler):
    jwks = {}

    def do_GET(self):
        body = json.dumps(self.jwks).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def jwks_server():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key()
    numbers = public.public_numbers()
    def b64u(n):
        return base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()
    kid = "test-kid-1"
    _JwksHandler.jwks = {"keys": [{
        "kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256",
        "n": b64u(numbers.n), "e": b64u(numbers.e),
    }]}
    server = HTTPServer(("127.0.0.1", 0), _JwksHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], key
    server.shutdown()


def _issue_rs256(private_key, aud, iss, kid, sub="alice"):
    now = int(time.time())
    return pyjwt.encode(
        {"sub": sub, "role": "operator", "exp": now + 3600, "iat": now, "aud": aud, "iss": iss},
        private_key, algorithm="RS256", headers={"kid": kid},
    )


def test_jwks_rs256_roundtrip(jwks_server):
    port, key = jwks_server
    jwks_url = f"http://127.0.0.1:{port}/jwks.json"
    token = _issue_rs256(key, settings.jwt_aud, settings.jwt_issuer, "test-kid-1")
    payload = security.verify_jwt_gov(token, jwks_url, settings.jwt_aud, settings.jwt_issuer, ["RS256"])
    assert payload["sub"] == "alice"
    assert payload["role"] == "operator"


def test_jwks_wrong_audience_rejected(jwks_server):
    port, key = jwks_server
    jwks_url = f"http://127.0.0.1:{port}/jwks.json"
    token = _issue_rs256(key, "other-api", settings.jwt_issuer, "test-kid-1")
    with pytest.raises(Exception):
        security.verify_jwt_gov(token, jwks_url, settings.jwt_aud, settings.jwt_issuer, ["RS256"])


# --- RBAC ---
def test_rbac_role_grant_and_deny():
    admin = {"sub": "boss", "role": "gov-admin"}
    auditor = {"sub": "a", "role": "auditor"}
    none = {"sub": "b"}

    assert require_role("gov-admin", "operator")(admin) == admin
    assert require_role("auditor")(auditor) == auditor
    with pytest.raises(HTTPException) as e:
        require_role("gov-admin")(auditor)
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        require_role("gov-admin")(none)
    assert e.value.status_code == 403


def test_claim_roles_normalization():
    assert _claim_roles({"role": "operator"}) == ["operator"]
    assert _claim_roles({"roles": ["admin", "auditor"]}) == ["admin", "auditor"]
    assert _claim_roles({}) == []


def test_production_fail_closed_no_token():
    if not settings.is_production():
        pytest.skip("requires production settings")
    with pytest.raises(HTTPException) as e:
        _verify_token(None)
    assert e.value.status_code == 401
    with pytest.raises(HTTPException) as e:
        _verify_token("NotBearer at all")
    assert e.value.status_code == 401


def test_verify_jwt_gov_rejects_unsigned_alg_mismatch(jwks_server):
    port, key = jwks_server
    jwks_url = f"http://127.0.0.1:{port}/jwks.json"
    # Signed with ES256 key but verifying as RS256 must fail.
    from cryptography.hazmat.primitives.asymmetric import ec
    ec_key = ec.generate_private_key(ec.SECP256R1())
    token = pyjwt.encode(
        {"sub": "alice", "exp": time.time() + 3600, "aud": settings.jwt_aud, "iss": settings.jwt_issuer},
        ec_key, algorithm="ES256",
    )
    with pytest.raises(Exception):
        security.verify_jwt_gov(token, jwks_url, settings.jwt_aud, settings.jwt_issuer, ["RS256"])


# --- In-process IdP (A4: removes the dead auth.protean.sh dependency) ---
from app.core.idp import LocalIdP


@pytest.fixture(autouse=True)
def _idp_store(tmp_path, monkeypatch):
    """Give IdP tests a throwaway encrypted store + master key so they don't
    touch the real data/secrets.enc (tests run in production env)."""
    monkeypatch.setattr(settings, "secrets_store_path", str(tmp_path / "secrets.enc"))
    monkeypatch.setenv("SECRETS_MASTER_KEY", "test-master-key-0123456789")


def test_local_idp_jwks_roundtrip():
    idp = LocalIdP(audience="protean-api", issuer="https://auth.protean.sh")
    jwks = idp.jwks()
    assert jwks["keys"][0]["kty"] == "RSA"
    assert jwks["keys"][0]["alg"] == "RS256"
    assert jwks["keys"][0]["use"] == "sig"
    assert jwks["keys"][0]["kid"]
    token = idp.issue_token("bob", "operator")
    payload = idp.verify(token)
    assert payload["sub"] == "bob"
    assert payload["role"] == "operator"


def test_local_idp_rejects_hs256():
    idp = LocalIdP(audience="protean-api", issuer="https://auth.protean.sh")
    token = _issue_hs256("shared-secret", "protean-api")
    with pytest.raises(Exception):
        idp.verify(token)


def test_local_idp_wrong_audience_rejected():
    idp = LocalIdP(audience="protean-api", issuer="https://auth.protean.sh")
    token = idp.issue_token("bob", "operator")
    with pytest.raises(Exception):
        idp.verify(token, audience="other-api")


def test_local_idp_expired_token_rejected():
    idp = LocalIdP(audience="protean-api", issuer="https://auth.protean.sh")
    now = int(time.time())
    token = pyjwt.encode(
        {
            "sub": "bob", "role": "operator",
            "exp": now - 10, "iat": now - 100,
            "aud": "protean-api", "iss": "https://auth.protean.sh",
        },
        idp._key, algorithm="RS256", headers={"kid": idp._kid},
    )
    with pytest.raises(Exception):
        idp.verify(token)


def test_local_idp_client_flow():
    idp = LocalIdP(audience="protean-api", issuer="https://auth.protean.sh")
    idp.register_client("k_test", "alice", "gov-admin")
    assert idp.token_for_api_key("k_unknown") is None
    token = idp.token_for_api_key("k_test")
    assert token
    payload = idp.verify(token)
    assert payload["sub"] == "alice"
    assert payload["role"] == "gov-admin"


def test_auth_deps_verify_with_local_idp():
    idp = LocalIdP(audience=settings.jwt_aud, issuer=settings.jwt_issuer)
    with mock.patch("app.core.auth_deps.settings.idp_mode", "local"), \
         mock.patch("app.core.idp.get_idp", return_value=idp):
        token = idp.issue_token("alice", "operator")
        payload = _verify_token(f"Bearer {token}")
        assert payload["sub"] == "alice"
        assert payload["role"] == "operator"
