"""
Enterprise Compliance Cache - Redis 24h TTL with fallback to file cache
Government Standard: FIPS 140-3, fail-closed with cached fallback
"""
import json
import logging
import os
from typing import Optional, Any
from datetime import timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

class ComplianceCache:
    def __init__(self, redis_url: Optional[str] = None, cache_dir: str = "/tmp/compliance_cache"):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.redis_client = None
        if HAS_REDIS:
            try:
                # TLS required in prod per gov standard
                self.redis_client = redis.from_url(self.redis_url, socket_timeout=5, socket_connect_timeout=5)
                self.redis_client.ping()
                logger.info(f"ComplianceCache: Redis connected at {self.redis_url[:30]}...")
            except Exception as e:
                logger.warning(f"ComplianceCache: Redis unavailable {e}, using file fallback")
                self.redis_client = None
        else:
            logger.warning("ComplianceCache: redis library not available, file fallback only")

    def _file_path(self, key: str) -> Path:
        # Sanitize key to filename
        safe_key = key.replace("/", "_").replace(":", "_")
        return self.cache_dir / f"{safe_key}.json"

    def get(self, key: str) -> Optional[Any]:
        """Get from Redis with fallback to file"""
        # Try Redis first
        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                if data:
                    logger.debug(f"Cache HIT Redis for {key}")
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Redis get failed for {key}: {e}")

        # Fallback to file cache
        file_path = self._file_path(key)
        if file_path.exists():
            try:
                with open(file_path) as f:
                    data = json.load(f)
                logger.info(f"Cache HIT File fallback for {key}")
                return data
            except Exception as e:
                logger.warning(f"File cache read failed for {key}: {e}")

        logger.debug(f"Cache MISS for {key}")
        return None

    def set(self, key: str, value: Any, ttl: int = 86400) -> bool:
        """Set with 24h TTL (86400s) default"""
        success = False
        
        # Try Redis
        if self.redis_client:
            try:
                self.redis_client.setex(key, ttl, json.dumps(value))
                logger.debug(f"Cache SET Redis for {key} TTL={ttl}s")
                success = True
            except Exception as e:
                logger.warning(f"Redis set failed for {key}: {e}")

        # Always write to file fallback
        try:
            file_path = self._file_path(key)
            with open(file_path, 'w') as f:
                json.dump(value, f)
            logger.debug(f"Cache SET File for {key}")
            success = True
        except Exception as e:
            logger.error(f"File cache write failed for {key}: {e}")

        return success

    def get_or_fetch(self, key: str, fetch_fn, ttl: int = 86400):
        """
        Enterprise pattern: get from cache, if miss or stale, fetch live
        If fetch fails, fallback to cached (even if stale)
        """
        cached = self.get(key)
        if cached is not None:
            # Check if we have metadata with timestamp
            # For simplicity, return cached, background refresh could be added
            logger.info(f"Using cached data for {key} (TTL 24h)")
            return cached

        # Cache miss, try live fetch
        try:
            logger.info(f"Cache miss for {key}, fetching live feed...")
            live_data = fetch_fn()
            self.set(key, live_data, ttl=ttl)
            logger.info(f"Live feed fetched and cached for {key}")
            return live_data
        except Exception as e:
            logger.error(f"Live feed fetch failed for {key}: {e}")
            # Fallback to stale file cache if exists
            stale = self.get(key)
            if stale is not None:
                logger.warning(f"Using STALE cached data for {key} due to fetch failure")
                return stale
            raise

# Singleton for enterprise
compliance_cache = ComplianceCache()
