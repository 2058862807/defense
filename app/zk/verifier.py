"""
Enterprise ZK Verifier - Real cryptographic verification
- Off-chain: local snarkjs groth16 verify against the real verification_key.json (primary)
- On-chain: real eth_call to the Groth16Verifier.verifyProof when contracts are deployed
- Fail-closed: never returns True without an actual verification passing
"""

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

from app.core.config import settings
from app.zk.snarkjs import resolve_snarkjs

logger = logging.getLogger(__name__)

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

GROTH16_VERIFIER_ABI = [
    {
        "inputs": [
            {"name": "a", "type": "uint256[2]"},
            {"name": "b", "type": "uint256[2][2]"},
            {"name": "c", "type": "uint256[2]"},
            {"name": "input", "type": "uint256[3]"},
        ],
        "name": "verifyProof",
        "outputs": [{"name": "r", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    }
]


class ZKVerifierEnterprise:
    def __init__(self, verifier_url: str = None):
        self.verifier_url = verifier_url or settings.zk_verifier_url

    def verify_offchain(self, proof: Dict, public_inputs: List, commitments: Dict = None) -> bool:
        """Real local snarkjs verification against the real verification key. Fail-closed."""
        if not proof:
            logger.error("No proof provided - fail closed")
            return False
        if not all(k in proof for k in ("pi_a", "pi_b", "pi_c")):
            logger.error("Proof missing required Groth16 fields - fail closed")
            return False
        try:
            return self._verify_local_snarkjs(proof, public_inputs)
        except Exception as e:
            logger.error(f"Local snarkjs verification failed: {e}")
            return False

    def _verify_local_snarkjs(self, proof: Dict, public_inputs: List) -> bool:
        vkey_candidates = [
            Path("circuits/final_artifacts/verification_key.json"),
            Path("circuits/build/verification_key.json"),
            Path(settings.zk_verification_key_path),
        ]
        vkey_path = next((p for p in vkey_candidates if p.exists()), None)
        if not vkey_path:
            logger.error("Verification key not found - fail closed")
            return False

        snarkjs_bin = resolve_snarkjs()

        with tempfile.TemporaryDirectory() as tmpdir:
            proof_path = Path(tmpdir) / "proof.json"
            public_path = Path(tmpdir) / "public.json"
            with open(proof_path, 'w') as f:
                json.dump(proof, f)
            with open(public_path, 'w') as f:
                json.dump(public_inputs, f)

            result = subprocess.run(
                [snarkjs_bin, "groth16", "verify", str(vkey_path), str(public_path), str(proof_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and "OK" in result.stdout:
                logger.info(f"Local snarkjs verification OK")
                return True
            logger.warning(f"Local snarkjs verification failed: {result.stdout} {result.stderr}")
            return False

    def verify_onchain(self, proof: Dict, public_inputs: List, input_commitment: str = None) -> bool:
        """
        Real on-chain verification: eth_call Groth16Verifier.verifyProof.
        Returns False (fail-closed) until the verifier contract is actually deployed
        and its address is configured.
        """
        if settings.fairness_verifier_address == ZERO_ADDRESS:
            logger.warning("FairnessVerifier address is zero - not deployed, on-chain verification unavailable")
            return False

        try:
            from web3 import Web3
            from app.evm.client import EVMClientEnterprise

            client = EVMClientEnterprise()
            if not client.w3_http.is_connected():
                logger.warning("EVM client not connected - cannot verify on-chain")
                return False

            w3 = client.w3_http
            verifier = w3.eth.contract(
                address=Web3.to_checksum_address(settings.fairness_verifier_address),
                abi=GROTH16_VERIFIER_ABI,
            )

            a = [int(proof["pi_a"][0]), int(proof["pi_a"][1])]
            b = [
                [int(proof["pi_b"][0][0]), int(proof["pi_b"][0][1])],
                [int(proof["pi_b"][1][0]), int(proof["pi_b"][1][1])],
            ]
            c = [int(proof["pi_c"][0]), int(proof["pi_c"][1])]
            inp = [int(p) for p in public_inputs]

            valid = verifier.functions.verifyProof(a, b, c, inp).call()
            logger.info(f"On-chain Groth16Verifier.verifyProof -> {valid}")
            return bool(valid)
        except Exception as e:
            logger.error(f"On-chain verification failed: {e}")
            return False

    def verify(self, proof: Dict, public_inputs: List, commitments: Dict = None) -> bool:
        """Defense in depth: off-chain cryptographic verification must pass."""
        offchain_valid = self.verify_offchain(proof, public_inputs, commitments)
        if not offchain_valid:
            logger.error("Off-chain verification failed - rejecting proof")
            return False

        # On-chain check is best-effort (requires deployed verifier contract).
        if commitments and commitments.get("input_commitment"):
            onchain_valid = self.verify_onchain(proof, public_inputs, commitments.get("input_commitment"))
            if not onchain_valid:
                logger.warning(
                    "On-chain verification unavailable/failed but off-chain passed - "
                    "proof valid cryptographically, anchoring pending contract deployment"
                )

        return True


# Alias
ZKVerifier = ZKVerifierEnterprise
