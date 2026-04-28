"""
src/utils/cache.py

Lightweight in-memory TTL cache decorators.

Two decorators are provided:

1. ``@cache(ttl=60)``  — generic TTL cache; key = str(args) + str(kwargs).
2. ``@tenant_cache(ttl_seconds=60)``  — specialized for API-key lookups.
   - Masks API keys in logs (``pk_pi***``) — never log full credentials.
   - Logs TTL remaining (seconds) on every cache hit for observability.

Every lookup emits a structured JSON log line:
    {"event": "cache_hit",  "api_key": "pk_pi***", "ttl_remaining": 42}
    {"event": "cache_miss", "api_key": "pk_pi***"}
"""
import functools
import time
from typing import Any, Callable

from src.utils.logger import get_logger

_logger = get_logger(__name__)


class _TTLCache:
    """Simple dict-backed cache with per-entry expiry timestamps."""

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        # {key: (value, expiry_timestamp)}
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> tuple[bool, Any]:
        """Return (hit, value).  Expired entries are evicted on access."""
        if key in self._store:
            value, expiry = self._store[key]
            if time.monotonic() < expiry:
                return True, value
            # Entry expired — evict it
            del self._store[key]
        return False, None

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key* with a TTL from now."""
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self, key: str | None = None) -> None:
        """Evict a single key (or the entire cache when *key* is None)."""
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)

    def ttl_remaining(self, key: str) -> float:
        """Return seconds left before *key* expires, or 0.0 if absent/expired."""
        if key in self._store:
            _, expiry = self._store[key]
            return max(0.0, expiry - time.monotonic())
        return 0.0

    @property
    def size(self) -> int:
        """Number of live (non-expired) entries currently in the cache."""
        now = time.monotonic()
        return sum(1 for _, (_, exp) in self._store.items() if now < exp)


def cache(ttl: float = 60) -> Callable:
    """
    Decorator factory — wraps a function with a TTL-aware in-memory cache.

    Parameters
    ----------
    ttl : float
        Seconds before a cached entry is considered stale.  Default: 60.

    The cache key is derived from ``str(args) + str(sorted(kwargs.items()))``.
    Cache hit / miss events are emitted at INFO level as structured JSON.
    """
    def decorator(func: Callable) -> Callable:
        _cache = _TTLCache(ttl=ttl)
        cache_name = func.__qualname__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            hit, value = _cache.get(key)

            if hit:
                _logger.info(
                    "Cache hit",
                    extra={"event": "cache_hit", "key": key, "cache": cache_name},
                )
                return value

            _logger.info(
                "Cache miss — loading from source",
                extra={"event": "cache_miss", "key": key, "cache": cache_name},
            )
            result = func(*args, **kwargs)
            _cache.set(key, result)
            return result

        # Expose the underlying _TTLCache so tests can inspect / invalidate it
        wrapper._cache = _cache  # type: ignore[attr-defined]
        return wrapper

    return decorator


def tenant_cache(ttl_seconds: float = 60) -> Callable:
    """
    Specialized TTL cache decorator for tenant API-key lookups.

    Key differences from the generic ``@cache``:

    * **Masked API key in logs** — only the first 5 characters are emitted
      (e.g. ``pk_pi***``).  Never log full credentials.
    * **TTL remaining** — cache-hit log includes ``ttl_remaining`` (seconds)
      so operators can see how fresh the cached data is.
    * **Skip caching None** — a failed lookup is never stored, so the next
      request always retries against the live registry.

    Parameters
    ----------
    ttl_seconds : float
        Seconds before a cached entry is considered stale.  Default: 60.

    Usage
    -----
        from src.utils.cache import tenant_cache

        @tenant_cache(ttl_seconds=60)
        def load_tenant_by_api_key(api_key: str) -> Optional[Tenant]:
            ...
    """
    def decorator(func: Callable) -> Callable:
        _cache = _TTLCache(ttl=ttl_seconds)
        cache_name = func.__qualname__

        @functools.wraps(func)
        def wrapper(api_key: str, *args, **kwargs):
            # Mask all but the first 5 characters — security best practice
            masked_key = f"{api_key[:5]}***" if len(api_key) > 5 else "***"

            hit, value = _cache.get(api_key)

            if hit:
                remaining = int(_cache.ttl_remaining(api_key))
                _logger.info(
                    "Cache hit",
                    extra={
                        "event": "cache_hit",
                        "api_key": masked_key,
                        "cache": cache_name,
                        "ttl_remaining": remaining,
                    },
                )
                return value

            _logger.info(
                "Cache miss — loading from source",
                extra={
                    "event": "cache_miss",
                    "api_key": masked_key,
                    "cache": cache_name,
                },
            )
            result = func(api_key, *args, **kwargs)

            # Only cache successful lookups — don't cache unknown keys
            if result is not None:
                _cache.set(api_key, result)

            return result

        # Expose cache for tests (inspect size, invalidate, etc.)
        wrapper._cache = _cache  # type: ignore[attr-defined]
        return wrapper

    return decorator
