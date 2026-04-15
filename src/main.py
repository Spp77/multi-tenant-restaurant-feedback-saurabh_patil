import json
import os
from collections import Counter
from fastapi import FastAPI, Header, HTTPException, Depends

from src.models.feedback import Feedback
from src.models.tenant import Tenant
from src.api.feedback_handler import FeedbackHandler
from src.storage.dynamodb_client import DynamoDBClient
from src.storage.s3_client import S3Client
from src.external.sentiment_service import SentimentService
from src.utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="Multi-Tenant Restaurant Review API",
    description="Collect and analyse customer feedback per restaurant tenant.",
    version="1.0.0",
)

db_client = DynamoDBClient()
s3_client = S3Client()
sentiment_svc = SentimentService()
handler = FeedbackHandler(db_client, sentiment_svc)

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "tenant_registry.json")


def load_tenants() -> dict:
    with open(REGISTRY_PATH) as f:
        data = json.load(f)
    return {t["tenant_id"]: Tenant.from_dict(t) for t in data["tenants"]}


TENANT_DB: dict[str, Tenant] = load_tenants()


def get_current_tenant(x_tenant_id: str = Header(...)) -> Tenant:
    tenant = TENANT_DB.get(x_tenant_id)
    if not tenant:
        logger.warning(f"Access attempt from unknown tenant: {x_tenant_id}")
        raise HTTPException(status_code=401, detail="Invalid Tenant ID")
    return tenant


@app.post("/api/feedback", status_code=201)
async def create_feedback(
    feedback: Feedback,
    tenant: Tenant = Depends(get_current_tenant),
):
    tenant_data = tenant.model_dump()
    tenant_data["features"] = tenant.features.model_dump()

    result = await handler.process_feedback(feedback, tenant_data)

    if "error" in result:
        raise HTTPException(status_code=result.get("code", 500), detail=result["error"])
    return result


@app.get("/api/restaurants/{tenant_id}/insights")
async def get_insights(
    tenant_id: str,
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Aggregated sentiment analytics for a tenant.

    Path param must match the authenticated tenant — prevents cross-tenant reads.
    """
    if tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to another tenant's data.")

    records = db_client.query_by_tenant(tenant_id)

    if not records:
        return {
            "tenant_id": tenant_id,
            "restaurant_name": tenant.restaurant_name,
            "total_feedback": 0,
            "average_rating": None,
            "sentiment_breakdown": {"positive": 0, "negative": 0, "neutral": 0},
            "average_sentiment_score": None,
            "top_complaints": [],
        }

    total = len(records)
    avg_rating = round(sum(r["rating"] for r in records) / total, 2)

    breakdown = {"positive": 0, "negative": 0, "neutral": 0}
    scores = []
    for r in records:
        label = r.get("sentiment_label")
        if label in breakdown:
            breakdown[label] += 1
        if (score := r.get("sentiment_score")) is not None:
            scores.append(score)

    avg_score = round(sum(scores) / len(scores), 4) if scores else None

    # Naive word-frequency over 1-2 star reviews — good enough for this tier
    stop = {"the", "was", "and", "this", "that", "with", "have", "for", "are"}
    negative_words = [
        w for r in records if r.get("rating", 5) <= 2
        for w in r.get("comment", "").lower().split()
        if len(w) > 4 and w not in stop
    ]
    top_complaints = [w for w, _ in Counter(negative_words).most_common(5)]

    logger.info("Insights generated", extra={"tenant_id": tenant_id, "total": total})

    return {
        "tenant_id": tenant_id,
        "restaurant_name": tenant.restaurant_name,
        "total_feedback": total,
        "average_rating": avg_rating,
        "sentiment_breakdown": breakdown,
        "average_sentiment_score": avg_score,
        "top_complaints": top_complaints,
    }


@app.get("/health")
def health():
    return {"status": "online", "version": app.version}