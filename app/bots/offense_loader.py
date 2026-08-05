"""
Offense/sandwich MEV capability is intentionally not part of this pilot-facing
codebase (pilot readiness review, 2026-08-04, finding C3: a bank/gov compliance
team will not accept live front-running/arbitrage code in the vendor's own repo,
no matter how well it's gated). It lives in the separate, access-restricted
protean-offense-tools repo and is loaded here only if a deployment explicitly
opts in via PROTEAN_OFFENSE_TOOLS_PATH.
"""
import os
import sys
import importlib


class OffenseToolsUnavailable(RuntimeError):
    pass


def load_offense_module(module_name: str):
    path = os.environ.get("PROTEAN_OFFENSE_TOOLS_PATH")
    if not path or not os.path.isdir(path):
        raise OffenseToolsUnavailable(
            f"'{module_name}' is unavailable: offense/sandwich capability lives in "
            "the separate protean-offense-tools repo and is not part of this "
            "deployment. Set PROTEAN_OFFENSE_TOOLS_PATH to a valid checkout to enable it."
        )
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module(module_name)
