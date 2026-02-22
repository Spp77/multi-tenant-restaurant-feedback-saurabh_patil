# Coding Exercise

**Time Estimate:** 4-6 hours (with AI assistance)

---

## 📋 Exercise Overview

You will build a **Multi-Tenant Restaurant Review API** - a simplified backend system.

**Scenario:** Multiple restaurants (tenants) use your API to collect and analyze customer feedback. Each restaurant's data must be completely isolated, and the system should support different feature tiers.

---

## 🎯 Learning Objectives

This exercise tests your ability to:
- ✅ Build multi-tenant architectures with data isolation
- ✅ Integrate external APIs (sentiment analysis)
- ✅ Work with AWS services (DynamoDB, S3 simulation)
- ✅ Write testable code with dependency injection
- ✅ Follow Git feature-branch workflow
- ✅ Write comprehensive tests with mocks
- ✅ Handle errors and edge cases gracefully
- ✅ Document your work clearly

---

## 🏗️ Architecture Overview

```
POST /api/feedback
  ↓
[Tenant Resolution] → Identify which restaurant
  ↓
[Feature Gate Check] → Can this tenant use sentiment analysis?
  ↓
[External API Call] → Get sentiment score (if enabled)
  ↓
[Data Storage] → Save to tenant-specific table
  ↓
[Response] → Return feedback ID + sentiment

GET /api/restaurants/{tenant_id}/insights
  ↓
[Data Retrieval] → Get all feedback for tenant
  ↓
[Analysis] → Calculate average sentiment, top complaints
  ↓
[Response] → Return insights JSON
```

---

## 📦 Project Structure

Create a new Git repository with this structure:

```
restaurant-review-api/
├── README.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   └── feedback_handler.py      # Main API logic
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── dynamodb_client.py       # Mock DynamoDB operations
│   │   └── s3_client.py             # Mock S3 operations
│   ├── external/
│   │   ├── __init__.py
│   │   └── sentiment_service.py     # External API integration
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tenant.py                # Tenant data model
│   │   └── feedback.py              # Feedback data model
│   └── utils/
│       ├── __init__.py
│       ├── logger.py                # Structured logging
│       └── exceptions.py            # Custom exceptions
├── tests/
│   ├── __init__.py
│   ├── test_feedback_handler.py
│   ├── test_dynamodb_client.py
│   ├── test_sentiment_service.py
│   └── fixtures/
│       └── sample_data.json
└── config/
    └── tenant_registry.json          # Mock tenant configuration
```

---

## 📝 Part 1: Data Models (30 minutes)

### Task 1.1: Create Tenant Model

**File:** `src/models/tenant.py`

Create a `Tenant` class with these attributes:
- `tenant_id` (str): Unique identifier
- `restaurant_name` (str): Display name
- `api_key` (str): Authentication key
- `plan` (str): "basic" or "premium"
- `features` (dict): Feature flags
  - `sentiment_analysis` (bool)
  - `advanced_insights` (bool)
- `created_at` (str): ISO 8601 timestamp

**Requirements:**
- Use Python dataclasses or Pydantic models
- Include type hints on all attributes
- Add a `from_dict()` class method for JSON deserialization
- Add a `to_dict()` method for JSON serialization
- Validate that `plan` is either "basic" or "premium"

**Example:**
```python
tenant = Tenant(
    tenant_id="pizza-palace-123",
    restaurant_name="Pizza Palace",
    api_key="pk_test_abc123",
    plan="premium",
    features={
        "sentiment_analysis": True,
        "advanced_insights": True
    },
    created_at="2026-02-22T10:00:00Z"
)
```

### Task 1.2: Create Feedback Model

**File:** `src/models/feedback.py`

Create a `Feedback` class with these attributes:
- `feedback_id` (str): UUID
- `tenant_id` (str): Which restaurant
- `customer_name` (str): Customer name (optional)
- `rating` (int): 1-5 stars
- `comment` (str): Text review
- `sentiment_score` (float | None): -1.0 to 1.0 (None if not analyzed)
- `sentiment_label` (str | None): "positive", "neutral", "negative"
- `created_at` (str): ISO 8601 timestamp

**Requirements:**
- Include validation: rating must be 1-5
- Auto-generate `feedback_id` using `uuid.uuid4()` if not provided
- Auto-set `created_at` to current UTC time if not provided
- Type hints on all attributes

---

## 📝 Part 2: Mock AWS Storage Layer (60 minutes)

### Task 2.1: Mock DynamoDB Client

**File:** `src/storage/dynamodb_client.py`

Create a `DynamoDBClient` class that simulates DynamoDB using an in-memory dictionary.

**Note:** You don't need real AWS credentials. Use a Python dict to simulate the database.

**Methods to implement:**

```python
class DynamoDBClient:
    def __init__(self):
        """Initialize in-memory storage: {tenant_id: [feedback_items]}"""
        self._storage: dict[str, list[dict]] = {}
    
    def save_feedback(self, tenant_id: str, feedback: dict) -> None:
        """
        Save feedback to tenant-specific table.
        
        Args:
            tenant_id: Restaurant identifier
            feedback: Feedback dict (from feedback.to_dict())
        
        Raises:
            ValueError: If tenant_id is empty
        """
        pass
    
    def get_feedback_by_id(self, tenant_id: str, feedback_id: str) -> dict | None:
        """
        Retrieve a specific feedback item.
        
        Returns:
            Feedback dict or None if not found
        """
        pass
    
    def list_feedback(self, tenant_id: str, limit: int = 100) -> list[dict]:
        """
        Get all feedback for a tenant (most recent first).
        
        Args:
            tenant_id: Restaurant identifier
            limit: Max number of items to return
        
        Returns:
            List of feedback dicts, sorted by created_at descending
        """
        pass
    
    def get_feedback_count(self, tenant_id: str) -> int:
        """Count total feedback items for tenant."""
        pass
    
    def delete_all_feedback(self, tenant_id: str) -> int:
        """
        Delete all feedback for tenant (for testing).
        
        Returns:
            Number of items deleted
        """
        pass
```

**Requirements:**
- Ensure complete tenant isolation (tenant1's data never visible to tenant2)
- Validate all inputs (raise `ValueError` for invalid data)
- Include docstrings with type hints
- Handle edge cases (empty tenant_id, non-existent feedback_id)

### Task 2.2: Mock S3 Client

**File:** `src/storage/s3_client.py`

Create a simple S3 client that stores tenant configuration files in memory.

```python
class S3Client:
    def __init__(self):
        """Initialize in-memory storage: {s3_key: file_content}"""
        self._storage: dict[str, str] = {}
    
    def upload_json(self, key: str, data: dict) -> None:
        """
        Upload JSON data to S3 key.
        
        Args:
            key: S3 key path (e.g., "tenants/pizza-palace/config.json")
            data: Dict to serialize as JSON
        """
        pass
    
    def download_json(self, key: str) -> dict | None:
        """
        Download and parse JSON from S3.
        
        Returns:
            Dict or None if key doesn't exist
        """
        pass
    
    def list_keys(self, prefix: str) -> list[str]:
        """
        List all keys starting with prefix.
        
        Args:
            prefix: S3 key prefix (e.g., "tenants/")
        
        Returns:
            List of matching keys
        """
        pass
```

**Requirements:**
- Store data as JSON strings in memory
- Handle JSON serialization errors gracefully
- Return `None` for missing keys (don't raise exceptions)

---

## 📝 Part 3: External API Integration (45 minutes)

### Task 3.1: Sentiment Analysis Service

**File:** `src/external/sentiment_service.py`

Create a service that calls a mock sentiment analysis API.

**Mock API Behavior:**
Since you don't have a real API, simulate it with this logic:

```python
class SentimentService:
    def __init__(self, api_key: str | None = None):
        """
        Initialize sentiment service.
        
        Args:
            api_key: API key for authentication (not used in mock)
        """
        self.api_key = api_key
    
    def analyze_sentiment(self, text: str) -> dict:
        """
        Analyze sentiment of text.
        
        Mock implementation: Use keyword matching
        - If text contains positive words → positive score
        - If text contains negative words → negative score
        - Otherwise → neutral
        
        Returns:
            {
                "score": float,      # -1.0 to 1.0
                "label": str,        # "positive", "neutral", "negative"
                "confidence": float  # 0.0 to 1.0
            }
        
        Raises:
            ValueError: If text is empty
            Exception: If API call fails (simulate 1% random failure)
        """
        pass
```

**Mock Implementation Logic:**

```python
import random

positive_words = ["great", "excellent", "amazing", "love", "best", "wonderful", "delicious"]
negative_words = ["bad", "terrible", "awful", "hate", "worst", "disgusting", "never"]

text_lower = text.lower()

# Count positive/negative words
positive_count = sum(1 for word in positive_words if word in text_lower)
negative_count = sum(1 for word in negative_words if word in text_lower)

# Simulate 1% API failure rate
if random.random() < 0.01:
    raise Exception("Sentiment API temporarily unavailable")

# Calculate score
if positive_count > negative_count:
    score = min(0.9, 0.3 + (positive_count * 0.2))
    label = "positive"
elif negative_count > positive_count:
    score = max(-0.9, -0.3 - (negative_count * 0.2))
    label = "negative"
else:
    score = 0.0
    label = "neutral"

return {
    "score": round(score, 2),
    "label": label,
    "confidence": 0.85
}
```

**Testing Scenarios:**
- "The pizza was amazing and delicious!" → positive
- "Terrible service, never coming back" → negative
- "It was okay" → neutral
- "" (empty) → ValueError
- (1% of calls) → Exception

---

## 📝 Part 4: Core API Handler (90 minutes)

### Task 4.1: Tenant Registry

**File:** `config/tenant_registry.json`

Create a JSON file with 3 mock restaurants:

```json
{
  "tenants": [
    {
      "tenant_id": "pizza-palace-123",
      "restaurant_name": "Pizza Palace",
      "api_key": "pk_pizza_abc123",
      "plan": "premium",
      "features": {
        "sentiment_analysis": true,
        "advanced_insights": true
      },
      "created_at": "2026-01-15T00:00:00Z"
    },
    {
      "tenant_id": "burger-barn-456",
      "restaurant_name": "Burger Barn",
      "api_key": "pk_burger_def456",
      "plan": "basic",
      "features": {
        "sentiment_analysis": false,
        "advanced_insights": false
      },
      "created_at": "2026-01-20T00:00:00Z"
    },
    {
      "tenant_id": "sushi-spot-789",
      "restaurant_name": "Sushi Spot",
      "api_key": "pk_sushi_ghi789",
      "plan": "premium",
      "features": {
        "sentiment_analysis": true,
        "advanced_insights": false
      },
      "created_at": "2026-02-01T00:00:00Z"
    }
  ]
}
```

### Task 4.2: Main API Handler

**File:** `src/api/feedback_handler.py`

Create a `FeedbackHandler` class that orchestrates the entire flow.

```python
import logging
from typing import Optional
from datetime import datetime
import json

from src.models.tenant import Tenant
from src.models.feedback import Feedback
from src.storage.dynamodb_client import DynamoDBClient
from src.storage.s3_client import S3Client
from src.external.sentiment_service import SentimentService
from src.utils.logger import get_logger

logger = get_logger(__name__)


class FeedbackHandler:
    def __init__(
        self,
        db_client: DynamoDBClient,
        s3_client: S3Client,
        sentiment_service: SentimentService
    ):
        """
        Initialize handler with dependencies.
        
        Args:
            db_client: DynamoDB client (or mock)
            s3_client: S3 client (or mock)
            sentiment_service: Sentiment analysis service
        """
        self.db_client = db_client
        self.s3_client = s3_client
        self.sentiment_service = sentiment_service
        self._tenant_cache: dict[str, Tenant] = {}
    
    def load_tenant_by_api_key(self, api_key: str) -> Tenant | None:
        """
        Resolve tenant from API key.
        
        Args:
            api_key: Restaurant API key from request header
        
        Returns:
            Tenant object or None if not found
        
        Implementation:
            - Load config/tenant_registry.json
            - Find tenant with matching api_key
            - Cache result in self._tenant_cache for 60s (optional)
        """
        pass
    
    def submit_feedback(
        self,
        api_key: str,
        customer_name: str,
        rating: int,
        comment: str
    ) -> dict:
        """
        Process new customer feedback.
        
        Flow:
            1. Resolve tenant from api_key
            2. Validate input (rating 1-5, comment not empty)
            3. Check if tenant has sentiment_analysis feature
            4. If yes, call sentiment_service.analyze_sentiment()
            5. Create Feedback object
            6. Save to DynamoDB (tenant-specific table)
            7. Return response
        
        Args:
            api_key: Restaurant API key
            customer_name: Customer name (can be empty)
            rating: 1-5 stars
            comment: Text review
        
        Returns:
            {
                "feedback_id": "uuid-here",
                "tenant_id": "pizza-palace-123",
                "rating": 5,
                "sentiment": {
                    "score": 0.85,
                    "label": "positive"
                } or None,
                "created_at": "2026-02-22T10:00:00Z",
                "message": "Thank you for your feedback!"
            }
        
        Raises:
            ValueError: If tenant not found or validation fails
            Exception: If sentiment API fails (catch and set sentiment=None)
        """
        pass
    
    def get_restaurant_insights(self, api_key: str) -> dict:
        """
        Calculate insights for a restaurant.
        
        Args:
            api_key: Restaurant API key
        
        Returns:
            {
                "tenant_id": "pizza-palace-123",
                "restaurant_name": "Pizza Palace",
                "total_feedback": 42,
                "average_rating": 4.2,
                "rating_distribution": {
                    "5": 20,
                    "4": 15,
                    "3": 5,
                    "2": 1,
                    "1": 1
                },
                "sentiment_summary": {
                    "average_score": 0.65,
                    "positive_count": 30,
                    "neutral_count": 8,
                    "negative_count": 4
                } or None (if sentiment not enabled),
                "recent_feedback": [
                    # Last 5 feedback items
                ]
            }
        
        Raises:
            ValueError: If tenant not found
        """
        pass
```

**Requirements:**
- Use dependency injection (pass clients in __init__)
- Add structured logging for all operations
- Handle errors gracefully (don't crash on API failures)
- Validate all inputs before processing
- Return consistent JSON-serializable dicts

---

## 📝 Part 5: Testing (75 minutes)

### Task 5.1: Unit Tests for DynamoDB Client

**File:** `tests/test_dynamodb_client.py`

Write pytest tests covering:

```python
import pytest
from src.storage.dynamodb_client import DynamoDBClient


class TestDynamoDBClient:
    def test_save_and_retrieve_feedback(self):
        """Test saving and getting feedback by ID."""
        pass
    
    def test_tenant_isolation(self):
        """
        Ensure tenant1's data is not visible to tenant2.
        
        Steps:
        1. Save feedback for tenant1
        2. Save feedback for tenant2
        3. Assert tenant1 can only see their data
        4. Assert tenant2 can only see their data
        """
        pass
    
    def test_list_feedback_sorting(self):
        """Test that list_feedback returns items in reverse chronological order."""
        pass
    
    def test_list_feedback_limit(self):
        """Test that limit parameter works correctly."""
        pass
    
    def test_invalid_tenant_id(self):
        """Test that empty tenant_id raises ValueError."""
        pass
    
    def test_get_nonexistent_feedback(self):
        """Test that getting non-existent feedback returns None."""
        pass
    
    def test_delete_all_feedback(self):
        """Test delete_all_feedback removes all items for tenant."""
        pass
```

**Coverage Target:** 90%+

### Task 5.2: Unit Tests for Sentiment Service

**File:** `tests/test_sentiment_service.py`

Write tests with mocked API calls:

```python
import pytest
from src.external.sentiment_service import SentimentService


class TestSentimentService:
    def test_positive_sentiment(self):
        """Test detection of positive reviews."""
        service = SentimentService()
        result = service.analyze_sentiment("The food was amazing and delicious!")
        
        assert result["label"] == "positive"
        assert result["score"] > 0.5
        assert 0 <= result["confidence"] <= 1.0
    
    def test_negative_sentiment(self):
        """Test detection of negative reviews."""
        pass
    
    def test_neutral_sentiment(self):
        """Test neutral reviews."""
        pass
    
    def test_empty_text_raises_error(self):
        """Test that empty text raises ValueError."""
        pass
    
    def test_api_failure_handling(self):
        """
        Test that random API failures are handled.
        
        Note: Since failure is random (1%), you may need to:
        - Mock random.random() to force failure
        - Or call analyze_sentiment() 200 times and expect at least 1 failure
        """
        pass
```

### Task 5.3: Integration Test for Full Flow

**File:** `tests/test_feedback_handler.py`

Write end-to-end tests:

```python
import pytest
from src.api.feedback_handler import FeedbackHandler
from src.storage.dynamodb_client import DynamoDBClient
from src.storage.s3_client import S3Client
from src.external.sentiment_service import SentimentService


class TestFeedbackHandler:
    @pytest.fixture
    def handler(self):
        """Create handler with fresh mock dependencies."""
        db_client = DynamoDBClient()
        s3_client = S3Client()
        sentiment_service = SentimentService()
        
        # Load tenant registry into S3 client
        # (you need to implement this helper)
        
        return FeedbackHandler(db_client, s3_client, sentiment_service)
    
    def test_submit_feedback_with_sentiment(self, handler):
        """
        Test submitting feedback for premium tenant (sentiment enabled).
        
        Steps:
        1. Submit feedback with api_key="pk_pizza_abc123"
        2. Assert feedback_id is returned
        3. Assert sentiment is included in response
        4. Assert data is saved to DynamoDB
        """
        pass
    
    def test_submit_feedback_without_sentiment(self, handler):
        """
        Test submitting feedback for basic tenant (sentiment disabled).
        
        Steps:
        1. Submit feedback with api_key="pk_burger_def456"
        2. Assert sentiment is None in response
        """
        pass
    
    def test_invalid_api_key(self, handler):
        """Test that invalid API key raises ValueError."""
        pass
    
    def test_invalid_rating(self, handler):
        """Test that rating outside 1-5 range raises ValueError."""
        pass
    
    def test_get_insights(self, handler):
        """
        Test get_restaurant_insights calculation.
        
        Steps:
        1. Submit 10 feedback items for a tenant
        2. Call get_restaurant_insights()
        3. Assert total_feedback == 10
        4. Assert average_rating is calculated correctly
        5. Assert rating_distribution is correct
        """
        pass
    
    def test_sentiment_api_failure_graceful_degradation(self, handler):
        """
        Test that sentiment API failures don't crash the system.
        
        Mock sentiment_service.analyze_sentiment() to raise Exception.
        Assert feedback is still saved with sentiment=None.
        """
        pass
```

**Coverage Target:** 80%+

---

## 📝 Part 6: Utilities (30 minutes)

### Task 6.1: Structured Logger

**File:** `src/utils/logger.py`

Create a logger utility that outputs JSON-formatted logs:

```python
import logging
import json
from datetime import datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Output:
        {
            "timestamp": "2026-02-22T10:00:00.000Z",
            "level": "INFO",
            "logger": "src.api.feedback_handler",
            "message": "Processing feedback",
            "tenant_id": "pizza-palace-123",
            "feedback_id": "uuid-here"
        }
        """
        pass


def get_logger(name: str) -> logging.Logger:
    """
    Get or create a logger with JSON formatting.
    
    Args:
        name: Logger name (use __name__ from calling module)
    
    Returns:
        Configured logger instance
    """
    pass
```

### Task 6.2: Custom Exceptions

**File:** `src/utils/exceptions.py`

```python
class TenantNotFoundException(Exception):
    """Raised when tenant cannot be found."""
    pass


class InvalidAPIKeyException(Exception):
    """Raised when API key is invalid or missing."""
    pass


class ValidationException(Exception):
    """Raised when input validation fails."""
    pass


class ExternalServiceException(Exception):
    """Raised when external API call fails."""
    pass
```

Use these exceptions in your code instead of generic `ValueError` or `Exception`.

---

## 📝 Part 7: Git Workflow (30 minutes)

### Task 7.1: Feature Branch Workflow

Complete these Git operations:

**Step 1: Initialize Repository**
```bash
git init
git add .
git commit -m "chore: initial project structure"
```

**Step 2: Create Feature Branch**
```bash
git checkout -b feature/tenant-isolation
# Implement Part 2 (storage layer)
git add src/storage/
git commit -m "feat: implement tenant-isolated DynamoDB client"
git checkout main
git merge feature/tenant-isolation
```

**Step 3: Create Another Feature Branch**
```bash
git checkout -b feature/sentiment-integration
# Implement Part 3 (sentiment service)
git add src/external/
git commit -m "feat: add sentiment analysis integration"
git checkout main
git merge feature/sentiment-integration
```

**Step 4: Simulate Merge Conflict**
```bash
# Create two branches that modify the same file
git checkout -b feature/logging-improvement
# Add logging to feedback_handler.py
git commit -m "feat: add structured logging"

git checkout main
git checkout -b feature/error-handling
# Add error handling to feedback_handler.py (same lines)
git commit -m "feat: improve error handling"

git checkout main
git merge feature/logging-improvement
git merge feature/error-handling  # This will cause a conflict

# Resolve the conflict manually
# Keep both logging and error handling changes
git add src/api/feedback_handler.py
git commit -m "merge: resolve conflict between logging and error handling"
```

### Task 7.2: Git History

Your final Git history should look something like:

```
* merge: resolve conflict between logging and error handling
|\
| * feat: improve error handling
* | feat: add structured logging
|/
* feat: add sentiment analysis integration
* feat: implement tenant-isolated DynamoDB client
* test: add unit tests for storage layer
* feat: implement core API handler
* chore: initial project structure
```

**Deliverable:** Include a `git log --oneline --graph` screenshot in your submission.

---

## 📝 Part 8: Documentation (20 minutes)

### Task 8.1: README.md

Create a comprehensive README with:

1. **Project Overview** (2-3 sentences)
2. **Setup Instructions**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Running Tests**
   ```bash
   pytest tests/ -v --cov=src --cov-report=term-missing
   ```
4. **API Usage Examples**
   ```python
   # Example: Submit feedback
   from src.api.feedback_handler import FeedbackHandler
   from src.storage.dynamodb_client import DynamoDBClient
   from src.storage.s3_client import S3Client
   from src.external.sentiment_service import SentimentService
   
   handler = FeedbackHandler(
       DynamoDBClient(),
       S3Client(),
       SentimentService()
   )
   
   result = handler.submit_feedback(
       api_key="pk_pizza_abc123",
       customer_name="John Doe",
       rating=5,
       comment="Amazing pizza!"
   )
   print(result)
   ```
5. **Architecture Decisions**
   - Why did you choose X over Y?
   - How does tenant isolation work?
   - What trade-offs did you make?

### Task 8.2: Code Comments

Add docstrings to:
- All public classes
- All public methods
- Complex logic sections

**Example:**
```python
def submit_feedback(self, api_key: str, customer_name: str, rating: int, comment: str) -> dict:
    """
    Process new customer feedback.
    
    This method handles the complete feedback submission flow:
    1. Authenticates the tenant via API key lookup
    2. Validates input data (rating range, non-empty comment)
    3. Conditionally calls sentiment analysis (if tenant has feature enabled)
    4. Stores feedback in tenant-isolated DynamoDB table
    5. Returns confirmation with sentiment data (if applicable)
    
    Args:
        api_key: Restaurant's API key for authentication
        customer_name: Name of the customer (optional, can be empty string)
        rating: Star rating between 1 and 5 (inclusive)
        comment: Text review from customer (must not be empty)
    
    Returns:
        Dict containing:
            - feedback_id: UUID of created feedback
            - tenant_id: Restaurant identifier
            - rating: Echo of submitted rating
            - sentiment: Sentiment analysis result (if enabled) or None
            - created_at: ISO 8601 timestamp
            - message: Confirmation message
    
    Raises:
        InvalidAPIKeyException: If api_key doesn't match any tenant
        ValidationException: If rating not in 1-5 range or comment is empty
    
    Example:
        >>> handler.submit_feedback(
        ...     api_key="pk_pizza_abc123",
        ...     customer_name="Jane",
        ...     rating=5,
        ...     comment="Best pizza ever!"
        ... )
        {
            "feedback_id": "a1b2c3...",
            "tenant_id": "pizza-palace-123",
            "rating": 5,
            "sentiment": {"score": 0.92, "label": "positive"},
            "created_at": "2026-02-22T10:30:00Z",
            "message": "Thank you for your feedback!"
        }
    """
    # Implementation here
```

---

## 📊 Evaluation Criteria

You will be evaluated on:

### 1. **Code Quality (30%)**
- [ ] Clean, readable code with consistent style
- [ ] Proper use of type hints
- [ ] Meaningful variable/function names
- [ ] No hardcoded values (use constants/config)
- [ ] DRY principle (no code duplication)

### 2. **Architecture (25%)**
- [ ] Complete tenant isolation (no data leakage)
- [ ] Proper dependency injection
- [ ] Feature flag implementation works correctly
- [ ] Separation of concerns (models, storage, API, external)
- [ ] Error handling at appropriate layers

### 3. **Testing (20%)**
- [ ] Tests pass without errors
- [ ] Code coverage ≥80%
- [ ] Tests cover edge cases (empty input, invalid data)
- [ ] Mocks are used correctly (no actual external API calls)
- [ ] Integration tests cover full user flows

### 4. **Git Workflow (10%)**
- [ ] Meaningful commit messages
- [ ] Feature branch workflow demonstrated
- [ ] Merge conflict resolution shown
- [ ] Clean commit history (no "fix typo" spam)

### 5. **Documentation (10%)**
- [ ] README explains project clearly
- [ ] Setup instructions are complete
- [ ] Docstrings on all public methods
- [ ] Architecture decisions explained

### 6. **Problem Solving (5%)**
- [ ] Code works end-to-end
- [ ] Edge cases handled gracefully
- [ ] Demonstrates understanding of multi-tenancy

---

## 🎁 Bonus Challenges (Optional, +10%)

If you finish early and want to impress:

### Bonus 1: Add Caching (1-2 hours)
- Cache tenant registry in memory for 60 seconds
- Add a `@cache` decorator to `load_tenant_by_api_key()`
- Show cache hits/misses in logs

### Bonus 2: Add Rate Limiting (1 hour)
- Limit each tenant to 100 feedback submissions per day
- Return error message if limit exceeded
- Track usage in DynamoDB or in-memory counter

### Bonus 3: Add API Server (1-2 hours)
- Create a Flask or FastAPI server with these endpoints:
  - `POST /api/feedback` - Submit feedback
  - `GET /api/insights` - Get restaurant insights
- Include API key authentication via header
- Deploy locally and show `curl` examples

### Bonus 4: Add CI/CD Pipeline (30 minutes)
- Create `.github/workflows/test.yml`
- Run pytest on every push
- Show passing build badge in README

---

## 📤 Submission Instructions

Submit your work as:

1. **GitHub Repository (Preferred)**
   - Create a public GitHub repo
   - Push all your code
   - Share the repository URL
   - Include README.md with setup instructions

2. **Zip File (Alternative)**
   - Zip the entire project folder
   - Include `.git` folder to show commit history
   - Email to: [hiring@jivaha.ai]

**Include in your submission:**
- ✅ All source code (`src/` directory)
- ✅ All tests (`tests/` directory)
- ✅ `README.md` with documentation
- ✅ `requirements.txt` with dependencies
- ✅ Git history (commit log screenshot or `.git` folder)
- ✅ Test coverage report (screenshot or HTML report)

**DO NOT include:**
- ❌ `venv/` or `__pycache__/` folders
- ❌ `.pyc` files
- ❌ IDE config files (`.vscode/`, `.idea/`)

**Add `.gitignore`:**
```
venv/
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
.DS_Store
.vscode/
.idea/
```

---

## 💡 Tips for Success

### Use AI Assistants Effectively
- ✅ Use Copilot/ChatGPT to generate boilerplate code
- ✅ Ask AI to explain concepts you don't understand
- ✅ Use AI to write test cases
- ❌ Don't blindly copy-paste AI output (review and understand it)
- ❌ Don't let AI write your README (use your own words)

### Time Management (4-6 hours)
- **Hour 1:** Setup project structure, data models (Part 1-2)
- **Hour 2:** Storage layer and tests (Part 2-3)
- **Hour 3:** Sentiment service (Part 3)
- **Hour 4:** API handler (Part 4)
- **Hour 5:** Integration tests (Part 5)
- **Hour 6:** Git workflow, documentation, final review (Part 7-8)

### Common Pitfalls to Avoid
- ❌ Not testing tenant isolation properly
- ❌ Forgetting error handling in external API calls
- ❌ Not using type hints consistently
- ❌ Committing directly to main instead of feature branches
- ❌ Writing tests that pass but don't actually test anything
- ❌ Not reading requirements carefully

### If You Get Stuck
1. **Read the error message carefully** - Most errors are self-explanatory
2. **Check your type hints** - Are you passing the right types?
3. **Use print debugging** - Add `print()` statements to see what's happening
4. **Write a minimal test case** - Isolate the problem
5. **Ask AI for help** - But understand the solution before using it
6. **Review the architecture diagram** - Are you following the flow?

---

## ❓ FAQs

**Q: Can I use external libraries?**  
A: Yes, but keep it minimal. Acceptable libraries:
- `pytest` (required for testing)
- `pydantic` (optional for data models)
- Flask/FastAPI (only for Bonus 3)
- `requests` (if you want to mock HTTP calls)

**Q: Do I need real AWS credentials?**  
A: No! Use the in-memory mock implementations. The point is to show you understand the patterns, not to actually deploy to AWS.

**Q: How detailed should my tests be?**  
A: Aim for 80% coverage. Focus on critical paths and edge cases. Don't test trivial getters/setters.

**Q: Can I use Python 3.11+ features?**  
A: Yes! We use Python 3.13 in production, but anything 3.9+ is fine.

**Q: What if I can't finish in 4-6 hours?**  
A: Submit what you have! Partial completion with high-quality work is better than rushed, buggy code. Prioritize core features (Parts 1-5) over bonuses.

**Q: Can I refactor/improve the suggested structure?**  
A: Absolutely! If you have a better architecture in mind, go for it. Just document your reasoning in README.md.

**Q: Should I write production-ready code?**  
A: Treat this as real production code. Include error handling, logging, tests, and documentation. But don't over-engineer - keep it simple and focused.

---

## 🎯 What We're Looking For

The ideal candidate will:
1. **Write clean, readable code** that others can understand and maintain
2. **Test thoroughly** with good coverage of edge cases
3. **Document clearly** so new developers can onboard quickly
4. **Follow Git best practices** with meaningful commits and branches
5. **Handle errors gracefully** instead of crashing
6. **Demonstrate multi-tenant thinking** with proper isolation
7. **Show problem-solving skills** by handling ambiguous requirements
8. **Communicate clearly** through code comments and documentation

**Good luck! 🚀**

We're excited to see what you build. This exercise simulates the real work you'll do on our production platform. If you have questions during the exercise, that's normal - just document your assumptions in README.md and move forward.

---
