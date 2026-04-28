import json
import os
from collections import Counter
from fastapi import FastAPI, Header, HTTPException, Depends
from typing import Optional

from src.models.feedback import Feedback
from src.models.tenant import Tenant
from src.models.responses import (
    FeedbackResponse,
    InsightsResponse,
    SentimentBreakdown,
    RootResponse,
    HealthResponse,
)
from src.api.feedback_handler import FeedbackHandler
from src.storage.dynamodb_client import DynamoDBClient
from src.storage.s3_client import S3Client
from src.external.sentiment_service import SentimentService
from src.utils.logger import get_logger
from src.utils.cache import tenant_cache
from src.utils.rate_limiter import RateLimiter

logger = get_logger(__name__)

# Insights tuning constants
TOP_COMPLAINTS_LIMIT  = 5
MIN_WORD_LENGTH       = 4
NEGATIVE_RATING_FLOOR = 2   # reviews at or below this rating feed the complaints list
STOP_WORDS: frozenset = frozenset({
    "the", "was", "and", "this", "that", "with", "have", "for", "are"
})

REGISTRY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "tenant_registry.json"
)

app = FastAPI(
    title="Multi-Tenant Restaurant Review API",
    description=(
        "Collect and analyse customer feedback per restaurant tenant.\n\n"
        "**Authentication**: Pass your `X-Tenant-ID` header on every request.\n\n"
        "**Rate limit**: 100 feedback submissions per tenant per day (HTTP 429 on breach)."
    ),
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

db_client     = DynamoDBClient()
s3_client     = S3Client()
sentiment_svc = SentimentService()
handler       = FeedbackHandler(db_client, sentiment_svc)
rate_limiter  = RateLimiter(limit=100)


def _load_registry() -> dict:
    """Read the raw JSON registry from disk and return the parsed dict."""
    with open(REGISTRY_PATH) as f:
        return json.load(f)


@tenant_cache(ttl_seconds=60)
def load_tenant_by_api_key(api_key: str) -> Optional[Tenant]:
    """
    Look up a tenant by their API key with a 60-second in-memory cache.

    Uses the ``@tenant_cache`` decorator which:
    - Masks the API key in logs (``pk_pi***``) — never logs full credentials.
    - Emits ``ttl_remaining`` (seconds) on every cache hit for observability.
    - Skips caching ``None`` results so unknown keys always retry live.

    Returns
    -------
    Tenant | None
        The matching ``Tenant`` object, or ``None`` if the key is unknown.
    """
    data = _load_registry()
    for entry in data["tenants"]:
        if entry.get("api_key") == api_key:
            return Tenant.from_dict(entry)
    return None


def load_tenants() -> dict[str, Tenant]:
    """
    Load and index the full tenant registry from JSON config.

    Used at startup to build the ``TENANT_DB`` fast-lookup dict.
    Individual lookups thereafter go through :func:`load_tenant_by_api_key`
    which is cached for 60 seconds.
    """
    data = _load_registry()
    return {t["tenant_id"]: Tenant.from_dict(t) for t in data["tenants"]}


TENANT_DB: dict[str, Tenant] = load_tenants()


def get_current_tenant(x_tenant_id: str = Header(...)) -> Tenant:
    """FastAPI dependency — resolves and validates tenant from X-Tenant-ID header."""
    tenant = TENANT_DB.get(x_tenant_id)
    if not tenant:
        logger.warning(
            "Access attempt from unknown tenant",
            extra={"tenant_id": x_tenant_id, "event": "auth_failure"},
        )
        raise HTTPException(status_code=401, detail="Invalid Tenant ID")
    return tenant


def check_rate_limit(tenant: Tenant = Depends(get_current_tenant)) -> Tenant:
    """
    FastAPI dependency — enforces the per-tenant daily submission cap.

    Dependency chain:
        POST /api/feedback
            → check_rate_limit          (this function)
                → get_current_tenant    (resolves + validates tenant)

    On success:  passes the resolved Tenant through unchanged.
    On limit hit: logs a ``limit_exceeded`` security event and raises HTTP 429.
    """
    allowed, count = rate_limiter.check_and_increment(tenant.tenant_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error":   "rate_limit_exceeded",
                "message": f"Daily limit of {rate_limiter.limit} feedback submissions reached.",
                "tenant_id": tenant.tenant_id,
                "submissions_today": count,
            },
        )
    return tenant


@app.get("/", response_model=RootResponse, tags=["Meta"])
def root() -> RootResponse:
    """
    API discovery endpoint.

    Returns the API name, version, health status, and links to the
    interactive docs. This is the first thing an SRE or load-balancer
    health check should hit.
    """
    return RootResponse(
        api_name=app.title,
        version=app.version,
        health="ok",
        docs_url="/docs",
        openapi_url="/openapi.json",
    )


@app.post("/api/feedback", status_code=201, response_model=FeedbackResponse, tags=["Feedback"])
async def create_feedback(
    feedback: Feedback,
    tenant: Tenant = Depends(check_rate_limit),
) -> FeedbackResponse:
    """
    Submit customer feedback.

    Dependency chain before handler runs:
        1. get_current_tenant  — authenticate & resolve tenant
        2. check_rate_limit    — enforce 100 submissions/day cap (HTTP 429 on breach)

    Handler pipeline:
        Validation → Feature Gate → Sentiment → Storage
    """
    tenant_data = tenant.model_dump()
    tenant_data["features"] = tenant.features.model_dump()

    result = await handler.process_feedback(feedback, tenant_data)

    if "error" in result:
        raise HTTPException(status_code=result.get("code", 500), detail=result["error"])

    return FeedbackResponse(
        status=result["status"],
        feedback_id=result["feedback_id"],
        tenant_name=result["tenant_name"],
        sentiment_applied=result.get("sentiment_applied"),
        submissions_today=rate_limiter.current_count(tenant.tenant_id),
    )


@app.get(
    "/api/restaurants/{tenant_id}/insights",
    response_model=InsightsResponse,
    tags=["Insights"],
)
async def get_insights(
    tenant_id: str,
    tenant: Tenant = Depends(get_current_tenant),
) -> InsightsResponse:
    """
    Aggregated sentiment analytics for a tenant.

    Path param must match the authenticated tenant — prevents cross-tenant reads.
    """
    if tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to another tenant's data.")

    records = db_client.query_by_tenant(tenant_id)

    if not records:
        return InsightsResponse(
            tenant_id=tenant_id,
            restaurant_name=tenant.restaurant_name,
            total_feedback=0,
            average_rating=None,
            sentiment_breakdown=SentimentBreakdown(positive=0, negative=0, neutral=0),
            average_sentiment_score=None,
            top_complaints=[],
        )

    total      = len(records)
    avg_rating = round(sum(r["rating"] for r in records) / total, 2)

    pos = neg = neu = 0
    scores: list[float] = []
    for r in records:
        label = r.get("sentiment_label")
        if label == "positive":
            pos += 1
        elif label == "negative":
            neg += 1
        elif label == "neutral":
            neu += 1
        if (score := r.get("sentiment_score")) is not None:
            scores.append(score)

    avg_score = round(sum(scores) / len(scores), 4) if scores else None

    negative_words = [
        w for r in records if r.get("rating", 5) <= NEGATIVE_RATING_FLOOR
        for w in r.get("comment", "").lower().split()
        if len(w) > MIN_WORD_LENGTH and w not in STOP_WORDS
    ]
    top_complaints = [w for w, _ in Counter(negative_words).most_common(TOP_COMPLAINTS_LIMIT)]

    logger.info("Insights generated", extra={"tenant_id": tenant_id, "total": total})

    return InsightsResponse(
        tenant_id=tenant_id,
        restaurant_name=tenant.restaurant_name,
        total_feedback=total,
        average_rating=avg_rating,
        sentiment_breakdown=SentimentBreakdown(positive=pos, negative=neg, neutral=neu),
        average_sentiment_score=avg_score,
        top_complaints=top_complaints,
    )


@app.get("/health", response_model=HealthResponse, tags=["Meta"])
def health() -> HealthResponse:
    """Minimal liveness check — returns online status and API version."""
    return HealthResponse(status="online", version=app.version)