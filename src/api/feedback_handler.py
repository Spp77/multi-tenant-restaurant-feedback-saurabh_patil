import logging
from typing import Dict, Any
from src.models.feedback import Feedback
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FeedbackHandler:
    """
    Orchestrates the full feedback submission pipeline for a given tenant.

    Designed to be HTTP-agnostic — returns plain dicts so the same instance
    can be driven from a FastAPI route, a CLI script, or a background task
    without coupling to any transport layer.
    """

    def __init__(self, db_client, sentiment_svc):
        """
        Args:
            db_client:      DynamoDBClient (or any compatible mock) for persistence.
            sentiment_svc:  SentimentService (or mock) for text analysis.
        """
        self.db = db_client
        self.sentiment_svc = sentiment_svc

    async def process_feedback(
        self, feedback: Feedback, tenant_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run the full pipeline: Validation → Feature Gate → Sentiment API → Storage.

        Sentiment failures are intentionally swallowed — an enrichment outage must
        never block persisting the customer's review. Failed records are marked
        ``sentiment_label="analysis_skipped"`` for later back-fill.

        Args:
            feedback:     Populated Feedback model. ``tenant_id`` will be overwritten
                          by ``tenant_data["tenant_id"]`` to prevent spoofing.
            tenant_data:  Dict loaded from the tenant registry, containing at minimum
                          ``tenant_id``, ``restaurant_name``, and ``features``.

        Returns:
            On success::

                {
                    "status": "success",
                    "feedback_id": "<uuid>",
                    "tenant_name": "<str>",
                    "sentiment_applied": "<label | None>"
                }

            On validation failure::

                {"error": "Comment cannot be empty", "code": 400}

            On unexpected failure::

                {"error": "Internal Server Error", "code": 500}

        Raises:
            Does not raise — all exceptions are caught and returned as error dicts.
        """
        logger.info(f"Processing feedback for tenant: {tenant_data.get('tenant_id')}")

        if not feedback.comment or not feedback.comment.strip():
            return {"error": "Comment cannot be empty", "code": 400}

        try:
            feedback.tenant_id = tenant_data["tenant_id"]

            features = tenant_data.get("features", {})
            if features.get("sentiment_analysis"):
                try:
                    label, score = await self.sentiment_svc.analyze_text(feedback.comment)
                    feedback.sentiment_label = label
                    feedback.sentiment_score = score
                except Exception as e:
                    logger.warning(f"Sentiment API failed: {e}. Storing without label.")
                    feedback.sentiment_label = "analysis_skipped"

            self.db.put_item(feedback)
            logger.info(f"Stored feedback {feedback.feedback_id}")

            return {
                "status": "success",
                "feedback_id": feedback.feedback_id,
                "tenant_name": tenant_data.get("restaurant_name"),
                "sentiment_applied": feedback.sentiment_label,
            }

        except Exception as e:
            logger.critical(f"Unhandled failure in FeedbackHandler: {e}")
            return {"error": "Internal Server Error", "code": 500}