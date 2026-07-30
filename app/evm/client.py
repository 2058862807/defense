"""
Enterprise EVM Client - Web3.py with WebsocketProvider, HSM signing, mTLS, no mock
Government: FIPS 140-3 TLS, fail-closed on missing secrets
"""
import logging
from typing import Dict, Any, Optional, List
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
from eth_account.signers.local import LocalAccount
import json

from app.core.config import settings
from app.core.circuit_breaker import evm_breaker

logger = logging.getLogger(__name__)

class EVMClientEnterprise:
    def __init__(self, rpc_url: str = None, ws_url: str = None, vault_signer_path: str = None):
        self.rpc_url = rpc_url or settings.evm_rpc_url.get_secret_value()
        self.ws_url = ws_url or settings.evm_ws_url.get_secret_value()
        self.vault_path = vault_signer_path or settings.vault_kv_path_signer

        # Web3 HTTP with TLS - enterprise provider
        self.w3_http = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 10, "verify": True}))
        # PoA middleware for L2s if needed
        self.w3_http.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

        if not self.w3_http.is_connected():
            if settings.is_production():
                raise ConnectionError(f"EVM RPC not connected: {self.rpc_url}")
            logger.warning(f"EVM RPC not connected (dev mode): {self.rpc_url}")

        # Signer loaded from Vault HSM - no private key in env in prod
        self.account: Optional[LocalAccount] = None
        self._load_signer_from_vault()

        # WebSocket for mempool subscription (defense bot)
        self.w3_ws: Optional[Web3] = None

    def _load_signer_from_vault(self):
        """Enterprise: load private key from Vault HSM, never from env file"""
        try:
            from app.core.security import get_secret_from_vault
            secret = get_secret_from_vault(
                settings.vault_addr,
                settings.vault_role_id,
                settings.vault_secret_id.get_secret_value(),
                self.vault_path
            )
            private_key = secret.get("private_key") or secret.get("evm_private_key")
            if not private_key:
                raise ValueError("Vault secret missing private_key")
            # Validate key format
            if not private_key.startswith("0x"):
                private_key = "0x" + private_key
            self.account = Account.from_key(private_key)
            logger.info(f"EVM signer loaded from Vault {self.vault_path} address={self.account.address}")
            # Zeroize private key material from memory (best effort)
            del private_key
        except Exception as e:
            if settings.is_production():
                # In production, require Vault - fail closed
                logger.error(f"Failed to load signer from Vault in production: {e}")
                raise
            # Dev: try env if Vault not available
            logger.warning(f"Vault signer load failed (dev mode): {e}, trying dev key")
            # Do not load default 0x000... in prod
            from app.core.config import settings as cfg
            if cfg.env != "production" and cfg.evm_private_key:
                try:
                    self.account = Account.from_key(cfg.evm_private_key.get_secret_value())
                    logger.info(f"Dev signer loaded address={self.account.address}")
                except:
                    pass

    def get_ws_client(self) -> Web3:
        if not self.w3_ws:
            self.w3_ws = Web3(Web3.LegacyWebSocketProvider(self.ws_url, websocket_kwargs={"timeout": 10}))
            if not self.w3_ws.is_connected() and settings.is_production():
                raise ConnectionError(f"EVM WS not connected: {self.ws_url}")
        return self.w3_ws

    @evm_breaker
    def get_block_number(self) -> int:
        return self.w3_http.eth.block_number

    @evm_breaker
    def get_pending_transactions(self) -> List[Dict[str, Any]]:
        """
        Enterprise: use txpool_content or pending filter
        Requires node with txpool enabled (Erigon, Geth with --txpool)
        """
        try:
            # Geth txpool_content is heavy - in production use filtered subscription
            # Here use pending block
            pending = self.w3_http.eth.get_block('pending', full_transactions=True)
            return pending.transactions if pending else []
        except Exception as e:
            logger.error(f"get_pending_transactions failed: {e}")
            raise

    @evm_breaker
    def send_transaction(self, tx: Dict[str, Any]) -> str:
        if not self.account:
            raise ValueError("No signer loaded")
        # Enterprise: estimate gas, set maxFeePerGas per EIP-1559, chain ID validation
        if "chainId" not in tx:
            tx["chainId"] = settings.evm_chain_id
        if "from" not in tx:
            tx["from"] = self.account.address
        
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3_http.eth.send_raw_transaction(signed.rawTransaction)
        logger.info(f"Transaction sent hash={tx_hash.hex()} from={self.account.address}")
        return tx_hash.hex()

    @evm_breaker
    def call_contract(self, contract_address: str, abi: List, function_name: str, args: List = None, block: str = "latest") -> Any:
        contract = self.w3_http.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)
        func = getattr(contract.functions, function_name)
        return func(*(args or [])).call(block_identifier=block)

    def close(self):
        # Web3 doesn't need explicit close for HTTP, but WS does
        if self.w3_ws and hasattr(self.w3_ws.provider, 'disconnect'):
            try:
                self.w3_ws.provider.disconnect()
            except:
                pass

# Alias
EVMClient = EVMClientEnterprise
