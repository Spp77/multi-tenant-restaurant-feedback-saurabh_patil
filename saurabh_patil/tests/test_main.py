"""
Integration Tests: FastAPI routes (tests/test_main.py)
Uses httpx AsyncClient to test the full HTTP layer — brings main.py coverage to 90%+.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from src.main import app


# ── Helper ─────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


PREMIUM_HEADERS = {"x-tenant-id": "pizza-palace-123"}
BASIC_HEADERS   = {"x-tenant-id": "burger-barn-456"}
INVALID_HEADERS = {"x-tenant-id": "unknown-tenant-999"}


# ── Health check ───────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_online_status(self, client):
        resp = await client.get("/health")
        assert resp.json()["status"] == "online"


# ── POST /api/feedback ─────────────────────────────────────────────────────────

class TestCreateFeedback:
    @pytest.mark.asyncio
    async def test_premium_tenant_returns_201(self, client):
        resp = await client.post(
            "/api/feedback",
            json={"comment": "Amazing pizza!", "rating": 5, "tenant_id": "pizza-palace-123"},
            headers=PREMIUM_HEADERS,
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_response_contains_feedback_id(self, client):
        resp = await client.post(
            "/api/feedback",
            json={"comment": "Delicious crust!", "rating": 5, "tenant_id": "pizza-palace-123"},
            headers=PREMIUM_HEADERS,
        )
        assert "feedback_id" in resp.json()

    @pytest.mark.asyncio
    async def test_premium_tenant_gets_sentiment_applied(self, client):
        resp = await client.post(
            "/api/feedback",
            json={"comment": "Amazing and delicious!", "rating": 5, "tenant_id": "pizza-palace-123"},
            headers=PREMIUM_HEADERS,
        )
        data = resp.json()
        assert data["sentiment_applied"] == "positive"

    @pytest.mark.asyncio
    async def test_basic_tenant_returns_201(self, client):
        resp = await client.post(
            "/api/feedback",
            json={"comment": "Good burger", "rating": 4, "tenant_id": "burger-barn-456"},
            headers=BASIC_HEADERS,
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_invalid_tenant_returns_401(self, client):
        resp = await client.post(
            "/api/feedback",
            json={"comment": "Nice food", "rating": 4, "tenant_id": "x"},
            headers=INVALID_HEADERS,
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_comment_returns_400(self, client):
        resp = await client.post(
            "/api/feedback",
            json={"comment": "", "rating": 3, "tenant_id": "pizza-palace-123"},
            headers=PREMIUM_HEADERS,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_missing_tenant_header_returns_422(self, client):
        """FastAPI returns 422 when a required header is missing."""
        resp = await client.post(
            "/api/feedback",
            json={"comment": "Nice", "rating": 4, "tenant_id": "x"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_rating_below_range_returns_422(self, client):
        resp = await client.post(
            "/api/feedback",
            json={"comment": "Meh", "rating": 0, "tenant_id": "pizza-palace-123"},
            headers=PREMIUM_HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_rating_above_range_returns_422(self, client):
        resp = await client.post(
            "/api/feedback",
            json={"comment": "Too good", "rating": 6, "tenant_id": "pizza-palace-123"},
            headers=PREMIUM_HEADERS,
        )
        assert resp.status_code == 422


# ── GET /api/restaurants/{tenant_id}/insights ─────────────────────────────────

class TestInsightsEndpoint:
    @pytest.mark.asyncio
    async def test_insights_returns_200_with_data(self, client):
        # First submit some feedback
        await client.post(
            "/api/feedback",
            json={"comment": "Amazing pizza!", "rating": 5, "tenant_id": "pizza-palace-123"},
            headers=PREMIUM_HEADERS,
        )
        resp = await client.get(
            "/api/restaurants/pizza-palace-123/insights",
            headers=PREMIUM_HEADERS,
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_insights_response_shape(self, client):
        resp = await client.get(
            "/api/restaurants/pizza-palace-123/insights",
            headers=PREMIUM_HEADERS,
        )
        data = resp.json()
        assert "total_feedback" in data
        assert "average_rating" in data
        assert "sentiment_breakdown" in data
        assert "top_complaints" in data

    @pytest.mark.asyncio
    async def test_insights_cross_tenant_access_denied(self, client):
        """Basic tenant cannot view premium tenant's insights."""
        resp = await client.get(
            "/api/restaurants/pizza-palace-123/insights",
            headers=BASIC_HEADERS,   # wrong tenant
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_insights_invalid_tenant_returns_401(self, client):
        resp = await client.get(
            "/api/restaurants/pizza-palace-123/insights",
            headers=INVALID_HEADERS,
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_insights_empty_tenant_returns_zero_totals(self, client):
        """Sushi Spot has not submitted any feedback yet — should return zeros."""
        resp = await client.get(
            "/api/restaurants/sushi-spot-789/insights",
            headers={"x-tenant-id": "sushi-spot-789"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_feedback"] == 0
        assert data["average_rating"] is None
