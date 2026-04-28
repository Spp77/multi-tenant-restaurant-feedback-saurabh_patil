# Multi-Tenant Restaurant Review API

[![CI](https://github.com/Spp77/multi-tenant-restaurant-feedback/actions/workflows/test.yml/badge.svg)](https://github.com/Spp77/multi-tenant-restaurant-feedback/actions/workflows/test.yml)

A production-grade, multi-tenant restaurant feedback API built with **FastAPI + Python 3.13 + Pydantic v2**. Each restaurant (tenant) is completely isolated — their data, rate limits, and feature flags never cross-contaminate.

---

## Architecture at a Glance

```
POST /api/feedback
  ↓
[Tenant Resolution]    X-Tenant-ID header → registry lookup (60s TTL cache, masked logs)
  ↓
[Rate Limit Gate]      100 submissions/tenant/day → HTTP 429 on breach
  ↓
[Feature Gate]         Premium plan only → sentiment analysis
  ↓
[External API Call]    SentimentService.analyze_text() → (label, score)
  ↓                    ← graceful degradation: failure = "analysis_skipped", never a 500
[Storage]              DynamoDB mock keyed {tenant_id → {feedback_id → record}}
  ↓
[Response]             FeedbackResponse(feedback_id, sentiment_applied, submissions_today)

GET /api/restaurants/{tenant_id}/insights
  ↓
[Cross-Tenant Guard]   Path param must match authenticated tenant (403 otherwise)
  ↓
[Data Retrieval]       query_by_tenant() → sorted by created_at DESC
  ↓
[Aggregation]          avg_rating, sentiment_breakdown, avg_score, top_complaints
  ↓
[Response]             InsightsResponse (typed Pydantic model)
```

---

## Key Engineering Decisions

### 1. Multi-Tenant Isolation

Data is stored as `{ tenant_id → { feedback_id → record } }` — mirroring DynamoDB's Partition Key / Sort Key model. Tenant A can never read Tenant B's data:

- **Write path**: `feedback.tenant_id` is overwritten from the auth header, not the request body — prevents spoofing.
- **Read path**: `GET /insights/{tenant_id}` cross-checks the path param against the authenticated tenant (returns **403** on mismatch).

### 2. Custom Exception Hierarchy

Instead of bare `raise Exception(...)`, every error type is a named class with an HTTP status code baked in. Clean, testable, and self-documenting:

```
RestaurantAPIError (base, 500)
├── TenantNotFoundError     → 401
├── FeatureNotEnabledError  → 403
├── ValidationError         → 400
│   └── EmptyCommentError
├── StorageError            → 500
└── SentimentServiceError   → 502
```

### 3. Performance-First Caching

Tenant registry lookups are cached for 60 seconds via a custom `@tenant_cache(ttl_seconds=60)` decorator (not `functools.lru_cache` — that has no TTL). Every cache event emits a structured log:

```json
{"event": "cache_miss", "api_key": "pk_pi***", "cache": "load_tenant_by_api_key"}
{"event": "cache_hit",  "api_key": "pk_pi***", "ttl_remaining": 47}
```

Note the **masked API key** (`pk_pi***`) — never log full credentials.

### 4. Tenant-Aware Rate Limiting

Enforced as a **FastAPI dependency** (`check_rate_limit`) — gates the request *before* the handler runs, saving CPU and making semantics explicit:

```
POST /api/feedback
  → check_rate_limit (HTTP 429 if > 100/day)
    → get_current_tenant (HTTP 401 if unknown)
```

Composite key: `rate_limit:{tenant_id}:{YYYY-MM-DD}` — counts reset automatically at midnight (no cron required).

### 5. Graceful Sentiment Degradation

The sentiment API has a 1% chaos-monkey failure rate (intentional). If it fires:
- The feedback is **still stored** (write path never blocked by enrichment)
- `sentiment_label` is set to `"analysis_skipped"` for later back-fill
- A `WARNING` log is emitted for alerting

### 6. Explicit Response Schemas

Every endpoint uses `response_model=` with a Pydantic model — not raw `dict`. This means:
- Swagger `/docs` shows the frontend **exactly** what to expect
- Outgoing data is validated (unexpected keys never leak)
- API contracts are enforced at the boundary, not assumed

### 7. Mock-to-Real Swap

Both `DynamoDBClient` and `S3Client` are in-memory mocks with **boto3-identical** API surfaces. Swapping to real AWS is a one-line config change — zero application code changes needed.

---

## Getting Started

```bash
# 1. Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1      # Windows PowerShell
# source venv/bin/activate       # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the server
uvicorn src.main:app --reload
```

Interactive Swagger docs: **http://127.0.0.1:8000/docs**
API discovery endpoint: **http://127.0.0.1:8000/**

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET`  | `/` | None | Discovery — name, version, health |
| `GET`  | `/health` | None | Liveness check |
| `POST` | `/api/feedback` | `X-Tenant-ID` | Submit feedback (rate-limited: 100/day) |
| `GET`  | `/api/restaurants/{tenant_id}/insights` | `X-Tenant-ID` | Aggregated analytics |

### Status Codes

| Code | Meaning |
|------|---------|
| 201 | Feedback accepted |
| 400 | Validation error (e.g. empty comment) |
| 401 | Unknown tenant ID |
| 403 | Cross-tenant access attempt |
| 422 | Malformed request body |
| 429 | Daily rate limit exceeded |
| 500 | Unexpected server error |

---

## Quick curl Examples

```bash
# Discovery
curl http://localhost:8000/

# Submit feedback (premium tenant — sentiment enabled)
curl -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: pizza-palace-123" \
  -d '{"tenant_id": "pizza-palace-123", "rating": 5, "comment": "Amazing pizza, absolutely delicious!"}'

# Submit feedback (basic tenant — no sentiment)
curl -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: burger-barn-456" \
  -d '{"tenant_id": "burger-barn-456", "rating": 3, "comment": "okay burgers"}'

# Get insights
curl http://localhost:8000/api/restaurants/pizza-palace-123/insights \
  -H "x-tenant-id: pizza-palace-123"

# Attempt cross-tenant read (expect 403)
curl http://localhost:8000/api/restaurants/pizza-palace-123/insights \
  -H "x-tenant-id: burger-barn-456"
```

Full smoke-test scripts: `scripts/test_api.sh` (bash) and `scripts/test_api.ps1` (PowerShell).

---

## Pre-Configured Tenants

| Tenant ID | Restaurant | Plan | Sentiment | Insights |
|-----------|-----------|------|-----------|---------|
| `pizza-palace-123` | Pizza Palace | Premium | ✅ | ✅ |
| `burger-barn-456` | Burger Barn | Basic | ❌ | ❌ |
| `sushi-spot-789` | Sushi Spot | Premium | ✅ | ❌ |

---

## Running Tests

```bash
# Run all tests with coverage
$env:PYTHONPATH = "."; pytest tests/ -v --cov=src --cov-report=term-missing

# Run a specific module
pytest tests/test_rate_limiter.py -v
```

**149 tests** across 8 modules. All mocked — no external services required.

> **Note on `test_mixed_case_okay`**: This test is marked `@pytest.mark.flaky(reruns=2)`. It can occasionally fail because the `SentimentService` has an intentional **1% chaos-monkey failure rate** (`CHAOS_RATE = 0.01`) to simulate real-world infrastructure instability and validate the graceful-degradation path. This is by design — a Principal Engineer acknowledges intentional chaos rather than ignoring it.

### Test Coverage by Module

| Module | Tests | What's covered |
|--------|-------|----------------|
| `test_main.py` | 15 | Route integration, auth, status codes |
| `test_feedback_handler.py` | — | Pipeline unit tests |
| `test_rate_limiter.py` | 22 | Logic, keys, daily reset, 429 response |
| `test_cache.py` | 18 | TTL hit/miss/expiry, masked API key logs |
| `test_dynamodb_client.py` | — | Storage layer isolation |
| `test_s3_client.py` | 17 | S3 mock CRUD + multi-bucket |
| `test_sentiment_service.py` | 12 | All keyword branches + chaos path |
| `test_logger.py` | — | JSON formatter output |

---

## Project Structure

```
saurabh_patil/
├── config/
│   └── tenant_registry.json       # Tenant plan config (3 restaurants)
├── src/
│   ├── main.py                    # FastAPI app + routes + dependencies
│   ├── api/
│   │   └── feedback_handler.py    # HTTP-agnostic pipeline orchestrator
│   ├── models/
│   │   ├── feedback.py            # Feedback Pydantic model
│   │   ├── tenant.py              # Tenant + TenantFeatures models
│   │   └── responses.py           # Typed response schemas (Swagger-friendly)
│   ├── storage/
│   │   ├── dynamodb_client.py     # In-memory DynamoDB (boto3-compatible API)
│   │   └── s3_client.py           # In-memory S3 (boto3-compatible API)
│   ├── external/
│   │   └── sentiment_service.py   # Mock sentiment analyzer (chaos-monkey enabled)
│   └── utils/
│       ├── cache.py               # @cache + @tenant_cache TTL decorators
│       ├── rate_limiter.py        # Tenant-aware daily rate limiter
│       ├── exceptions.py          # Custom exception hierarchy
│       └── logger.py              # Structured JSON logger (CloudWatch-ready)
├── tests/                         # 149 tests, all mocked
├── scripts/
│   ├── test_api.sh                # Bash smoke tests (curl + jq)
│   └── test_api.ps1               # PowerShell smoke tests
├── .github/workflows/test.yml     # CI: lint → test → coverage upload
└── requirements.txt
```

---

## CI/CD

GitHub Actions pipeline (`.github/workflows/test.yml`):

1. **Lint** — Ruff runs first. If code style fails, tests don't run (fast feedback).
2. **Test** — Full pytest suite with `--cov=src` and XML coverage report.
3. **Coverage** — Uploaded to Codecov on every push/PR.

The `lint` job must pass before the `test` job starts (`needs: lint`) — ensuring no CPU cycles are wasted running tests against unreviewed code.
