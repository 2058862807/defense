"""
ZK Resilience + Circuit Breaker
Requirement: graceful degradation if ZK prover down, Kafka down, DB down, etc.
"""
import pybreaker
import logging
import time
from functools import wraps
from typing import Callable, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

# Global breakers
zk_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.cb_fail_max,
    reset_timeout=settings.cb_reset_timeout,
    name="zk-prover"
)

ml_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.cb_fail_max,
    reset_timeout=settings.cb_reset_timeout,
    name="ml-scorer"
)

evm_breaker = pybreaker.CircuitBreaker(
    fail_max=settings.cb_fail_max,
    reset_timeout=settings.cb_reset_timeout,
    name="evm-relay"
)

def zk_resilient(fallback: Callable = None):
    """
    Decorator: try ZK path, on failure use fallback if zk_fallback_enabled
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                # Circuit breaker protects ZK prover calls
                return zk_breaker.call(func, *args, **kwargs)
            except pybreaker.CircuitBreakerError:
                logger.warning(f"ZK circuit OPEN for {func.__name__} - using fallback")
                if not settings.zk_fallback_enabled:
                    raise
                if fallback:
                    return fallback(*args, **kwargs)
                # Degraded mode: return unverified but logged
                return {
                    "status": "DEGRADED_NO_ZK",
                    "result": fallback(*args, **kwargs) if fallback else None,
                    "zk_proof": None,
                    "warning": "ZK prover unavailable, manual verification required"
                }
            except Exception as e:
                logger.error(f"ZK call failed: {e}")
                if settings.zk_fallback_enabled and fallback:
                    return fallback(*args, **kwargs)
                raise
        return wrapper
    return decorator

# Listeners for observability
class BreakerListener(pybreaker.CircuitBreakerListener):
    def state_change(self, cb, old_state, new_state):
        logger.warning(f"Circuit breaker {cb.name}: {old_state} -> {new_state}")

zk_breaker.add_listener(BreakerListener())
ml_breaker.add_listener(BreakerListener())
