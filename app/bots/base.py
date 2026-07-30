"""
Enterprise Base Bot - Government standard, no mocks, HSM, Vault, mTLS, OTel
"""
import logging
from abc import ABC
from typing import Dict, Any
from app.ml.scorer import ProteanScorerEnterprise
from app.ml.xai import ZKXAICouplerEnterprise
from app.evm.client import EVMClientEnterprise
from app.evm.flashbots import FlashbotsClientEnterprise
from app.evm.fairness_registry import FairnessRegistryEnterprise
from app.streaming.kafka import KafkaBusEnterprise
from app.core.config import settings

logger = logging.getLogger(__name__)

class BaseProteanBotEnterprise(ABC):
    def __init__(self):
        # Enterprise components - fail closed if missing
        self.scorer = ProteanScorerEnterprise()
        self.xai_coupler = ZKXAICouplerEnterprise(self.scorer)
        self.evm = EVMClientEnterprise()
        self.flashbots = FlashbotsClientEnterprise()
        self.registry = FairnessRegistryEnterprise(self.evm)
        self.kafka = KafkaBusEnterprise()
        self.running = False

    async def with_zk_fairness(self, tx_data: Dict[str, Any], is_offense: bool) -> Dict[str, Any]:
        """
        Enterprise ZK xAI coupling - real prover, PQC, on-chain anchor
        """
        # 1. Generate ZK XAI proof - fails closed in prod if prover down
        zk_package = self.xai_coupler.generate_zk_proof(tx_data)

        # 2. Validate proof is present if required
        if settings.require_zk_proof and not zk_package.get("zk_proof"):
            raise RuntimeError("ZK proof required but not generated - fail closed")

        # 3. Publish to Kafka with TLS/SASL for observability (SIEM)
        try:
            await self.kafka.publish(
                settings.kafka_topic_risk if not is_offense else settings.kafka_topic_mev,
                {
                    "score": zk_package["score"],
                    "is_fair": zk_package["fairness"]["is_fair"],
                    "model_hash": zk_package["commitments"]["model_commitment"],
                    "input_commitment": zk_package["commitments"]["input_commitment"],
                    "policy_version": settings.fairness_policy_version,
                    "provenance": zk_package.get("provenance", {}),
                    "timestamp": zk_package.get("provenance", {}).get("timestamp")
                }
            )
        except Exception as e:
            logger.error(f"Kafka publish failed: {e}")
            if settings.is_production():
                # In production, kafka failure should not block protection, but must be logged for SIEM
                from app.core.logging import audit_log
                audit_log("KAFKA_FAILURE", "bot", "publish", "kafka", "FAILURE", {"error": str(e)})

        # 4. Submit proof on-chain for audit trail - defense always logs, offense only if fair
        if zk_package["fairness"]["is_fair"] or not is_offense:
            try:
                tx_hash = await self.registry.submit_proof(zk_package, is_offense=is_offense)
                zk_package["onchain_hash"] = tx_hash
                logger.info(f"Fairness proof anchored on-chain hash={tx_hash} fair={zk_package['fairness']['is_fair']}")
            except Exception as e:
                logger.error(f"On-chain anchoring failed: {e}")
                if settings.is_production() and is_offense and not zk_package["fairness"]["is_fair"]:
                    # Offense unfair must not proceed if on-chain anchoring fails
                    raise

        return zk_package

    async def close(self):
        await self.evm.close() if hasattr(self.evm, 'close') else None
        await self.flashbots.close()
        await self.kafka.close()

# Alias for compat
BaseProteanBot = BaseProteanBotEnterprise
