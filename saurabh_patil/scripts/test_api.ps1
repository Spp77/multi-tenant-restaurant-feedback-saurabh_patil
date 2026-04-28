# scripts/test_api.ps1
# PowerShell smoke-test for the Multi-Tenant Restaurant Review API.
# Usage:  .\scripts\test_api.ps1  (with the server running on localhost:8000)

$BASE_URL = $env:BASE_URL ?? "http://localhost:8000"

function Pass($msg) { Write-Host "✓ PASS  $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "✗ FAIL  $msg" -ForegroundColor Red   }
function Section($msg) { Write-Host "`n── $msg ──" -ForegroundColor Cyan }

# ── 1. Root ────────────────────────────────────────────────────────────────────
Section "GET / (discovery)"
$r = Invoke-WebRequest "$BASE_URL/" -UseBasicParsing -ErrorAction SilentlyContinue
$r.Content | ConvertFrom-Json | ConvertTo-Json
if ($r.StatusCode -eq 200) { Pass "GET / → 200 OK" } else { Fail "GET / → $($r.StatusCode)" }

# ── 2. Health ──────────────────────────────────────────────────────────────────
Section "GET /health"
$r = Invoke-WebRequest "$BASE_URL/health" -UseBasicParsing
$r.Content | ConvertFrom-Json | ConvertTo-Json
if ($r.StatusCode -eq 200) { Pass "GET /health → 200 OK" } else { Fail "GET /health → $($r.StatusCode)" }

# ── 3. Submit feedback — premium tenant ────────────────────────────────────────
Section "POST /api/feedback (premium — Pizza Palace)"
$body = @{ tenant_id="pizza-palace-123"; rating=5; comment="Amazing pizza, absolutely delicious!"; customer_name="Alice" } | ConvertTo-Json
$r = Invoke-WebRequest "$BASE_URL/api/feedback" -Method POST `
     -Headers @{ "x-tenant-id"="pizza-palace-123"; "Content-Type"="application/json" } `
     -Body $body -UseBasicParsing
$r.Content | ConvertFrom-Json | ConvertTo-Json
if ($r.StatusCode -eq 201) { Pass "POST /api/feedback → 201 Created" } else { Fail "POST → $($r.StatusCode)" }

# ── 4. Submit feedback — basic tenant ─────────────────────────────────────────
Section "POST /api/feedback (basic — Burger Barn)"
$body = @{ tenant_id="burger-barn-456"; rating=3; comment="okay burgers, nothing special" } | ConvertTo-Json
$r = Invoke-WebRequest "$BASE_URL/api/feedback" -Method POST `
     -Headers @{ "x-tenant-id"="burger-barn-456"; "Content-Type"="application/json" } `
     -Body $body -UseBasicParsing
$r.Content | ConvertFrom-Json | ConvertTo-Json
if ($r.StatusCode -eq 201) { Pass "POST /api/feedback (basic) → 201 Created" } else { Fail "POST → $($r.StatusCode)" }

# ── 5. Invalid tenant → 401 ────────────────────────────────────────────────────
Section "POST /api/feedback (invalid tenant → expect 401)"
try {
    Invoke-WebRequest "$BASE_URL/api/feedback" -Method POST `
        -Headers @{ "x-tenant-id"="unknown-tenant"; "Content-Type"="application/json" } `
        -Body '{"tenant_id":"x","rating":3,"comment":"test"}' -UseBasicParsing | Out-Null
    Fail "Expected 401 but got success"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 401) { Pass "Invalid tenant → 401 Unauthorized" } else { Fail "Got $code, expected 401" }
}

# ── 6. Empty comment → 400 ────────────────────────────────────────────────────
Section "POST /api/feedback (empty comment → expect 400)"
try {
    Invoke-WebRequest "$BASE_URL/api/feedback" -Method POST `
        -Headers @{ "x-tenant-id"="pizza-palace-123"; "Content-Type"="application/json" } `
        -Body '{"tenant_id":"pizza-palace-123","rating":3,"comment":"   "}' -UseBasicParsing | Out-Null
    Fail "Expected 400 but got success"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 400) { Pass "Empty comment → 400 Bad Request" } else { Fail "Got $code, expected 400" }
}

# ── 7. Get insights ────────────────────────────────────────────────────────────
Section "GET /api/restaurants/pizza-palace-123/insights"
$r = Invoke-WebRequest "$BASE_URL/api/restaurants/pizza-palace-123/insights" `
     -Headers @{ "x-tenant-id"="pizza-palace-123" } -UseBasicParsing
$r.Content | ConvertFrom-Json | ConvertTo-Json -Depth 5
if ($r.StatusCode -eq 200) { Pass "GET /insights → 200 OK" } else { Fail "GET /insights → $($r.StatusCode)" }

# ── 8. Cross-tenant read → 403 ────────────────────────────────────────────────
Section "GET /insights (burger-barn reads pizza → expect 403)"
try {
    Invoke-WebRequest "$BASE_URL/api/restaurants/pizza-palace-123/insights" `
        -Headers @{ "x-tenant-id"="burger-barn-456" } -UseBasicParsing | Out-Null
    Fail "Expected 403 but got success"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 403) { Pass "Cross-tenant read → 403 Forbidden" } else { Fail "Got $code, expected 403" }
}

Write-Host "`n── Done ──`n" -ForegroundColor Cyan
