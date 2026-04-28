"""
tests/test_rate_limiter.py

Unit + integration tests for tenant-aware rate limiting.

Covers:
  - RateLimiter unit: allowed/blocked/count logic
  - Composite key format includes tenant_id and ISO date
  - Daily reset via date rollover simulation
  - Limit-exceeded log emits correct security event
  - POST /api/feedback returns HTTP 429 when limit hit
  - POST /api/feedback still returns 201 for a different tenant (isolation)
  - Insights endpoint is NOT rate-limited (reads are free)
"""
import io
import logging
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from src.utils.rate_limiter import RateLimiter, KEY_PREFIX


# ── Helpers ────────────────────────────────────────────────────────────────────

def _capture_rate_limit_logs(limiter: RateLimiter, tenant_id: str) -> str:
    """Capture JSON log output emitted by the rate_limiter logger."""
    rl_logger = logging.getLogger("src.utils.rate_limiter")
    buf = io.StringIO()
    old_streams = []
    for h in rl_logger.handlers:
        if hasattr(h, "stream"):
            old_streams.append((h, h.stream))
            h.stream = buf
    try:
        limiter.check_and_increment(tenant_id)
    finally:
        for h, old in old_streams:
            h.stream = old
    return buf.getvalue()


def _make_pizza_payload() -> dict:
    return {"tenant_id": "pizza-palace-123", "rating": 4, "comment": "Great pizza!"}


PIZZA_HEADERS  = {"x-tenant-id": "pizza-palace-123"}
BURGER_HEADERS = {"x-tenant-id": "burger-barn-456"}


# ── RateLimiter unit tests ─────────────────────────────────────────────────────

class TestRateLimiterUnit:

    def test_first_call_is_allowed(self):
        rl = RateLimiter(limit=5)
        allowed, count = rl.check_and_increment("tenant-a")
        assert allowed is True
        assert count == 1

    def test_count_increments_on_each_allowed_call(self):
        rl = RateLimiter(limit=5)
        for expected in range(1, 4):
            allowed, count = rl.check_and_increment("tenant-a")
            assert allowed is True
            assert count == expected

    def test_exact_limit_call_is_still_allowed(self):
        """The 100th call should succeed; the 101st should be blocked."""
        rl = RateLimiter(limit=3)
        rl.check_and_increment("t")
        rl.check_and_increment("t")
        allowed, count = rl.check_and_increment("t")   # 3rd = at limit
        assert allowed is True
        assert count == 3

    def test_call_beyond_limit_is_blocked(self):
        rl = RateLimiter(limit=3)
        for _ in range(3):
            rl.check_and_increment("t")
        allowed, count = rl.check_and_increment("t")   # 4th = over limit
        assert allowed is False
        assert count == 3   # count stays at the cap

    def test_different_tenants_have_independent_counters(self):
        rl = RateLimiter(limit=2)
        rl.check_and_increment("tenant-a")
        rl.check_and_increment("tenant-a")
        # tenant-a is now blocked
        blocked, _ = rl.check_and_increment("tenant-a")
        # tenant-b should still be free
        allowed, count = rl.check_and_increment("tenant-b")
        assert blocked is False
        assert allowed is True
        assert count == 1

    def test_current_count_returns_zero_before_first_call(self):
        rl = RateLimiter(limit=10)
        assert rl.current_count("new-tenant") == 0

    def test_is_allowed_returns_false_when_at_limit(self):
        rl = RateLimiter(limit=2)
        rl.check_and_increment("t")
        rl.check_and_increment("t")
        assert rl.is_allowed("t") is False

    def test_reset_clears_a_single_tenant(self):
        rl = RateLimiter(limit=2)
        rl.check_and_increment("tenant-a")
        rl.check_and_increment("tenant-a")
        rl.reset("tenant-a")
        assert rl.current_count("tenant-a") == 0

    def test_reset_all_clears_every_tenant(self):
        rl = RateLimiter(limit=10)
        rl.check_and_increment("tenant-a")
        rl.check_and_increment("tenant-b")
        rl.reset_all()
        assert rl.current_count("tenant-a") == 0
        assert rl.current_count("tenant-b") == 0


# ── Composite key tests ────────────────────────────────────────────────────────

class TestCompositeKey:

    def test_key_format_contains_prefix_tenant_and_date(self):
        rl = RateLimiter()
        today = date.today().isoformat()
        key = rl._make_key("pizza-palace-123")
        assert key == f"{KEY_PREFIX}:pizza-palace-123:{today}"

    def test_keys_for_different_dates_are_distinct(self):
        rl = RateLimiter()
        today     = date.today()
        yesterday = today - timedelta(days=1)
        assert rl._make_key("t", today) != rl._make_key("t", yesterday)

    def test_daily_reset_via_date_rollover(self):
        """
        Simulate midnight rollover: exhaust limit on 'today', then verify
        the same tenant is allowed again when the date advances.
        """
        rl = RateLimiter(limit=2)
        today     = date.today()
        tomorrow  = today + timedelta(days=1)

        # Exhaust today's limit
        rl.check_and_increment("t", for_date=today)
        rl.check_and_increment("t", for_date=today)
        blocked, _ = rl.check_and_increment("t", for_date=today)
        assert blocked is False

        # Tomorrow's counter starts fresh
        allowed, count = rl.check_and_increment("t", for_date=tomorrow)
        assert allowed is True
        assert count == 1


# ── Logging tests ──────────────────────────────────────────────────────────────

class TestRateLimiterLogging:

    def test_limit_exceeded_log_contains_security_event(self):
        rl = RateLimiter(limit=1)
        rl.check_and_increment("log-tenant")       # consumes the 1 allowed slot

        output = _capture_rate_limit_logs(rl, "log-tenant")  # blocked call
        assert "limit_exceeded" in output

    def test_limit_exceeded_log_contains_tenant_id(self):
        rl = RateLimiter(limit=1)
        rl.check_and_increment("log-tenant-2")

        output = _capture_rate_limit_logs(rl, "log-tenant-2")
        assert "log-tenant-2" in output

    def test_limit_exceeded_log_contains_count_and_limit(self):
        rl = RateLimiter(limit=2)
        rl.check_and_increment("t")
        rl.check_and_increment("t")

        output = _capture_rate_limit_logs(rl, "t")
        assert "\"count\": 2" in output or "\"count\":2" in output
        assert "\"limit\": 2" in output or "\"limit\":2" in output

    def test_allowed_call_does_not_log_limit_exceeded(self):
        rl = RateLimiter(limit=10)
        output = _capture_rate_limit_logs(rl, "safe-tenant")
        assert "limit_exceeded" not in output


# ── Integration tests (FastAPI route) ─────────────────────────────────────────

class TestRateLimitIntegration:
    """
    These tests replace the global rate_limiter in main with a fresh instance
    so we never bleed state from other test classes.
    """

    @pytest.fixture(autouse=True)
    def fresh_limiter(self):
        """Patch the global rate_limiter with a fresh one before each test."""
        import src.main as main_module
        fresh = RateLimiter(limit=100)
        old   = main_module.rate_limiter
        main_module.rate_limiter = fresh
        yield fresh
        main_module.rate_limiter = old

    @pytest.fixture()
    def client(self):
        from src.main import app
        return TestClient(app)

    def test_first_submission_returns_201(self, client):
        resp = client.post("/api/feedback", json=_make_pizza_payload(), headers=PIZZA_HEADERS)
        assert resp.status_code == 201

    def test_101st_submission_returns_429(self, client, fresh_limiter):
        """Burn through all 100 slots then expect a 429 on the next request."""
        # Directly exhaust the counter to avoid 100 HTTP calls
        for _ in range(100):
            fresh_limiter.check_and_increment("pizza-palace-123")

        resp = client.post("/api/feedback", json=_make_pizza_payload(), headers=PIZZA_HEADERS)
        assert resp.status_code == 429

    def test_429_response_body_contains_error_key(self, client, fresh_limiter):
        for _ in range(100):
            fresh_limiter.check_and_increment("pizza-palace-123")

        resp = client.post("/api/feedback", json=_make_pizza_payload(), headers=PIZZA_HEADERS)
        body = resp.json()["detail"]
        assert body["error"] == "rate_limit_exceeded"
        assert "pizza-palace-123" in body["tenant_id"]
        assert body["submissions_today"] == 100

    def test_rate_limit_is_per_tenant(self, client, fresh_limiter):
        """Blocking pizza-palace should not affect burger-barn."""
        for _ in range(100):
            fresh_limiter.check_and_increment("pizza-palace-123")

        # pizza is blocked
        resp_pizza = client.post(
            "/api/feedback", json=_make_pizza_payload(), headers=PIZZA_HEADERS
        )
        # burger is still free
        resp_burger = client.post(
            "/api/feedback",
            json={"tenant_id": "burger-barn-456", "rating": 3, "comment": "decent"},
            headers=BURGER_HEADERS,
        )
        assert resp_pizza.status_code  == 429
        assert resp_burger.status_code == 201

    def test_insights_endpoint_is_not_rate_limited(self, client, fresh_limiter):
        """GET /insights must not be gated by the submission rate limiter."""
        # Exhaust pizza's write quota
        for _ in range(100):
            fresh_limiter.check_and_increment("pizza-palace-123")

        # Reads should still succeed
        resp = client.get(
            "/api/restaurants/pizza-palace-123/insights", headers=PIZZA_HEADERS
        )
        assert resp.status_code == 200

    def test_invalid_tenant_still_returns_401_not_429(self, client):
        """Auth failure must return 401 before rate limiting is even checked."""
        resp = client.post(
            "/api/feedback",
            json=_make_pizza_payload(),
            headers={"x-tenant-id": "unknown-tenant"},
        )
        assert resp.status_code == 401
