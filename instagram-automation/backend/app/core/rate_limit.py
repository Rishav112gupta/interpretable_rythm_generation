"""Small fixed-window rate limiter.

Uses Redis when reachable (shared across API replicas) and falls back to an
in-process counter so development and tests work without Redis.
"""

from __future__ import annotations

import logging
import threading
import time

from app.core.config import settings
from app.core.errors import RateLimited

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self) -> None:
        self._memory: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._redis = None
        self._redis_checked = False

    def _get_redis(self):
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        if settings.app_env == "test":
            return None
        try:
            import redis

            client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=0.5, socket_timeout=0.5)
            client.ping()
            self._redis = client
        except Exception:
            logger.info("Redis unavailable for rate limiting; using in-memory limiter")
            self._redis = None
        return self._redis

    def hit(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return
        window = int(time.time() // window_seconds)
        bucket = f"ratelimit:{key}:{window}"
        client = self._get_redis()
        if client is not None:
            try:
                count = client.incr(bucket)
                if count == 1:
                    client.expire(bucket, window_seconds)
                if count > limit:
                    raise RateLimited("Too many requests. Please wait a minute and try again.")
                return
            except RateLimited:
                raise
            except Exception:
                logger.warning("Redis rate-limit error; falling back to memory")
        with self._lock:
            count, _ = self._memory.get(bucket, (0, 0.0))
            count += 1
            self._memory[bucket] = (count, time.time())
            if len(self._memory) > 10000:
                self._memory.clear()
        if count > limit:
            raise RateLimited("Too many requests. Please wait a minute and try again.")

    def reset(self) -> None:
        with self._lock:
            self._memory.clear()


rate_limiter = RateLimiter()
