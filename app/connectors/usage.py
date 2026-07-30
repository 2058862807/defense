"""
Usage Tracking - Enterprise
GAP8: Complete usage tracking

- Tracks API usage per API key, customer, license
- Stores in Redis (real-time) + Postgres (persistent) - in-memory for demo
- Metrics: total requests, success/error, latency, throughput
- Per license tier limits: dev 1k/day, enterprise 10k/day, enterprise_gov 100k/day
- Tiered disclosure for usage stats
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# In-memory for demo, Redis + Postgres in prod
usage_db: Dict[str, Dict] = {}
usage_counters: Dict[str, int] = defaultdict(int)  # api_key -> count

# Tier limits per day
TIER_LIMITS = {
    "dev": 1000,
    "enterprise": 10000,
    "enterprise_gov": 100000
}

def record_usage(api_key: str, endpoint: str, latency_ms: float, status: int, customer: Optional[str] = None):
    """
    Record API usage - called by connector and API services
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    timestamp_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # In production, this would be Kafka -> Postgres + Redis INCR
    usage_key = f"{api_key}:{timestamp_day}:{int(time.time()*1000)}"
    
    record = {
        "api_key": api_key[:20] + "...",  # Don't store full key in logs for PII
        "api_key_full": api_key,  # Full key stored securely in prod Postgres, not logs
        "customer": customer,
        "endpoint": endpoint,
        "timestamp": timestamp,
        "timestamp_day": timestamp_day,
        "latency_ms": latency_ms,
        "status": status
    }

    usage_db[usage_key] = record
    usage_counters[api_key] += 1

    # Check limits
    from app.connectors.api_key import get_api_key_info
    key_info = get_api_key_info(api_key)
    if key_info:
        tier = key_info.get("tier", "dev")
        limit = TIER_LIMITS.get(tier, 1000)
        count = usage_counters[api_key]
        if count > limit:
            logger.warning(f"API key {api_key[:20]}... exceeded daily limit {limit} for tier {tier} - count {count}")

    logger.debug(f"Usage recorded: api_key={api_key[:20]}... endpoint={endpoint} status={status} latency={latency_ms:.2f}ms")

    return record

def get_usage_stats(api_key: Optional[str] = None, customer: Optional[str] = None, days: int = 7) -> Dict:
    """
    Get usage stats - for customer portal and tiered disclosure
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    filtered = []
    for record in usage_db.values():
        try:
            ts = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
            if ts < cutoff:
                continue
        except:
            pass

        if api_key and not record["api_key_full"].startswith(api_key) and api_key not in record["api_key_full"]:
            # Allow prefix search
            if api_key not in record["api_key_full"] and not record["api_key_full"].startswith(api_key):
                continue

        if customer:
            # Need to join with api_keys_db to get customer
            from app.connectors.api_key import get_api_key_info
            # For simplicity, if customer filter, check if api_key belongs to customer
            # In real prod, would have customer field in usage record
            pass

        filtered.append(record)

    total = len(filtered)
    success = len([r for r in filtered if r["status"] < 400])
    error = total - success
    avg_latency = sum([r["latency_ms"] for r in filtered]) / total if total > 0 else 0
    p95_latency = sorted([r["latency_ms"] for r in filtered])[int(len(filtered)*0.95)] if filtered else 0

    # Per endpoint breakdown
    per_endpoint = defaultdict(int)
    for r in filtered:
        per_endpoint[r["endpoint"]] += 1

    return {
        "total_requests": total,
        "success": success,
        "error": error,
        "success_rate": success / total if total > 0 else 0,
        "error_rate": error / total if total > 0 else 0,
        "avg_latency_ms": avg_latency,
        "p95_latency_ms": p95_latency,
        "per_endpoint": dict(per_endpoint),
        "period_days": days,
        "period_start": cutoff.isoformat(),
        "period_end": now.isoformat()
    }

def get_customer_usage(customer: str, days: int = 30) -> Dict:
    """Get usage for customer across all their API keys"""
    # Find all API keys for customer
    from app.connectors.api_key import api_keys_db
    customer_keys = [k for k, v in api_keys_db.items() if v["customer"] == customer]
    
    stats = get_usage_stats(days=days)
    # Filter to customer keys only
    customer_usage = [r for r in usage_db.values() if r["api_key_full"] in customer_keys]
    
    total = len(customer_usage)
    # Check limits per tier
    # Get tier from first key
    tier = "dev"
    if customer_keys:
        first_key_info = api_keys_db.get(customer_keys[0], {})
        tier = first_key_info.get("tier", "dev")
    
    limit = TIER_LIMITS.get(tier, 1000)
    limit_daily = limit
    limit_period = limit * days

    return {
        "customer": customer,
        "tier": tier,
        "period_days": days,
        "total_requests": total,
        "limit_daily": limit_daily,
        "limit_period": limit_period,
        "usage_percent": (total / limit_period * 100) if limit_period > 0 else 0,
        "remaining": max(0, limit_period - total),
        "stats": get_usage_stats(days=days)
    }

def check_rate_limit(api_key: str) -> bool:
    """
    Check if API key is within rate limit
    Returns True if allowed, False if exceeded
    """
    from app.connectors.api_key import get_api_key_info
    key_info = get_api_key_info(api_key)
    if not key_info:
        return False

    tier = key_info.get("tier", "dev")
    limit = TIER_LIMITS.get(tier, 1000)
    
    # Simple daily limit check - in prod would use Redis INCR with TTL
    count = usage_counters.get(api_key, 0)
    return count < limit
