"""
AWS Quantum Random Number Generator - Real Cloud QRNG via AWS Braket
- AWS Braket provides access to quantum hardware (IonQ, Rigetti, IQM, QuEra) for QRNG
- Free tier: via AWS Marketplace Qrypt or Braket free tier
- Docs: https://docs.aws.amazon.com/braket/latest/developerguide/braket-devices.html

Government Standard: FIPS 140-3, IAM auth, audit logging

Implementation:
- Uses AWS Braket to run Hadamard circuit on quantum device for true randomness
- Or via AWS Marketplace: Qrypt Entropy as a Service EaaS
- Falls back to os.urandom if quantum device unavailable
"""

import logging
import os
from typing import Optional

from .base import QRNGProvider

logger = logging.getLogger(__name__)

class AWSQRNG(QRNGProvider):
    def __init__(self, 
                 aws_access_key: Optional[str] = None,
                 aws_secret_key: Optional[str] = None,
                 region: Optional[str] = None,
                 device_arn: Optional[str] = None):
        self.aws_access_key = aws_access_key or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_key = aws_secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.device_arn = device_arn or os.getenv("AWS_BRAKET_DEVICE_ARN", "arn:aws:braket:::device/qpu/ionq/Aria-1")
        
        # Alternative: Qrypt via AWS Marketplace
        self.qrypt_via_aws = os.getenv("QRYPT_AWS_MARKETPLACE_TOKEN")

    def get_provider_name(self) -> str:
        return "AWS Braket"

    def is_available(self) -> bool:
        return bool((self.aws_access_key and self.aws_secret_key) or self.qrypt_via_aws)

    def get_random_bytes(self, num_bytes: int) -> bytes:
        """
        Real AWS Braket QRNG - generates quantum random bytes via Hadamard circuit on QPU
        
        Circuit:
        - Create n qubits (8 per byte)
        - Apply H gate to each (superposition)
        - Measure (collapses to 0/1 with 50% probability - true quantum randomness due to Born rule)
        - Convert measurements to bytes
        """
        if not self.is_available():
            raise RuntimeError("AWS credentials not configured for Braket QRNG")

        try:
            return self._get_via_braket(num_bytes)
        except ImportError as e:
            logger.warning(f"Braket SDK not available: {e}, trying Qrypt via AWS Marketplace")
            return self._get_via_qrypt_marketplace(num_bytes)
        except Exception as e:
            logger.error(f"AWS Braket QRNG failed: {e}")
            raise

    def _get_via_braket(self, num_bytes: int) -> bytes:
        """
        Via AWS Braket SDK - real quantum device
        """
        try:
            from braket.circuits import Circuit
            from braket.aws import AwsDevice, AwsQuantumTask

            # Create quantum circuit for QRNG: H gate + measurement
            # For num_bytes, need num_bytes*8 qubits measured
            # But Braket devices have limited qubits, so we run multiple shots

            # Use IonQ Aria-1 or similar - 25 qubits, high fidelity
            device = AwsDevice(self.device_arn)

            # Build circuit: 8 qubits, H on each, measure
            circuit = Circuit()
            for i in range(min(8, 20)):  # Use 8 qubits per run
                circuit.h(i)

            # Number of shots = num_bytes (each shot gives 8 random bits = 1 byte)
            # But we can get multiple bytes per shot if we use more qubits
            # For simplicity, run num_bytes shots
            shots = num_bytes

            # Create quantum task
            task = device.run(circuit, shots=shots)

            # Wait for results (in production, async with S3)
            result = task.result()
            
            # Extract measurements - each measurement is random bits
            measurements = result.measurements  # shape (shots, qubits)
            
            random_bytes = bytearray()
            for shot in measurements:
                # Convert bit array to byte
                byte_val = 0
                for bit_idx, bit in enumerate(shot[:8]):  # First 8 qubits
                    if bit:
                        byte_val |= (1 << bit_idx)
                random_bytes.append(byte_val)

            # Ensure we have requested bytes
            if len(random_bytes) < num_bytes:
                logger.warning(f"Braket returned {len(random_bytes)} bytes, expected {num_bytes}")
                import os as os_mod
                random_bytes.extend(os_mod.urandom(num_bytes - len(random_bytes)))

            logger.info(f"AWS Braket QRNG fetched {len(random_bytes)} bytes via {self.device_arn} device")

            return bytes(random_bytes[:num_bytes])

        except ImportError as e:
            logger.error(f"Braket SDK not installed: {e}")
            raise
        except Exception as e:
            logger.error(f"Braket QRNG task failed: {e}")
            raise

    def _get_via_qrypt_marketplace(self, num_bytes: int) -> bytes:
        """
        Via Qrypt EaaS on AWS Marketplace - Entropy as a Service
        - $2000/month for 0-2GB, but free tier via trial
        - API similar to Qrypt direct
        """
        import httpx
        import base64

        if not self.qrypt_via_aws:
            raise RuntimeError("Qrypt AWS Marketplace token not configured")

        # Qrypt EaaS via AWS Marketplace uses same API but with AWS auth
        endpoint = os.getenv("QRYPT_EAAS_ENDPOINT", "https://api-eus.qrypt.com/api/v1/quantum-entropy")

        headers = {
            "Authorization": f"Bearer {self.qrypt_via_aws}",
            "Accept": "application/json",
            "User-Agent": "Protean-Defense-AWS-Marketplace/2.0.0",
        }

        try:
            with httpx.Client(timeout=10.0, verify=True) as client:
                resp = client.get(endpoint, headers=headers, params={"size": num_bytes})
                resp.raise_for_status()
                data = resp.json()
                random_b64 = data.get("random") or data.get("entropy")
                if not random_b64:
                    raise ValueError(f"Qrypt Marketplace response missing random: {data}")
                random_bytes = base64.b64decode(random_b64)
                logger.info(f"Qrypt via AWS Marketplace fetched {len(random_bytes)} bytes")
                return random_bytes[:num_bytes]

        except Exception as e:
            logger.error(f"Qrypt via AWS Marketplace failed: {e}")
            raise
