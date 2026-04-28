# 🍕 Multi-Tenant Restaurant Review API

<div align="center">

[![CI](https://github.com/Spp77/multi-tenant-restaurant-feedback-saurabh_patil/actions/workflows/test.yml/badge.svg)](https://github.com/Spp77/multi-tenant-restaurant-feedback-saurabh_patil/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/tests-149%20passed-brightgreen)](./tests)
[![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)](./tests)
[![Ruff](https://img.shields.io/badge/linter-ruff-orange)](https://docs.astral.sh/ruff)

</div>

> A production-grade, multi-tenant restaurant feedback API built with **FastAPI + Python 3.13 + Pydantic v2**.
> Each restaurant (tenant) is completely isolated — their data, rate limits, and feature flags **never cross-contaminate**.

---

## Table of Contents

- [Architecture](#architecture)
- [Key Engineering Decisions](#key-engineering-decisions)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Sample Responses](#sample-responses)
- [Pre-Configured Tenants](#pre-configured-tenants)
- [Running Tests](#running-tests)
- [Project Structure](#project-structure)
- [CI/CD Pipeline](#cicd-pipeline)

---

## Architecture

### `POST /api/feedback` Flow

```
Request (X-Tenant-ID header)
  │
  ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Dependency Chain                                        │
│                                                                  │
│  get_current_tenant()  ──► registry lookup                      │
│    └─ 60s TTL cache       api_key masked in logs: "pk_pi***"    │
│    └─ HTTP 401 on miss                                           │
│                                                                  │
│  check_rate_limit()    ──► composite key: rate_limit:{id}:{date}│
│    └─ 100 req/day/tenant                                         │
│    └─ HTTP 429 on breach + security log                          │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  FeedbackHandler.process_feedback()                              │
│                                                                  │
│  [Feature Gate]   tenant.features.sentiment_analysis?           │
│       YES ──► SentimentService.analyze_text(comment)            │
│               └─ 1% chaos-monkey: failure → "analysis_skipped"  │
│               └─ review always saved regardless                  │
│       NO  ──► skip (basic plan)                                  │
│                                                                  │
│  [Storage]  DynamoDB.put_item(tenant_id, feedback_id, record)   │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
         FeedbackResponse (HTTP 201)
         { feedback_id, sentiment_applied, submissions_today }
```

### `GET /api/restaurants/{tenant_id}/insights` Flow

```
Request (X-Tenant-ID header)
  │
  ▼
get_current_tenant() ──► HTTP 401 on miss
  │
  ▼
Cross-tenant guard ──► path param must match auth header (HTTP 403 on mismatch)
  │
  ▼
DynamoDB.query_by_tenant(tenant_id)
  │
  ▼
Aggregation: avg_rating · sentiment_breakdown · top_complaints (word-freq on low-rated)
  │
  ▼
InsightsResponse (HTTP 200)
```

---

## Key Engineering Decisions

### 1. Multi-Tenant Data Isolation

Storage layout mirrors **DynamoDB Partition Key / Sort Key** semantics:

```
{ tenant_id → { feedback_id → record } }
```

Two isolation guarantees:
- **Write path** — `feedback.tenant_id` is stamped from the auth header, never the request body. Prevents spoofing.
- **Read path** — `GET /insights/{tenant_id}` cross-checks path param vs authenticated tenant → **HTTP 403** on mismatch.

### 2. Custom Exception Hierarchy

Every error is a named class with its HTTP status baked in — no bare `raise Exception()` anywhere:

```
RestaurantAPIError (base → 500)
├── TenantNotFoundError     → 401
├── FeatureNotEnabledError  → 403
├── ValidationError         → 400
│   └── EmptyCommentError
├── StorageError            → 500
└── SentimentServiceError   → 502
```

This makes the FastAPI route layer a thin translator — it just maps exception types to HTTP responses.

### 3. Performance-First Caching

Built a custom `@tenant_cache(ttl_seconds=60)` decorator instead of `functools.lru_cache` (which has no TTL). Two security properties enforced in every log line:

```json
{"event": "cache_miss", "api_key": "pk_pi***", "cache": "load_tenant_by_api_key"}
{"event": "cache_hit",  "api_key": "pk_pi***", "ttl_remaining": 47}
```

- **Masked API key** — `pk_pi***` (first 5 chars only) — credentials never reach the log sink
- **TTL remaining** — visible on every hit, enabling cache efficiency dashboards

### 4. Tenant-Aware Rate Limiting (FastAPI Dependency)

Enforced as a dependency, not inside the handler — request is rejected **before** any DB or sentiment work starts:

```
POST /api/feedback
  └─► check_rate_limit()     ← HTTP 429 + security log if > 100/day
        └─► get_current_tenant()  ← HTTP 401 if unknown
```

Composite date key means counts reset automatically at midnight — **no cron job, no TTL management**:
```
rate_limit:pizza-palace-123:2026-04-28  →  count: 47
```

### 5. Graceful Sentiment Degradation

`SentimentService` has an intentional **1% chaos-monkey** (`CHAOS_RATE = 0.01`) to simulate real downstream instability. The contract:

| Scenario | Outcome |
|----------|---------|
| Sentiment succeeds | `sentiment_label = "positive"/"negative"/"neutral"` |
| Sentiment fails (any exception) | `sentiment_label = "analysis_skipped"`, record **still saved** |
| Tenant on basic plan | `sentiment_label = None` (feature gate, not a failure) |

The write path is **never blocked** by enrichment failures.

### 6. Explicit Response Schemas

Every endpoint declares `response_model=` — not raw `dict`. Benefits:

- Swagger `/docs` tells the frontend exactly what to expect (no guessing)
- Pydantic validates outgoing data — unexpected keys can't leak
- Contracts enforced at the HTTP boundary, not assumed

### 7. Mock-to-Real Swap Path

`DynamoDBClient` and `S3Client` are in-memory mocks with **boto3-identical method signatures**. Going to production is a single dependency injection change — zero application code changes.

---

## Getting Started

> **Reviewer note:** this submission lives inside the `saurabh_patil/` subfolder of the shared fork. All commands below assume you have `cd`'d into that folder.

### Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.11 + | `python --version` |
| pip | latest | `pip --version` |
| git | any | `git --version` |

No AWS account, no API keys, no Docker — the entire stack runs on mocked in-memory services.

---

### 1 — Clone & navigate

```bash
git clone https://github.com/Spp77/multi-tenant-restaurant-feedback-saurabh_patil.git
cd multi-tenant-restaurant-feedback-saurabh_patil
```

---

### 2 — Create a virtual environment

```bash
# Create
python -m venv venv

# Activate — pick your shell:
.\venv\Scripts\Activate.ps1          # Windows PowerShell  ← recommended
.\venv\Scripts\activate.bat          # Windows CMD
source venv/bin/activate             # Mac / Linux / Git Bash
```

Your prompt will show `(venv)` when active.

---

### 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `fastapi` + `uvicorn` — web framework and ASGI server
- `pydantic v2` — data validation
- `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-rerunfailures` — test stack
- `httpx` — async HTTP client used by FastAPI's TestClient
- `ruff` — linter (same tool used in CI)

---

### 4 — Run the test suite

```bash
# Windows PowerShell
$env:PYTHONPATH = "."; pytest tests/ -v --cov=src --cov-report=term-missing

# Mac / Linux / Git Bash
PYTHONPATH=. pytest tests/ -v --cov=src --cov-report=term-missing
```

Expected output:

```
149 passed in ~1.5s
TOTAL  96% coverage
```

> **Why `PYTHONPATH=.`?** Python needs to find `src.*` imports from the project root. The CI pipeline sets this automatically via `env: PYTHONPATH: .`.

---

### 5 — Start the development server

```bash
uvicorn src.main:app --reload
```

| URL | What you get |
|-----|-------------|
| `http://127.0.0.1:8000/` | API discovery — name, version, links |
| `http://127.0.0.1:8000/docs` | Interactive Swagger UI (try endpoints live) |
| `http://127.0.0.1:8000/redoc` | ReDoc API reference |
| `http://127.0.0.1:8000/health` | Liveness check |

---

### 6 — Smoke-test the live server

**PowerShell (Windows):**
```powershell
.\scripts\test_api.ps1
```

**Bash (Mac/Linux/Git Bash):**
```bash
bash scripts/test_api.sh
```

Both scripts hit every endpoint and print colour-coded ✓ PASS / ✗ FAIL output.

Or use curl directly:

```bash
# Submit feedback (premium tenant)
curl -s -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: pizza-palace-123" \
  -d '{"tenant_id":"pizza-palace-123","rating":5,"comment":"Amazing pizza!"}' \
  | python -m json.tool

# Get insights
curl -s http://localhost:8000/api/restaurants/pizza-palace-123/insights \
  -H "x-tenant-id: pizza-palace-123" \
  | python -m json.tool
```

---

### 7 — Run the linter (same check as CI)

```bash
ruff check src/ tests/
# Expected: All checks passed!
```

---

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'src'` | Set `PYTHONPATH=.` before pytest |
| `command not found: uvicorn` | Run `pip install -r requirements.txt` inside venv |
| `(venv)` not showing in prompt | Activate the venv — see Step 2 |
| Port 8000 already in use | `uvicorn src.main:app --reload --port 8001` |
| `test_mixed_case_okay` occasionally fails | Expected — it's a 1% chaos-monkey simulation, marked `@pytest.mark.flaky(reruns=2)` |

---

Interactive Swagger docs: **http://127.0.0.1:8000/docs**
API discovery endpoint: **http://127.0.0.1:8000/**

---

## API Reference

| Method | Endpoint | Auth | Rate Limited | Description |
|--------|----------|------|:---:|-------------|
| `GET` | `/` | — | — | API discovery |
| `GET` | `/health` | — | — | Liveness check |
| `POST` | `/api/feedback` | `X-Tenant-ID` | ✅ 100/day | Submit feedback |
| `GET` | `/api/restaurants/{tenant_id}/insights` | `X-Tenant-ID` | — | Aggregated analytics |

### HTTP Status Codes

| Code | Trigger |
|------|---------|
| `201` | Feedback accepted |
| `400` | Validation error (empty/whitespace comment) |
| `401` | Unknown or missing `X-Tenant-ID` header |
| `403` | Cross-tenant read attempt |
| `422` | Malformed JSON body (Pydantic validation) |
| `429` | Daily rate limit exceeded (100 submissions/tenant/day) |
| `500` | Unexpected server error |

---

## Sample Responses

### `POST /api/feedback` → `201 Created`

```json
{
  "status": "success",
  "feedback_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "tenant_name": "Pizza Palace",
  "sentiment_applied": "positive",
  "submissions_today": 3
}
```

### `GET /api/restaurants/{tenant_id}/insights` → `200 OK`

```json
{
  "tenant_id": "pizza-palace-123",
  "restaurant_name": "Pizza Palace",
  "total_feedback": 40,
  "average_rating": 3.8,
  "sentiment_breakdown": {
    "positive": 23,
    "negative": 5,
    "neutral": 12
  },
  "average_sentiment_score": 0.412,
  "top_complaints": ["cold", "slow", "burnt", "wait", "rude"]
}
```

### `POST /api/feedback` → `429 Too Many Requests`

```json
{
  "detail": {
    "error": "rate_limit_exceeded",
    "message": "Daily limit of 100 feedback submissions reached.",
    "tenant_id": "pizza-palace-123",
    "submissions_today": 100
  }
}
```

---

## Quick curl Examples

```bash
# API discovery
curl http://localhost:8000/

# Submit feedback — premium tenant (sentiment enabled)
curl -s -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: pizza-palace-123" \
  -d '{"tenant_id": "pizza-palace-123", "rating": 5, "comment": "Amazing pizza, absolutely delicious!"}' \
  | jq .

# Submit feedback — basic tenant (no sentiment)
curl -s -X POST http://localhost:8000/api/feedback \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: burger-barn-456" \
  -d '{"tenant_id": "burger-barn-456", "rating": 3, "comment": "okay burgers"}' \
  | jq .

# Get insights
curl -s http://localhost:8000/api/restaurants/pizza-palace-123/insights \
  -H "x-tenant-id: pizza-palace-123" | jq .

# Cross-tenant read — expect 403
curl -s http://localhost:8000/api/restaurants/pizza-palace-123/insights \
  -H "x-tenant-id: burger-barn-456" | jq .
```

> **Windows users**: run `.\scripts\test_api.ps1` for the same tests in PowerShell with colour-coded pass/fail output.
> **Mac/Linux users**: run `bash scripts/test_api.sh` (requires `curl` + `jq`).

---

## Pre-Configured Tenants

| Tenant ID | Restaurant | Plan | Sentiment Analysis | Advanced Insights |
|-----------|-----------|------|:---:|:---:|
| `pizza-palace-123` | Pizza Palace | Premium | ✅ | ✅ |
| `burger-barn-456` | Burger Barn | Basic | ❌ | ❌ |
| `sushi-spot-789` | Sushi Spot | Premium | ✅ | ✅ |

Tenant config lives in `config/tenant_registry.json` — outside `src/` by design (config ≠ logic).

---

## Running Tests

```bash
# Full suite with coverage report
$env:PYTHONPATH = "."; pytest tests/ -v --cov=src --cov-report=term-missing

# Single module
pytest tests/test_rate_limiter.py -v

# Lint check (same as CI)
ruff check src/ tests/
```

**149 tests** across 8 modules — all mocked, no external services required.

### Coverage Summary (96% total)

| Module | Cover | Highlights |
|--------|:---:|-----------|
| `feedback_handler.py` | **100%** | All pipeline branches including graceful failure |
| `sentiment_service.py` | **100%** | All keyword branches + chaos-monkey path |
| `rate_limiter.py` | **100%** | Logic, composite keys, daily reset, 429 response |
| `responses.py` | **100%** | All Pydantic response schemas |
| `dynamodb_client.py` | **100%** | Tenant-isolated CRUD |
| `logger.py` | **100%** | JSON formatter, field masking |
| `main.py` | 98% | 2 unreachable error-path branches |
| `cache.py` | 99% | TTL hit/miss/expiry, masked key logs |
| `exceptions.py` | 91% | `to_dict()` helper methods |
| `s3_client.py` | 89% | Error-handling branches |

> **Note on `test_mixed_case_okay`**: Marked `@pytest.mark.flaky(reruns=2)`. The `SentimentService` has an intentional **1% chaos-monkey** (`CHAOS_RATE = 0.01`) to simulate real-world service instability. The marker is the professional acknowledgement — not a band-aid. See decision #5 above.

---

## Project Structure

```
saurabh_patil/
├── config/
│   └── tenant_registry.json        # Tenant plan config (3 restaurants)
│
├── src/
│   ├── main.py                     # FastAPI app, routes, dependency chain
│   ├── api/
│   │   └── feedback_handler.py     # HTTP-agnostic business logic
│   ├── models/
│   │   ├── feedback.py             # Feedback request model (Pydantic)
│   │   ├── tenant.py               # Tenant + TenantFeatures models
│   │   └── responses.py            # Typed response schemas (all endpoints)
│   ├── storage/
│   │   ├── dynamodb_client.py      # In-memory DynamoDB (boto3-compatible)
│   │   └── s3_client.py            # In-memory S3 (boto3-compatible)
│   ├── external/
│   │   └── sentiment_service.py    # Mock NLP (chaos-monkey enabled)
│   └── utils/
│       ├── cache.py                # @cache + @tenant_cache TTL decorators
│       ├── rate_limiter.py         # Tenant-aware daily rate limiter
│       ├── exceptions.py           # Custom exception hierarchy
│       └── logger.py              # Structured JSON logger (CloudWatch-ready)
│
├── tests/                          # 149 tests, all mocked
│   ├── test_main.py
│   ├── test_feedback_handler.py
│   ├── test_rate_limiter.py
│   ├── test_cache.py
│   ├── test_dynamodb_client.py
│   ├── test_s3_client.py
│   ├── test_sentiment_service.py
│   └── test_logger.py
│
├── scripts/
│   ├── test_api.sh                 # Bash smoke tests (curl + jq)
│   └── test_api.ps1                # PowerShell smoke tests
│
├── .github/workflows/test.yml      # CI: lint → test → Codecov upload
├── requirements.txt
└── .gitignore
```

---

## CI/CD Pipeline

`.github/workflows/test.yml` — two jobs, sequential by design:

```
push / PR to main
  │
  ▼
Job 1: Lint (Ruff)         ← fails fast if code style is broken
  │  needs: pass
  ▼
Job 2: Test + Coverage     ← full pytest suite, --cov=src
  │
  ▼
Codecov upload             ← coverage.xml → badge + PR annotation
```

**Key decisions:**
- `defaults.run.working-directory: saurabh_patil` — handles the shared mono-repo structure correctly
- `needs: lint` — no CPU wasted running 149 tests against unreviewed code
- `cache: 'pip'` — subsequent runs are significantly faster
- `fail_ci_if_error: false` on Codecov — a badge service outage never blocks a merge

---

<div align="center">
  <sub>Built by Saurabh Patil · Jivaha Backend Engineering Exercise · 2026 · <a href="https://github.com/Spp77/multi-tenant-restaurant-feedback-saurabh_patil">github.com/Spp77/multi-tenant-restaurant-feedback-saurabh_patil</a></sub>
</div>
