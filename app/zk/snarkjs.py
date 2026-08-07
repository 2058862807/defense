"""Resolve the real snarkjs binary used by ingest/prove/verify. No mock."""
import shutil
from pathlib import Path


def resolve_snarkjs() -> str:
    found = shutil.which("snarkjs")
    if found:
        return found
    candidates = [
        Path("node_modules/.bin/snarkjs"),
        Path(__file__).resolve().parents[3] / "node_modules/.bin/snarkjs",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    raise RuntimeError(
        "snarkjs not found - required for real Groth16 proof generation. Install via 'npm install'."
    )
