# Multi-Tenant Restaurant Review API

This is my submission for the Jivaha backend engineering exercise. It's a Python/FastAPI service that lets multiple restaurants collect customer feedback through a single API — each restaurant's data is completely isolated from the others.

The interesting part was designing the tenant isolation properly and making sure a failing sentiment analysis never breaks the core write path.

---

## What it does

Restaurants sign up as tenants. When a customer leaves a review, the API:
1. Figures out which restaurant the request belongs to (via `X-Tenant-ID` header)
2. Checks if that restaurant is on a premium plan (feature gating)
3. Runs sentiment analysis on the comment if they are
4. Saves everything and returns a response

Premium tenants get sentiment labels on their reviews. Basic tenants just get storage.

There's also a `GET /insights` endpoint that gives aggregated stats — average rating, sentiment breakdown, top complaint words from low-rated reviews.

---

## Getting started

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

pip install -r requirements.txt
```

Run the API:
```bash
uvicorn src.main:app --reload
```

Swagger docs auto-generate at `http://127.0.0.1:8000/docs` — easiest way to poke around.

---

## Running the tests

```bash
$env:PYTHONPATH = "."; pytest tests/ -v --cov=src --cov-report=term-missing
```

Should be 100+ tests, 85%+ coverage. Tests use mocks so nothing actually hits an external API.

---

## Quick API example

Submit a review:
```bash
curl -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: pizza-palace-123" \
  -d '{"comment": "Amazing pizza!", "rating": 5, "tenant_id": "pizza-palace-123"}'
```

Get insights:
```bash
curl http://localhost:8000/api/restaurants/pizza-palace-123/insights \
  -H "x-tenant-id: pizza-palace-123"
```

Three tenants are pre-configured in `config/tenant_registry.json`:
- `pizza-palace-123` — premium (sentiment enabled)
- `burger-barn-456` — basic (sentiment off)
- `sushi-spot-789` — premium

---

## Project structure

```
src/
├── api/feedback_handler.py     # core pipeline logic
├── external/sentiment_service.py
├── models/                     # Pydantic models
├── storage/                    # DynamoDB + S3 mocks
├── utils/                      # logger, custom exceptions
└── main.py                     # FastAPI app + routes

tests/                          # 100+ tests across all modules
config/tenant_registry.json     # tenant plan config
```

---

## Some decisions I made and why

**Tenant isolation via nested dict structure**
The mock DynamoDB uses `{ tenant_id → { feedback_id → record } }` — mirrors how a real DynamoDB table would use Partition Keys. This means a tenant query is always scoped to their partition and there's no way to accidentally leak data across tenants.

**Sentiment failures don't fail the request**
If the sentiment API goes down, I still want to save the review. The error gets swallowed, the record gets `sentiment_label = "analysis_skipped"`, and you could back-fill later. Seemed like the right call — the review is the important thing, not the label.

**FeedbackHandler returns dicts, not HTTP exceptions**
I wanted to keep the handler testable without spinning up a full HTTP server. It just returns `{"error": ..., "code": 400}` and the FastAPI route translates that into an actual HTTPException. Makes unit testing way cleaner.

**Custom exception hierarchy**
Instead of bare `ValueError` or `Exception`, every error type has its own class with an HTTP status code baked in. `StorageError` knows it's a 500, `TenantNotFoundError` knows it's a 401. Easier to handle consistently up the stack.

**In-memory storage**
It's a mock — obviously wouldn't ship this. But the `DynamoDBClient` and `S3Client` interfaces are the same as what you'd use with real boto3, so swapping them out later is just a config change.
