"""
Internal bank / credit-union transaction stream - Kafka pull consumer.

Consumes internal-transaction messages from the configured ``bank_tx_topic``,
normalizes each payload (single tx or batch) with the shared internal-stream
normalizer, and hands normalized transactions to the registered callback
(which runs the live monitoring pipeline). Reconnects with backoff so a broker
restart never kills the stream.
"""
import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from app.core.config import settings
from app.integrations.internal_stream import normalizer
from app.streaming.kafka import KafkaConsumerEnterprise

logger = logging.getLogger(__name__)


class InternalTxConsumer:
    def __init__(self, topic: Optional[str] = None):
        self.topic = topic or settings.bank_tx_topic
        self._on_tx: Optional[Callable[[Dict[str, Any]], Coroutine]] = None
        self._stopped = False

    def register_callback(self, on_tx: Callable[[Dict[str, Any]], Coroutine]) -> None:
        self._on_tx = on_tx

    async def _handle_message(self, payload: Dict[str, Any]) -> None:
        results = normalizer.normalize_batch(payload)
        if self._on_tx is None:
            return
        for result in results:
            if not result["ok"]:
                logger.warning(f"Internal-tx stream message rejected: {result['error']}")
                continue
            try:
                await self._on_tx(result["tx"])
            except Exception as e:
                logger.error(f"Internal-tx stream handler failed for {result['ref']}: {e}")

    async def run(self) -> None:
        """Infinite consume loop with reconnect backoff. Only returns on stop."""
        if not self.topic:
            logger.warning("Internal-tx Kafka consumer disabled: no bank_tx_topic configured")
            return
        backoff = 5
        while not self._stopped:
            consumer = KafkaConsumerEnterprise([self.topic])
            try:
                await consumer.start()
                if consumer.consumer is None:
                    if settings.is_production():
                        raise RuntimeError("Kafka consumer failed to start in production - fail closed")
                    backoff = min(backoff * 2, 60)
                    await asyncio.sleep(backoff)
                    continue
                backoff = 5
                logger.info(f"Internal-tx stream consuming from topic={self.topic}")
                await consumer.consume(self._handle_message)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Internal-tx stream loop crashed: {e} - reconnecting in {backoff}s")
            finally:
                try:
                    await consumer.stop()
                except Exception:
                    pass
            if self._stopped:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    async def stop(self) -> None:
        self._stopped = True
