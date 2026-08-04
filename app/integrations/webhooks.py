"""
Signed webhook delivery (C2 - universal integration).

Every scored decision and metered event can be pushed to a customer's own
endpoint (bank middleware, core-banking bus, AML/transaction-monitoring stack).
Delivery is:

  * Signed - HMAC-SHA256 over the exact JSON body, header:
      X-Protean-Signature: sha256=<hex>
      X-Protean-Event: <event_type>
      X-Protean-Delivery: <delivery_id>
      X-Protean-Timestamp: <unix_seconds>
  * Reliable - asynchronous delivery with retry + exponential backoff (3
    attempts), each delivery persisted in the metering store for audit.
  * Verifiable - SDKs ship a signature checker; receivers can recompute the
    signature from the raw body + their registered secret.
"""
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
import uuid
import urllib.request
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.metering.store import metering_store

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3
_BACKOFF_BASE = 1.0
_TIMEOUT_SECONDS = 10


def _canonical_body(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def compute_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    expected = compute_signature(secret, body)
    return hmac.compare_digest(expected, signature)


def register_webhook(customer_id: str, url: str, events: List[str]) -> Dict[str, Any]:
    return metering_store.register_webhook(customer_id, url, events)


def list_webhooks(customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return metering_store.list_webhooks(customer_id)


def deliver_event(event_type: str, payload: Dict[str, Any], customer_id: Optional[str] = None) -> List[str]:
    """Enqueue the event to every subscribed webhook. Returns delivery ids."""
    hooks = metering_store.list_webhooks(customer_id)
    delivery_ids: List[str] = []
    for hook in hooks:
        if event_type not in hook["events"]:
            continue
        delivery_id = str(uuid.uuid4())
        delivery_ids.append(delivery_id)
        threading.Thread(
            target=_deliver_worker,
            args=(hook, event_type, payload, delivery_id),
            daemon=True,
            name=f"webhook-{delivery_id[:8]}",
        ).start()
    return delivery_ids


def _deliver_worker(hook: Dict[str, Any], event_type: str, payload: Dict[str, Any], delivery_id: str) -> None:
    body = _canonical_body(payload)
    payload_hash = hashlib.sha256(body).hexdigest()
    signature = compute_signature(hook["secret"], body)
    attempt = 0
    backoff = _BACKOFF_BASE
    last_error: Optional[str] = None

    while attempt < _MAX_ATTEMPTS:
        attempt += 1
        try:
            req = urllib.request.Request(
                hook["url"],
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Protean-Signature": signature,
                    "X-Protean-Event": event_type,
                    "X-Protean-Delivery": delivery_id,
                    "X-Protean-Timestamp": str(int(time.time())),
                    "User-Agent": "protean-defense-webhook/2.0",
                },
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                status = resp.status
            if status < 200 or status >= 300:
                raise RuntimeError(f"webhook returned HTTP {status}")
            metering_store.record_webhook_delivery(hook["id"], event_type, payload_hash, "delivered", attempt)
            logger.info(f"webhook {event_type} delivered to {hook['url']} (delivery={delivery_id[:8]})")
            return
        except Exception as e:
            last_error = str(e)
            if attempt < _MAX_ATTEMPTS:
                time.sleep(backoff)
                backoff *= 2

    metering_store.record_webhook_delivery(hook["id"], event_type, payload_hash, "failed", _MAX_ATTEMPTS, last_error)
    logger.error(f"webhook {event_type} delivery FAILED to {hook['url']}: {last_error}")
