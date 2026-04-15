import pytest
from src.external.sentiment_service import SentimentService
from src.models.feedback import Feedback
from src.api.feedback_handler import FeedbackHandler
from src.storage.dynamodb_client import DynamoDBClient

@pytest.mark.asyncio
async def test_full_premium_flow():
    # Setup
    db = DynamoDBClient()
    svc = SentimentService()
    handler = FeedbackHandler(db, svc)
    
    tenant_data = {
        "tenant_id": "pizza-palace-123",
        "restaurant_name": "Pizza Palace",
        "features": {"sentiment_analysis": True}
    }
    
    fb = Feedback(comment="The pizza was amazing and delicious!", rating=5, tenant_id="pizza-palace-123")
    
    # Execute
    result = await handler.process_feedback(fb, tenant_data)
    
    # Assert
    assert result["status"] == "success"
    assert fb.sentiment_label == "positive"
    assert fb.tenant_id == "pizza-palace-123"

@pytest.mark.asyncio
async def test_empty_comment_validation():
    handler = FeedbackHandler(None, None)
    fb = Feedback(comment="", rating=1, tenant_id="any-tenant")
    result = await handler.process_feedback(fb, {"tenant_id": "any"})
    assert "error" in result
    assert result["code"] == 400

@pytest.mark.asyncio
async def test_basic_plan_no_sentiment():
    db = DynamoDBClient()
    svc = SentimentService()
    handler = FeedbackHandler(db, svc)

    tenant_data = {
        "tenant_id": "burger-barn-456",
        "restaurant_name": "Burger Barn",
        "features": {"sentiment_analysis": False}  # Gated!
    }

    fb = Feedback(comment="Good burger", rating=4, tenant_id="burger-barn-456")
    await handler.process_feedback(fb, tenant_data)

    # sentiment_label is never set when the feature gate is False — stays None
    assert fb.sentiment_label is None

@pytest.mark.asyncio
async def test_sentiment_service_error_handling(monkeypatch):
    # This forces the service to raise an Exception to test our 'Graceful Failure'
    async def mock_fail(*args, **kwargs):
        raise Exception("API Down")

    svc = SentimentService()
    monkeypatch.setattr(svc, "analyze_text", mock_fail)

    handler = FeedbackHandler(DynamoDBClient(), svc)
    fb = Feedback(comment="Amazing!", rating=5, tenant_id="test")

    result = await handler.process_feedback(fb, {"tenant_id": "test", "features": {"sentiment_analysis": True}})

    assert result["status"] == "success"
    assert fb.sentiment_label == "analysis_skipped"  # Proves graceful failure!