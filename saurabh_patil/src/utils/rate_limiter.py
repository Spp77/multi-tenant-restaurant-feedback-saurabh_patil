"""
src/utils/rate_limiter.py

Tenant-aware in-memory rate limiter.

Strategy
--------
Tracks submission counts in a dict keyed by a composite string:

    rate_limit:{tenant_id}:{YYYY-MM-DD}

Using the ISO date as part of the key means counts automatically reset at
midnight with no cron job or TTL logic required — yesterday's keys simply
become unreachable and are garbage-collected lazily.

Design choice — FastAPI Dependency (not inside FeedbackHandler):
  Gating the request *before* the handler saves CPU (no DB call, no
  sentiment API call) and makes the 429 semantics crystal-clear at the
  HTTP layer rather than buried in business logic.
"""
from datetime import date
from typing import Tuple

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default daily cap — override via RateLimiter(limit=N) for tests
DAILY_LIMIT: int = 100
KEY_PREFIX:   str = "rate_limit"


class RateLimiter:
    """
    In-memory sliding-day rate limiter for multi-tenant APIs.

    Internal layout::

        _store = {
            "rate_limit:pizza-palace-123:2026-04-28": 47,
            "rate_limit:burger-barn-456:2026-04-28":  12,
        }

    Keys are composite so:
    - Different tenants never share counts (isolation).
    - Counts reset automatically at midnight (date rolls over → new key).
    - Old keys accumulate but remain tiny in practice (one int per tenant/day).
    """

    def __init__(self, limit: int = DAILY_LIMIT) -> None:
        self.limit = limit
        # { composite_key: submission_count }
        self._store: dict[str, int] = {}

    # ── Key helpers ────────────────────────────────────────────────────────

    def _make_key(self, tenant_id: str, for_date: date | None = None) -> str:
        """
        Build the composite rate-limit key.

        Parameters
        ----------
        tenant_id : str
            The tenant whose counter we are addressing.
        for_date : date | None
            Override today's date (used in tests to simulate date rollover).
        """
        day = (for_date or date.today()).isoformat()
        return f"{KEY_PREFIX}:{tenant_id}:{day}"

    # ── Public API ─────────────────────────────────────────────────────────

    def current_count(self, tenant_id: str, for_date: date | None = None) -> int:
        """Return how many submissions this tenant has made today (0 if none)."""
        return self._store.get(self._make_key(tenant_id, for_date), 0)

    def is_allowed(self, tenant_id: str, for_date: date | None = None) -> bool:
        """Return True if the tenant has NOT yet reached today's limit."""
        return self.current_count(tenant_id, for_date) < self.limit

    def check_and_increment(
        self, tenant_id: str, for_date: date | None = None
    ) -> Tuple[bool, int]:
        """
        Atomically check the limit then increment on success.

        Returns
        -------
        (allowed, count) : tuple[bool, int]
            - allowed=True  → request is permitted; *count* is the new total.
            - allowed=False → limit reached;  *count* is the current (capped) total.
              A ``limit_exceeded`` security event is logged.

        The check-then-increment is safe here because Python's GIL makes
        dict reads and writes effectively atomic for a single-process server.
        """
        key = self._make_key(tenant_id, for_date)
        count = self._store.get(key, 0)

        if count >= self.limit:
            logger.warning(
                "Rate limit exceeded — request blocked",
                extra={
                    "event":     "limit_exceeded",
                    "tenant_id": tenant_id,
                    "count":     count,
                    "limit":     self.limit,
                    "date":      (for_date or date.today()).isoformat(),
                    "key":       key,
                },
            )
            return False, count

        self._store[key] = count + 1
        return True, count + 1

    def reset(self, tenant_id: str, for_date: date | None = None) -> None:
        """Remove a tenant's counter (used in tests)."""
        self._store.pop(self._make_key(tenant_id, for_date), None)

    def reset_all(self) -> None:
        """Clear every counter (used in tests)."""
        self._store.clear()
