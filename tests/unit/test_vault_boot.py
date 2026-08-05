"""
Fail-closed Vault-at-boot check (app.core.security.require_vault_or_fail).

A misconfigured VAULT_ROLE_ID/VAULT_SECRET_ID must crash the process at boot
in production, not just surface later on the first sign/secret-read attempt.
Verified live against a real local Vault dev server during development; this
test covers the same gating logic with a mock so it runs in CI without a
live Vault.
"""
import pytest
from pydantic import SecretStr

import app.core.security as security


class FakeSettings:
    def __init__(self, production: bool):
        self._production = production
        self.vault_addr = "http://127.0.0.1:8200"
        self.vault_role_id = "some-role-id"
        self.vault_secret_id = SecretStr("some-secret-id")

    def is_production(self):
        return self._production


class FakeAuthenticatedClient:
    def is_authenticated(self):
        return True


class FakeUnauthenticatedClient:
    def is_authenticated(self):
        return False


def test_require_vault_or_fail_skips_outside_production(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("get_vault_client should not be called outside production")

    monkeypatch.setattr(security, "get_vault_client", boom)
    security.require_vault_or_fail(FakeSettings(production=False))  # must not raise


def test_require_vault_or_fail_passes_when_vault_authenticates(monkeypatch):
    monkeypatch.setattr(security, "get_vault_client", lambda *a, **k: FakeAuthenticatedClient())
    security.require_vault_or_fail(FakeSettings(production=True))  # must not raise


def test_require_vault_or_fail_raises_on_auth_exception(monkeypatch):
    def raise_invalid_role(*args, **kwargs):
        raise Exception("invalid role or secret ID")

    monkeypatch.setattr(security, "get_vault_client", raise_invalid_role)
    with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
        security.require_vault_or_fail(FakeSettings(production=True))


def test_require_vault_or_fail_raises_when_client_not_authenticated(monkeypatch):
    monkeypatch.setattr(security, "get_vault_client", lambda *a, **k: FakeUnauthenticatedClient())
    with pytest.raises(RuntimeError, match="FAIL-CLOSED"):
        security.require_vault_or_fail(FakeSettings(production=True))
