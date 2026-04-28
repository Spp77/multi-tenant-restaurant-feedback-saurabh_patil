"""
tests/test_cache.py

Unit tests for src/utils/cache.py

Covers:
  - Cache miss on first call → logs 'cache_miss'
  - Cache hit on second call → logs 'cache_hit'
  - TTL expiry forces a fresh load → logs 'cache_miss'
  - Cache.invalidate() clears a specific entry
  - load_tenant_by_api_key() returns correct Tenant on hit
  - load_tenant_by_api_key() returns None for unknown API key
"""
import io
import time
import logging
from unittest.mock import patch

from src.utils.cache import cache, _TTLCache


def _capture_cache_logs(fn, *args, **kwargs) -> str:
    """
    Call *fn* with *args/kwargs* and return the JSON log output written by the
    'src.utils.cache' logger during that call.

    We can't use capfd/caplog because our JsonFormatter writes to a
    StreamHandler with propagate=False, so we temporarily swap the stream.
    """
    cache_logger = logging.getLogger("src.utils.cache")
    buf = io.StringIO()
    # Replace every handler's stream for the duration of the call
    old_streams = []
    for h in cache_logger.handlers:
        if hasattr(h, "stream"):
            old_streams.append((h, h.stream))
            h.stream = buf
    try:
        fn(*args, **kwargs)
    finally:
        for h, old in old_streams:
            h.stream = old
    return buf.getvalue()


# ── _TTLCache unit tests ──────────────────────────────────────────────────────

class TestTTLCache:
    def test_miss_on_empty_cache(self):
        c = _TTLCache(ttl=60)
        hit, val = c.get("nonexistent")
        assert hit is False
        assert val is None

    def test_set_then_hit(self):
        c = _TTLCache(ttl=60)
        c.set("k", "v")
        hit, val = c.get("k")
        assert hit is True
        assert val == "v"

    def test_entry_expires_after_ttl(self):
        c = _TTLCache(ttl=0.05)   # 50 ms TTL
        c.set("k", "v")
        time.sleep(0.1)
        hit, val = c.get("k")
        assert hit is False
        assert val is None

    def test_invalidate_single_key(self):
        c = _TTLCache(ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.invalidate("a")
        assert c.get("a") == (False, None)
        assert c.get("b") == (True, 2)

    def test_invalidate_all(self):
        c = _TTLCache(ttl=60)
        c.set("a", 1)
        c.set("b", 2)
        c.invalidate()
        assert c.size == 0

    def test_size_counts_live_entries_only(self):
        c = _TTLCache(ttl=0.05)
        c.set("x", 1)
        c.set("y", 2)
        assert c.size == 2
        time.sleep(0.1)
        assert c.size == 0


# ── @cache decorator tests ────────────────────────────────────────────────────

class TestCacheDecorator:
    def test_first_call_is_a_miss_and_calls_fn(self):
        call_count = 0

        @cache(ttl=60)
        def fn(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        result = fn(3)
        assert result == 6
        assert call_count == 1

    def test_second_call_is_a_hit_and_skips_fn(self):
        call_count = 0

        @cache(ttl=60)
        def fn(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        fn(4)
        fn(4)
        assert call_count == 1   # underlying fn called only once

    def test_different_args_are_separate_cache_entries(self):
        call_count = 0

        @cache(ttl=60)
        def fn(x):
            nonlocal call_count
            call_count += 1
            return x

        fn(1)
        fn(2)
        assert call_count == 2

    def test_expiry_triggers_new_call(self):
        call_count = 0

        @cache(ttl=0.05)
        def fn(x):
            nonlocal call_count
            call_count += 1
            return x

        fn("z")
        time.sleep(0.1)
        fn("z")
        assert call_count == 2

    def test_cache_miss_log_is_emitted(self):
        @cache(ttl=60)
        def fn(x):
            return x

        output = _capture_cache_logs(fn, "miss-test")
        assert "cache_miss" in output
        assert "Cache miss" in output

    def test_cache_hit_log_is_emitted(self):
        @cache(ttl=60)
        def fn(x):
            return x

        fn("hit-test")   # populates cache
        output = _capture_cache_logs(fn, "hit-test")  # should hit
        assert "cache_hit" in output
        assert "Cache hit" in output

    def test_exposed_cache_attribute(self):
        @cache(ttl=60)
        def fn(x):
            return x

        assert hasattr(fn, "_cache")
        assert isinstance(fn._cache, _TTLCache)


# ── load_tenant_by_api_key integration tests ─────────────────────────────────

class TestLoadTenantByApiKey:
    def setup_method(self):
        """Clear the cache before every test so they are independent."""
        from src.main import load_tenant_by_api_key
        load_tenant_by_api_key._cache.invalidate()

    def test_returns_tenant_for_valid_api_key(self):
        from src.main import load_tenant_by_api_key
        tenant = load_tenant_by_api_key("pk_pizza_abc123")
        assert tenant is not None
        assert tenant.tenant_id == "pizza-palace-123"
        assert tenant.restaurant_name == "Pizza Palace"

    def test_returns_none_for_unknown_api_key(self):
        from src.main import load_tenant_by_api_key
        tenant = load_tenant_by_api_key("pk_unknown_000")
        assert tenant is None

    def test_second_call_is_served_from_cache(self):
        from src.main import load_tenant_by_api_key

        with patch("src.main._load_registry") as mock_reg:
            mock_reg.return_value = {
                "tenants": [
                    {
                        "tenant_id": "pizza-palace-123",
                        "restaurant_name": "Pizza Palace",
                        "api_key": "pk_pizza_abc123",
                        "plan": "premium",
                        "features": {"sentiment_analysis": True, "advanced_insights": True},
                        "created_at": "2026-01-15T00:00:00Z",
                    }
                ]
            }
            load_tenant_by_api_key("pk_pizza_abc123")   # miss
            load_tenant_by_api_key("pk_pizza_abc123")   # hit
            # Registry should only be read once despite two calls
            assert mock_reg.call_count == 1

    def test_cache_miss_log_on_first_call(self):
        from src.main import load_tenant_by_api_key

        output = _capture_cache_logs(load_tenant_by_api_key, "pk_burger_def456")
        assert "cache_miss" in output
        # Ensure the API key is masked — security requirement
        assert "pk_bu***" in output
        assert "pk_burger_def456" not in output

    def test_cache_hit_log_on_second_call(self):
        from src.main import load_tenant_by_api_key

        load_tenant_by_api_key("pk_sushi_ghi789")  # prime cache
        output = _capture_cache_logs(load_tenant_by_api_key, "pk_sushi_ghi789")  # hit
        assert "cache_hit" in output
        # ttl_remaining must appear in hit log
        assert "ttl_remaining" in output
        # Ensure the API key is masked — security requirement
        assert "pk_su***" in output
        assert "pk_sushi_ghi789" not in output
