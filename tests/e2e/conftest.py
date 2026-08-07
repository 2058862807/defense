"""Load local-only env files (0600, git-ignored) so e2e signing tests exercise
the real software custody path. EVM_PRIVATE_KEY/FLASHBOTS_SIGNING_KEY are NOT
in .env by design (secret hygiene)."""

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_env_file(rel: str) -> None:
    p = _ROOT / rel
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_env_file("data/local_secrets.env")
_load_env_file("data/.secrets_master_key")
