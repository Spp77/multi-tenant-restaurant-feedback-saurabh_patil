# FEATURE: ERROR HANDLING IMPROVEMENTS
import logging
from typing import Dict, Any
from src.models.feedback import Feedback
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FeedbackHandler:
    def __init__(self, db_client, sentiment_svc):
        self.db = db_client
        self.sentiment_svc = sentiment_svc

    async def process_feedback(self, feedback: Feedback, tenant_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Orchestrates: Validation → Feature Gate → Sentiment API → Storage

        Sentiment errors are swallowed intentionally — a failed analysis should
        never block persisting the customer's review.
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