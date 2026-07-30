"""
AWS CloudHSM - Real Cloud HSM
- Free tier: 1 HSM for 30 days
- FIPS 140-2 Level 3
- Docs: https://docs.aws.amazon.com/cloudhsm/latest/userguide/

Government Standard: IAM auth, audit logging, mTLS

Real implementation uses:
- CloudHSM Client SDK
- PKCS#11 interface
- Or AWS KMS with custom key store backed by CloudHSM

For enterprise without hardware procurement, we use AWS KMS + CloudHSM custom key store
"""

import logging
import os
from typing import Optional

from .base import HSMProvider

logger = logging.getLogger(__name__)

class AWSCloudHSM(HSMProvider):
    def __init__(self, 
                 cluster_id: Optional[str] = None,
                 region: Optional[str] = None,
                 hsm_user: Optional[str] = None,
                 hsm_password: Optional[str] = None):
        self.cluster_id = cluster_id or os.getenv("AWS_CLOUDHSM_CLUSTER_ID")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.hsm_user = hsm_user or os.getenv("AWS_CLOUDHSM_USER", "crypto_user")
        self.hsm_password = hsm_password or os.getenv("AWS_CLOUDHSM_PASSWORD")
        
        # Alternative: Use AWS KMS with CloudHSM backing
        self.kms_key_id = os.getenv("AWS_KMS_KEY_ID")
        self.use_kms = bool(self.kms_key_id)

    def get_provider_name(self) -> str:
        return "AWS CloudHSM"

    def is_available(self) -> bool:
        # Check if either CloudHSM cluster or KMS key configured
        return bool((self.cluster_id and self.hsm_user) or self.kms_key_id)

    def sign(self, key_id: str, data: bytes) -> bytes:
        """
        Real AWS CloudHSM signing via PKCS#11 or KMS
        - If using KMS with CloudHSM custom key store: KMS Sign API
        - If using direct CloudHSM: PKCS#11 C_Sign
        """
        if self.use_kms:
            return self._sign_via_kms(key_id, data)
        else:
            return self._sign_via_pkcs11(key_id, data)

    def _sign_via_kms(self, key_id: str, data: bytes) -> bytes:
        """Via AWS KMS with CloudHSM backing - real cloud HSM"""
        try:
            import boto3
            from botocore.exceptions import ClientError

            kms_client = boto3.client('kms', region_name=self.region)
            
            # KMS Sign - uses HSM backing if custom key store is CloudHSM
            response = kms_client.sign(
                KeyId=key_id or self.kms_key_id,
                Message=data,
                MessageType='RAW',
                SigningAlgorithm='ECDSA_SHA_256'  # For P-256, or RSASSA_PKCS1_V1_5_SHA_256 for RSA
            )
            
            signature = response['Signature']
            logger.info(f"AWS KMS CloudHSM signed {len(data)} bytes via key {key_id} - sig len {len(signature)}")
            return signature

        except ImportError:
            raise RuntimeError("boto3 not installed - required for AWS CloudHSM KMS")
        except Exception as e:
            logger.error(f"AWS KMS CloudHSM signing failed: {e}")
            raise

    def _sign_via_pkcs11(self, key_id: str, data: bytes) -> bytes:
        """Direct CloudHSM via PKCS#11 - real HSM"""
        try:
            # PKCS#11 via python-pkcs11 or similar
            # This requires CloudHSM client installed and configured
            import pkcs11

            # Load PKCS#11 library - CloudHSM client provides /opt/cloudhsm/lib/libcloudhsm_pkcs11.so
            lib_path = os.getenv("PKCS11_LIB", "/opt/cloudhsm/lib/libcloudhsm_pkcs11.so")
            lib = pkcs11.lib(lib_path)
            
            # Open token
            token = lib.get_token(token_label=os.getenv("HSM_TOKEN_LABEL", "cavium"))
            
            with token.open(user_pin=f"{self.hsm_user}:{self.hsm_password}") as session:
                # Find private key by label
                private_key = session.get_key(label=key_id, object_class=pkcs11.ObjectClass.PRIVATE_KEY)
                # Sign
                signature = private_key.sign(data, mechanism=pkcs11.Mechanism.ECDSA)
                logger.info(f"AWS CloudHSM PKCS#11 signed via {key_id}")
                return signature

        except ImportError:
            raise RuntimeError("python-pkcs11 not installed - required for direct CloudHSM")
        except Exception as e:
            logger.error(f"AWS CloudHSM PKCS#11 signing failed: {e}")
            raise

    def get_public_key(self, key_id: str) -> bytes:
        try:
            import boto3
            kms_client = boto3.client('kms', region_name=self.region)
            response = kms_client.get_public_key(KeyId=key_id or self.kms_key_id)
            return response['PublicKey']
        except Exception as e:
            logger.error(f"AWS CloudHSM get_public_key failed: {e}")
            raise
