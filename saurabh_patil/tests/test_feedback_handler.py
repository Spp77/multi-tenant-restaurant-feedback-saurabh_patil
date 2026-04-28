"""
Integration / End-to-End Tests: FeedbackHandler (tests/test_feedback_handler.py)
Coverage target: 80%+
All external dependencies (DynamoDBClient, SentimentService) are either real
mock implementations or replaced via monkeypatch/unittest.mock.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.api.feedback_handler import FeedbackHandler
from src.storage.dynamodb_client import DynamoDBClient
from src.external.sentiment_service import SentimentService
from src.models.feedback import Feedback


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def real_db():
    return DynamoDBClient()


@pytest.fixture
def real_svc():
    return SentimentService()


@pytest.fixture
def premium_tenant():
    return {
        "tenant_id": "pizza-palace-123",
        "restaurant_name": "Pizza Palace",
        "features": {"sentiment_analysis": True},
    }


@pytest.fixture
def basic_tenant():
    return {
        "tenant_id": "burger-barn-456",
        "restaurant_name": "Burger Barn",
        "features": {"sentiment_analysis": False},
    }


# ── Happy path: Premium plan ──────────────────────────────────────────────────

class TestPremiumPlanFlow:
    @pytest.mark.asyncio
    async def test_positive_sentiment_stored_correctly(self, real_db, real_svc, premium_tenant):
        handler = FeedbackHandler(real_db, real_svc)
        fb = Feedback(comment="The pizza was amazing!", rating=5, tenant_id="pizza-palace-123")

        result = await handler.process_feedback(fb, premium_tenant)

        assert result["status"] == "success"
        assert fb.sentiment_label == "positive"
        assert fb.sentiment_score == 0.95

    @pytest.mark.asyncio
    async def test_feedback_is_persisted_in_db(self, real_db, real_svc, premium_tenant):
        handler = FeedbackHandler(real_db, real_svc)
        fb = Feedback(comment="Delicious crust!", rating=5, tenant_id="pizza-palace-123")

        _ = await handler.process_feedback(fb, premium_tenant)

        stored = real_db.get_item("pizza-palace-123", fb.feedback_id)
        assert stored is not None
        assert stored["comment"] == "Delicious crust!"

    @pytest.mark.asyncio
    async def test_response_contains_expected_keys(self, real_db, real_svc, premium_tenant):
        handler = FeedbackHandler(real_db, real_svc)
        fb = Feedback(comment="amazing food", rating=4, tenant_id="pizza-palace-123")

        result = await handler.process_feedback(fb, premium_tenant)

        assert "status" in result
        assert "feedback_id" in result
        assert "tenant_name" in result
        assert "sentiment_applied" in result

    @pytest.mark.asyncio
    async def test_tenant_id_overwritten_by_handler(self, real_db, real_svc, premium_tenant):
        """Handler always stamps tenant_id from tenant_data onto the Feedback object."""
        handler = FeedbackHandler(real_db, real_svc)
        fb = Feedback(comment="Amazing service", rating=5, tenant_id="wrong-tenant")

        await handler.process_feedback(fb, premium_tenant)

        assert fb.tenant_id == "pizza-palace-123"

    @pytest.mark.asyncio
    async def test_negative_sentiment_flow(self, real_db, real_svc, premium_tenant):
        handler = FeedbackHandler(real_db, real_svc)
        fb = Feedback(comment="Terrible, never coming back.", rating=1, tenant_id="pizza-palace-123")

        result = await handler.process_feedback(fb, premium_tenant)

        assert result["status"] == "success"
        assert fb.sentiment_label == "negative"


# ── Happy path: Basic plan (feature gate OFF) ─────────────────────────────────

class TestBasicPlanFlow:
    @pytest.mark.asyncio
    async def test_sentiment_not_called_for_basic_plan(self, real_db, basic_tenant):
        mock_svc = MagicMock()
        mock_svc.analyze_text = AsyncMock()

        handler = FeedbackHandler(real_db, mock_svc)
        fb = Feedback(comment="Good burger", rating=4, tenant_id="burger-barn-456")

        await handler.process_feedback(fb, basic_tenant)

        mock_svc.analyze_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_sentiment_label_is_none_for_basic_plan(self, real_db, real_svc, basic_tenant):
        handler = FeedbackHandler(real_db, real_svc)
        fb = Feedback(comment="Decent fries", rating=3, tenant_id="burger-barn-456")

        await handler.process_feedback(fb, basic_tenant)

        assert fb.sentiment_label is None

    @pytest.mark.asyncio
    async def test_basic_plan_still_stores_feedback(self, real_db, real_svc, basic_tenant):
        handler = FeedbackHandler(real_db, real_svc)
        fb = Feedback(comment="Nice place", rating=4, tenant_id="burger-barn-456")

        result = await handler.process_feedback(fb, basic_tenant)

        assert result["status"] == "success"
        assert real_db.get_item("burger-barn-456", fb.feedback_id) is not None


# ── Validation failures ───────────────────────────────────────────────────────

class TestValidation:
    @pytest.mark.asyncio
    async def test_empty_comment_returns_400(self):
        handler = FeedbackHandler(None, None)
        fb = Feedback(comment="", rating=3, tenant_id="any-tenant")

        result = await handler.process_feedback(fb, {"tenant_id": "any-tenant"})

        assert "error" in result
        assert result["code"] == 400

    @pytest.mark.asyncio
    async def test_whitespace_only_comment_returns_400(self):
        handler = FeedbackHandler(None, None)
        fb = Feedback(comment="   ", rating=3, tenant_id="any-tenant")

        result = await handler.process_feedback(fb, {"tenant_id": "any-tenant"})

        assert result["code"] == 400

    @pytest.mark.asyncio
    async def test_error_message_in_400_response(self):
        handler = FeedbackHandler(None, None)
        fb = Feedback(comment="", rating=1, tenant_id="any-tenant")

        result = await handler.process_feedback(fb, {"tenant_id": "x"})

        assert "Comment" in result["error"] or "empty" in result["error"].lower()


# ── Graceful failure: Sentiment API down ─────────────────────────────────────

class TestGracefulFailure:
    @pytest.mark.asyncio
    async def test_sentiment_api_failure_still_returns_success(self, real_db, premium_tenant):
        mock_svc = MagicMock()
        mock_svc.analyze_text = AsyncMock(side_effect=Exception("API Down"))

        handler = FeedbackHandler(real_db, mock_svc)
        fb = Feedback(comment="Amazing food!", rating=5, tenant_id="pizza-palace-123")

        result = await handler.process_feedback(fb, premium_tenant)

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_sentiment_api_failure_sets_analysis_skipped(self, real_db, premium_tenant):
        mock_svc = MagicMock()
        mock_svc.analyze_text = AsyncMock(side_effect=Exception("Timeout"))

        handler = FeedbackHandler(real_db, mock_svc)
        fb = Feedback(comment="Delicious pizza!", rating=5, tenant_id="pizza-palace-123")

        await handler.process_feedback(fb, premium_tenant)

        assert fb.sentiment_label == "analysis_skipped"

    @pytest.mark.asyncio
    async def test_sentiment_api_failure_still_stores_item(self, real_db, premium_tenant):
        mock_svc = MagicMock()
        mock_svc.analyze_text = AsyncMock(side_effect=Exception("Network Error"))

        handler = FeedbackHandler(real_db, mock_svc)
        fb = Feedback(comment="Amazing service!", rating=5, tenant_id="pizza-palace-123")

        await handler.process_feedback(fb, premium_tenant)

        assert real_db.get_item("pizza-palace-123", fb.feedback_id) is not None


# ── DB write failure ──────────────────────────────────────────────────────────

class TestDatabaseFailure:
    @pytest.mark.asyncio
    async def test_db_failure_returns_500(self, real_svc, premium_tenant):
        mock_db = MagicMock()
        mock_db.put_item = MagicMock(side_effect=Exception("DynamoDB unavailable"))

        handler = FeedbackHandler(mock_db, real_svc)
        fb = Feedback(comment="Amazing food!", rating=5, tenant_id="pizza-palace-123")

        result = await handler.process_feedback(fb, premium_tenant)

        assert result["code"] == 500
        assert "error" in result


# ── Tenant isolation via handler ──────────────────────────────────────────────

class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_two_tenants_data_is_isolated(self, real_db, real_svc):
        handler = FeedbackHandler(real_db, real_svc)

        tenant_premium = {
            "tenant_id": "pizza-palace-123",
            "restaurant_name": "Pizza Palace",
            "features": {"sentiment_analysis": True},
        }
        tenant_basic = {
            "tenant_id": "burger-barn-456",
            "restaurant_name": "Burger Barn",
            "features": {"sentiment_analysis": False},
        }

        fb1 = Feedback(comment="Amazing pizza!", rating=5, tenant_id="pizza-palace-123")
        fb2 = Feedback(comment="Good burger", rating=4, tenant_id="burger-barn-456")

        await handler.process_feedback(fb1, tenant_premium)
        await handler.process_feedback(fb2, tenant_basic)

        # Pizza Palace only sees its own data
        pizza_records = real_db.query_by_tenant("pizza-palace-123")
        burger_records = real_db.query_by_tenant("burger-barn-456")

        assert len(pizza_records) == 1
        assert pizza_records[0]["comment"] == "Amazing pizza!"
        assert len(burger_records) == 1
        assert burger_records[0]["comment"] == "Good burger"
