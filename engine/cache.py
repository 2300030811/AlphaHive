import os
import json
import logging
import time

logger = logging.getLogger("alphahive.engine.cache")


class SignalCache:
    def __init__(self):
        # Lazy redis connection: avoid hard crash if redis is unavailable at import time
        self._redis = None
        self._memory_cache: dict[str, tuple[str, float]] = {}
        self.SWARM_TTL = 6 * 60 * 60      # 6 hours in seconds
        self.SIGNAL_TTL = 1 * 60 * 60     # 1 hour for full signals
    
    async def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379"),
                encoding="utf-8",
                decode_responses=True
            )
            # test connection
            try:
                await self._redis.ping()
            except Exception:
                logger.warning("Redis ping failed during lazy init — using in-memory fallback")
                self._redis = None
        except Exception as e:
            logger.warning(f"Failed to import redis.asyncio: {e}. Using in-memory cache fallback.")
            self._redis = None
        return self._redis

    async def get_swarm(self, ticker: str) -> dict | None:
        """Get cached swarm result. Returns None if not cached."""
        key = f"swarm:{ticker}"
        redis = await self._get_redis()
        if redis:
            try:
                data = await redis.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Redis get_swarm failed for {ticker}: {e}")
                # fall through to memory fallback

        # memory fallback
        entry = self._memory_cache.get(key)
        if not entry:
            return None
        data_str, expire_ts = entry
        if expire_ts and time.time() > expire_ts:
            # expired
            del self._memory_cache[key]
            return None
        try:
            return json.loads(data_str)
        except Exception:
            return None
    
    async def set_swarm(self, ticker: str, swarm_result: dict):
        """Cache swarm result for 6 hours."""
        key = f"swarm:{ticker}"
        redis = await self._get_redis()
        if redis:
            try:
                await redis.set(key, json.dumps(swarm_result), ex=self.SWARM_TTL)
                return
            except Exception as e:
                logger.warning(f"Redis set_swarm failed for {ticker}: {e}")

        # memory fallback with expiry
        expire_ts = time.time() + self.SWARM_TTL if self.SWARM_TTL else 0
        self._memory_cache[key] = (json.dumps(swarm_result), expire_ts)
    
    async def get_signal(self, ticker: str) -> dict | None:
        """Get full cached AlphaHiveSignal."""
        key = f"signal:{ticker}"
        redis = await self._get_redis()
        if redis:
            try:
                data = await redis.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Redis get_signal failed for {ticker}: {e}")

        entry = self._memory_cache.get(key)
        if not entry:
            return None
        data_str, expire_ts = entry
        if expire_ts and time.time() > expire_ts:
            del self._memory_cache[key]
            return None
        try:
            return json.loads(data_str)
        except Exception:
            return None
    
    async def set_signal(self, ticker: str, signal: dict):
        """Cache full signal for 1 hour."""
        key = f"signal:{ticker}"
        redis = await self._get_redis()
        if redis:
            try:
                await redis.set(key, json.dumps(signal), ex=self.SIGNAL_TTL)
                return
            except Exception as e:
                logger.warning(f"Redis set_signal failed for {ticker}: {e}")

        expire_ts = time.time() + self.SIGNAL_TTL if self.SIGNAL_TTL else 0
        self._memory_cache[key] = (json.dumps(signal), expire_ts)
    
    async def invalidate(self, ticker: str):
        """Force refresh — delete both cached values for a ticker."""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.delete(f"swarm:{ticker}")
                await redis.delete(f"signal:{ticker}")
            except Exception as e:
                logger.warning(f"Redis invalidate failed for {ticker}: {e}")

        # ensure memory fallback cleared as well
        self._memory_cache.pop(f"swarm:{ticker}", None)
        self._memory_cache.pop(f"signal:{ticker}", None)
    
    async def health(self) -> bool:
        """Check Redis connection."""
        redis = await self._get_redis()
        if redis:
            try:
                await redis.ping()
                return True
            except Exception:
                return False
        # no redis — still healthy but using fallback
        return False
