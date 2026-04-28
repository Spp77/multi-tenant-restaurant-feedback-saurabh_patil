"""
src/models/responses.py

Explicit Pydantic response schemas for every API endpoint.

Why bother?
-----------
1. **Self-documenting Swagger** — FastAPI's /docs shows the frontend exactly
   what fields to expect, including optional fields and their types.
2. **Serialisation guarantee** — Pydantic validates *outgoing* data too, so a
   bug that accidentally adds unexpected keys never leaks to callers.
3. **Contract stability** — if a response field is renamed internally, the
   schema enforces the change at the boundary rather than silently drifting.
"""
from typing import Optional
from pydantic import BaseModel, Field


# ── POST /api/feedback ─────────────────────────────────────────────────────────

class FeedbackResponse(BaseModel):
    """
    Returned by ``POST /api/feedback`` on success (HTTP 201).

    Fields
    ------
    status
        Always ``"success"`` — presence of this field (vs an ``error`` key)
        is a quick client-side success check.
    feedback_id
        UUID generated at submission time — use this to reference the record.
    tenant_name
        Human-readable restaurant name for the authenticated tenant.
    sentiment_applied
        Sentiment label assigned by the analysis service (``"positive"``,
        ``"negative"``, ``"neutral"``), ``"analysis_skipped"`` if the service
        was unavailable, or ``None`` if the tenant's plan excludes sentiment.
    submissions_today
        Running count of this tenant's submissions for the current UTC day.
        Useful for clients to display a quota indicator.
    """

    status:            str           = Field(...)
    feedback_id:       str           = Field(...)
    tenant_name:       str           = Field(...)
    sentiment_applied: Optional[str] = Field(None)
    submissions_today: Optional[int] = Field(None)

    model_config = {"json_schema_extra": {"example": {
        "status":            "success",
        "feedback_id":       "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        "tenant_name":       "Pizza Palace",
        "sentiment_applied": "positive",
        "submissions_today": 42,
    }}}


# ── GET /api/restaurants/{tenant_id}/insights ──────────────────────────────────

class SentimentBreakdown(BaseModel):
    """Counts of reviews by sentiment label."""
    positive: int = Field(..., ge=0)
    negative: int = Field(..., ge=0)
    neutral:  int = Field(..., ge=0)

    model_config = {"json_schema_extra": {"example": {
        "positive": 23, "negative": 5, "neutral": 12,
    }}}


class InsightsResponse(BaseModel):
    """
    Returned by ``GET /api/restaurants/{tenant_id}/insights`` (HTTP 200).

    Fields
    ------
    tenant_id
        Stable machine identifier for the restaurant.
    restaurant_name
        Human-readable name.
    total_feedback
        Total submissions stored for this tenant.
    average_rating
        Mean star rating (1-5), or ``None`` if no feedback yet.
    sentiment_breakdown
        Counts of positive / negative / neutral reviews.
    average_sentiment_score
        Mean score in [-1.0, 1.0], or ``None`` if no analysed reviews.
    top_complaints
        Up to 5 most frequent words from low-rated (≤2 ★) reviews,
        after filtering common stop-words.
    """

    tenant_id:               str             = Field(...)
    restaurant_name:         str             = Field(...)
    total_feedback:          int             = Field(..., ge=0)
    average_rating:          Optional[float] = Field(None)
    sentiment_breakdown:     SentimentBreakdown
    average_sentiment_score: Optional[float] = Field(None)
    top_complaints:          list[str]       = Field(...)

    model_config = {"json_schema_extra": {"example": {
        "tenant_id":               "pizza-palace-123",
        "restaurant_name":         "Pizza Palace",
        "total_feedback":          40,
        "average_rating":          3.8,
        "sentiment_breakdown":     {"positive": 23, "negative": 5, "neutral": 12},
        "average_sentiment_score": 0.412,
        "top_complaints":          ["cold", "slow", "burnt"],
    }}}


# ── GET / and GET /health ──────────────────────────────────────────────────────

class RootResponse(BaseModel):
    """
    Returned by ``GET /`` — the API discovery / liveness endpoint.

    SREs and load-balancer health checks hit this first.
    """
    api_name:    str = Field(...)
    version:     str = Field(...)
    health:      str = Field(...)
    docs_url:    str = Field(...)
    openapi_url: str = Field(...)

    model_config = {"json_schema_extra": {"example": {
        "api_name":    "Multi-Tenant Restaurant Review API",
        "version":     "1.0.0",
        "health":      "ok",
        "docs_url":    "/docs",
        "openapi_url": "/openapi.json",
    }}}


class HealthResponse(BaseModel):
    """Returned by ``GET /health`` — minimal liveness check."""
    status:  str = Field(...)
    version: str = Field(...)

    model_config = {"json_schema_extra": {"example": {
        "status":  "online",
        "version": "1.0.0",
    }}}

