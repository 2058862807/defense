"""
Event publisher facade (C2 - Kafka / event-streaming).

Publishes scored-decision events to the institution's streaming infrastructure.
Kafka publishing uses the existing KafkaBusEnterprise (aiokafka, TLS/SASL_SSL);
when no broker is configured the publisher degrades to the durable webhook
path + local ledger, never silently dropping a decision in production.
"""
import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.integrations import webhooks
from app.streaming.kafka import KafkaBusEnterprise, HAS_KAFKA

logger = logging.getLogger(__name__)


class EventPublisher:
    def __init__(self):
        self._kafka: Optional[KafkaBusEnterprise] = None
        self._kafka_connected = False

    async def _ensure_kafka(self) -> Optional[KafkaBusEnterprise]:
        if settings.kafka_brokers and not self._kafka_connected:
            self._kafka = KafkaBusEnterprise()
            try:
                await self._kafka.connect()
                self._kafka_connected = self._kafka.connected
            except Exception as e:
                logger.error(f"Kafka connect failed: {e}")
                self._kafka = None
        return self._kafka

    async def publish_decision(self, event: Dict[str, Any], customer_id: Optional[str] = None) -> Dict[str, Any]:
        """Publish a scored-decision event. Returns delivery summary."""
        event_type = event.get("event_type", "tx.analyzed")
        result = {"event_type": event_type, "kafka": False, "webhooks": []}

        # 1) Kafka (risk-scores topic by default).
        kafka = await self._ensure_kafka()
        if kafka and settings.kafka_topic_risk:
            try:
                await kafka.publish(settings.kafka_topic_risk, event)
                result["kafka"] = True
            except Exception as e:
                logger.error(f"Kafka publish failed for {event_type}: {e}")

        # 2) Signed webhook delivery to customer-registered endpoints.
        result["webhooks"] = webhooks.deliver_event(event_type, event, customer_id=customer_id)

        # 3) Deterministic fingerprint for audit cross-checking.
        result["payload_hash"] = hashlib.sha256(
            json.dumps(event, sort_keys=True, default=str).encode()
        ).hexdigest()
        return result

    async def close(self) -> None:
        if self._kafka:
            await self._kafka.close()


publisher = EventPublisher()
