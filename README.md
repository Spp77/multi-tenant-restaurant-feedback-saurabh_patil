# Multi-Tenant Restaurant Review API

A backend system that lets multiple restaurants share a single API while keeping their data completely isolated. Each tenant can submit customer feedback, and premium-tier tenants get automatic sentiment analysis applied to every review.

## Setup

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

## Running Tests

```bash
# From the saurabh_patil/ directory
$env:PYTHONPATH = "."; pytest tests/ -v --cov=src --cov-report=term-missing
```

## Running the API

```bash
uvicorn src.main:app --reload
# Swagger UI: http://127.0.0.1:8000/docs
```

## API Usage

### Submit Feedback

```bash
curl -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: pizza-palace-123" \
  -d '{"comment": "Amazing pizza!", "rating": 5, "tenant_id": "pizza-palace-123"}'
```

```json
{
  "status": "success",
  "feedback_id": "a1b2c3d4-...",
  "tenant_name": "Pizza Palace",
  "sentiment_applied": "positive"
}
```

### Get Insights

```bash
curl http://localhost:8000/api/restaurants/pizza-palace-123/insights \
  -H "x-tenant-id: pizza-palace-123"
```

```json
{
  "tenant_id": "pizza-palace-123",
  "restaurant_name": "Pizza Palace",
  "total_feedback": 42,
  "average_rating": 4.2,
  "sentiment_breakdown": {"positive": 30, "negative": 5, "neutral": 7},
  "average_sentiment_score": 0.61,
  "top_complaints": ["cold", "slow", "wrong"]
}
```

### Python Usage

```python
import asyncio
from src.api.feedback_handler import FeedbackHandler
from src.storage.dynamodb_client import DynamoDBClient
from src.external.sentiment_service import SentimentService
from src.models.feedback import Feedback

handler = FeedbackHandler(DynamoDBClient(), SentimentService())
fb = Feedback(comment="Amazing pizza!", rating=5, tenant_id="pizza-palace-123")

result = asyncio.run(handler.process_feedback(fb, {
    "tenant_id": "pizza-palace-123",
    "restaurant_name": "Pizza Palace",
    "features": {"sentiment_analysis": True},
}))
print(result)
```

## Project Structure

```
saurabh_patil/
├── src/
│   ├── api/
│   │   └── feedback_handler.py      # Orchestration: validation → gate → sentiment → storage
│   ├── external/
│   │   └── sentiment_service.py     # Mock sentiment API with chaos monkey
│   ├── models/
│   │   ├── feedback.py              # Pydantic feedback model
│   │   └── tenant.py                # Tenant model with feature flags
│   ├── storage/
│   │   ├── dynamodb_client.py       # In-memory DynamoDB simulation (PK/SK isolation)
│   │   └── s3_client.py             # In-memory S3 simulation
│   ├── utils/
│   │   ├── exceptions.py            # Custom exception hierarchy with HTTP status codes
│   │   └── logger.py                # Structured JSON logger (CloudWatch-compatible)
│   └── main.py                      # FastAPI app, routes, tenant registry
├── tests/
│   ├── fixtures/sample_data.json
│   ├── test_dynamodb_client.py
│   ├── test_feedback_flow.py
│   ├── test_feedback_handler.py
│   ├── test_logger.py
│   ├── test_main.py
│   ├── test_s3_client.py
│   └── test_sentiment_service.py
└── config/
    └── tenant_registry.json         # Tenant plan & feature configuration
```

## Architecture Decisions

### Why keyword-based sentiment over a real ML model?
The external API is mocked to keep the exercise self-contained and deterministic. The `SentimentService` interface is identical to what you'd wire up against a real provider (AWS Comprehend, Google NLP) — only the implementation changes.

### How does tenant isolation work?
DynamoDB is modelled as `{ tenant_id → { feedback_id → record } }`, mirroring how a real DynamoDB table uses a Partition Key. Every read and write is scoped to the tenant's partition. A tenant can never reach another tenant's `feedback_id` because the query always starts from their own partition.

### Why swallow sentiment errors instead of returning 500?
Network failures in an enrichment step shouldn't make the write fail. The review is the primary data — sentiment is additive. Records written during an outage get `sentiment_label = "analysis_skipped"` and can be back-filled later.

### Why return error dicts from `process_feedback` instead of raising?
The handler is HTTP-agnostic by design. It returns plain dicts so the same logic can be called from the FastAPI route, a CLI tool, or a Celery task without catching HTTP exceptions. The route layer translates dicts to `HTTPException` as needed.

### Trade-offs
| Decision | What we gained | What we gave up |
|---|---|---|
| In-memory storage | No AWS credentials needed, instant tests | Data lost on restart, no persistence |
| Keyword sentiment | Fully deterministic tests | Not representative of real NLP accuracy |
| Sync tenant registry load | Simple startup | Hot-reloading tenants requires restart |

## Tenant Plans

| Feature | Basic | Premium |
|---|---|---|
| Submit feedback | ✅ | ✅ |
| Sentiment analysis | ❌ | ✅ |
| Advanced insights | ❌ | ✅ |

Registered tenants: `pizza-palace-123` (premium), `burger-barn-456` (basic), `sushi-spot-789` (premium).
