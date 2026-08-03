"""
TLS/mTLS transport material helpers (A2).

`require_tls` / `require_mtls_peer` fail closed: when the policy demands TLS
(or client-certificate verification for the internal peer) and the cert
material is missing, the process refuses to start rather than silently serving
plaintext. This is checked by the stack supervisor before launching uvicorn and
mirrors the fail-closed contract used across auth and custody.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def tls_paths(cert: Optional[str] = None, key: Optional[str] = None, ca: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (cert_path, key_path, ca_path) resolved as absolute paths or None."""
    paths = []
    for p in (cert, key, ca):
        if p:
            paths.append(str(Path(p).resolve()))
        else:
            paths.append(None)
    return tuple(paths)  # type: ignore[return-value]


def tls_available(cert: Optional[str] = None, key: Optional[str] = None, ca: Optional[str] = None) -> bool:
    cert_p, key_p, ca_p = tls_paths(cert, key, ca)
    return all(p and Path(p).is_file() for p in (cert_p, key_p, ca_p))


def client_tls_available(client_cert: Optional[str] = None, client_key: Optional[str] = None, ca: Optional[str] = None) -> bool:
    c, k, a = tls_paths(client_cert, client_key, ca)
    return all(p and Path(p).is_file() for p in (c, k, a))


def require_tls_or_fail(settings) -> None:
    """Fail closed: TLS material must exist when require_tls is set."""
    if not settings.require_tls:
        return
    if not tls_available(settings.tls_cert_path, settings.tls_key_path, settings.tls_ca_path):
        raise RuntimeError(
            "FAIL-CLOSED (A2): require_tls=true but cert material missing. "
            f"Run scripts/generate_tls_certs.sh (expected cert={settings.tls_cert_path}, "
            f"key={settings.tls_key_path}, ca={settings.tls_ca_path})."
        )
    if settings.require_mtls_peer and not client_tls_available(
        settings.tls_client_cert_path, settings.tls_client_key_path, settings.tls_ca_path
    ):
        raise RuntimeError(
            "FAIL-CLOSED (A2): require_mtls_peer=true but client cert material missing. "
            "Run scripts/generate_tls_certs.sh."
        )
