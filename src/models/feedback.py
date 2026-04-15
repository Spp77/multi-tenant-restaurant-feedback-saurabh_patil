import uuid
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class Feedback(BaseModel):
    """
    Immutable record of a single customer review.

    ``feedback_id`` and ``created_at`` are auto-generated at instantiation.
    ``sentiment_score`` and ``sentiment_label`` are populated by
    ``SentimentService`` after submission and remain ``None`` for basic-plan
    tenants or when sentiment analysis is unavailable.
    """

    feedback_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    customer_name: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)
    comment: str
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        """Return a plain dict suitable for storage or JSON serialisation."""
        return self.model_dump()