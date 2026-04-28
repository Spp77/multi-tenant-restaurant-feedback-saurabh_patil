#!/usr/bin/env bash
# =============================================================================
# scripts/test_api.sh
#
# Smoke-test every endpoint of the Multi-Tenant Restaurant Review API.
# Requires: curl, jq  (brew install jq  /  apt install jq)
#
# Usage:
#   chmod +x scripts/test_api.sh
#   BASE_URL=http://localhost:8000 bash scripts/test_api.sh
# =============================================================================

BASE_URL="${BASE_URL:-http://localhost:8000}"

# ANSI colours
GREEN='\033[0;32m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'

pass() { echo -e "${GREEN}✓ PASS${NC}  $1"; }
fail() { echo -e "${RED}✗ FAIL${NC}  $1"; }
section() { echo -e "\n${BLUE}── $1 ──${NC}"; }

# ─── 1. Root / Discovery ─────────────────────────────────────────────────────
section "GET / (discovery)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/")
BODY=$(curl -s "$BASE_URL/" | jq .)
echo "$BODY"
[ "$STATUS" = "200" ] && pass "GET / → 200 OK" || fail "GET / → $STATUS"

# ─── 2. Health ────────────────────────────────────────────────────────────────
section "GET /health"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
BODY=$(curl -s "$BASE_URL/health" | jq .)
echo "$BODY"
[ "$STATUS" = "200" ] && pass "GET /health → 200 OK" || fail "GET /health → $STATUS"

# ─── 3. Submit feedback — PREMIUM tenant (with sentiment) ────────────────────
section "POST /api/feedback (premium tenant — Pizza Palace)"
RESPONSE=$(curl -s -X POST "$BASE_URL/api/feedback" \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: pizza-palace-123" \
  -d '{
    "tenant_id": "pizza-palace-123",
    "rating": 5,
    "comment": "Amazing pizza, absolutely delicious!",
    "customer_name": "Alice"
  }')
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/feedback" \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: pizza-palace-123" \
  -d '{"tenant_id":"pizza-palace-123","rating":4,"comment":"Amazing pizza!"}')
echo "$RESPONSE" | jq .
[ "$STATUS" = "201" ] && pass "POST /api/feedback (premium) → 201 Created" \
                        || fail "POST /api/feedback (premium) → $STATUS"

# ─── 4. Submit feedback — BASIC tenant (no sentiment) ────────────────────────
section "POST /api/feedback (basic tenant — Burger Barn)"
RESPONSE=$(curl -s -X POST "$BASE_URL/api/feedback" \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: burger-barn-456" \
  -d '{
    "tenant_id": "burger-barn-456",
    "rating": 3,
    "comment": "okay burgers, nothing special",
    "customer_name": "Bob"
  }')
echo "$RESPONSE" | jq .
STATUS=$(echo "$RESPONSE" | jq -r '.status // "error"')
[ "$STATUS" = "success" ] && pass "POST /api/feedback (basic) returned success" \
                            || fail "POST /api/feedback (basic) returned: $STATUS"

# ─── 5. Submit feedback — Bad tenant (expect 401) ────────────────────────────
section "POST /api/feedback (invalid tenant → expect 401)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/feedback" \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: unknown-tenant-xyz" \
  -d '{"tenant_id":"unknown","rating":3,"comment":"test"}')
[ "$STATUS" = "401" ] && pass "Invalid tenant → 401 Unauthorized" \
                        || fail "Invalid tenant → $STATUS (expected 401)"

# ─── 6. Submit feedback — Empty comment (expect 400) ─────────────────────────
section "POST /api/feedback (empty comment → expect 400)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/feedback" \
  -H "Content-Type: application/json" \
  -H "x-tenant-id: pizza-palace-123" \
  -d '{"tenant_id":"pizza-palace-123","rating":3,"comment":"   "}')
[ "$STATUS" = "400" ] && pass "Empty comment → 400 Bad Request" \
                        || fail "Empty comment → $STATUS (expected 400)"

# ─── 7. Get insights ─────────────────────────────────────────────────────────
section "GET /api/restaurants/pizza-palace-123/insights"
RESPONSE=$(curl -s "$BASE_URL/api/restaurants/pizza-palace-123/insights" \
  -H "x-tenant-id: pizza-palace-123")
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/restaurants/pizza-palace-123/insights" \
  -H "x-tenant-id: pizza-palace-123")
echo "$RESPONSE" | jq .
[ "$STATUS" = "200" ] && pass "GET /insights → 200 OK" || fail "GET /insights → $STATUS"

# ─── 8. Cross-tenant read attempt (expect 403) ───────────────────────────────
section "GET /api/restaurants/pizza-palace-123/insights (burger-barn auth → expect 403)"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$BASE_URL/api/restaurants/pizza-palace-123/insights" \
  -H "x-tenant-id: burger-barn-456")
[ "$STATUS" = "403" ] && pass "Cross-tenant read → 403 Forbidden" \
                        || fail "Cross-tenant read → $STATUS (expected 403)"

echo -e "\n${BLUE}── Done ──${NC}\n"
