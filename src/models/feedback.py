import uuid
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone

class Feedback(BaseModel):
    feedback_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    customer_name: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)  # Validation for 1-5 stars
    comment: str
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self):
        return self.model_dump()