"""
Federated learning crypto - wrapper for security.py
"""
from app.core.security import hybrid_encrypt, hybrid_decrypt, aes_gcm_encrypt, aes_gcm_decrypt, ml_kem_encapsulate
import json

def encrypt_federated_payload(payload: dict, peer_pubkey: bytes = None) -> dict:
    plaintext = json.dumps(payload).encode()
    return hybrid_encrypt(peer_pubkey, plaintext)

def decrypt_federated_payload(enc_dict: dict) -> dict:
    pt = hybrid_decrypt(enc_dict["kem_ct"], enc_dict["nonce"], enc_dict["ciphertext"])
    return json.loads(pt.decode())
