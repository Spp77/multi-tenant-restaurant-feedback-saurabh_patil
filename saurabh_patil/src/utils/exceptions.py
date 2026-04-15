"""
src/utils/exceptions.py
Custom exception hierarchy for the Multi-Tenant Restaurant Review API.
Using specific exception types makes error handling explicit and testable.
"""


class RestaurantAPIError(Exception):
    """Base exception for all application errors."""
    http_status: int = 500

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "code": self.http_status,
        }


# ── Tenant errors (4xx) ───────────────────────────────────────────────────────

class TenantNotFoundError(RestaurantAPIError):
    """Raised when the X-Tenant-ID header does not match a known tenant."""
    http_status = 401

    def __init__(self, tenant_id: str):
        super().__init__(
            message=f"Tenant '{tenant_id}' not found or is inactive.",
            details={"tenant_id": tenant_id},
        )


class FeatureNotEnabledError(RestaurantAPIError):
    """Raised when a tenant tries to use a feature their plan does not include."""
    http_status = 403

    def __init__(self, tenant_id: str, feature: str):
        super().__init__(
            message=f"Feature '{feature}' is not enabled for tenant '{tenant_id}'.",
            details={"tenant_id": tenant_id, "feature": feature},
        )


# ── Validation errors (400) ───────────────────────────────────────────────────

class ValidationError(RestaurantAPIError):
    """Raised when request data fails business-rule validation."""
    http_status = 400

    def __init__(self, message: str, field: str = None):
        details = {"field": field} if field else {}
        super().__init__(message=message, details=details)


class EmptyCommentError(ValidationError):
    """Specific validation error for blank feedback comments."""

    def __init__(self):
        super().__init__(
            message="Feedback comment cannot be empty or whitespace only.",
            field="comment",
        )


# ── Storage errors (500) ──────────────────────────────────────────────────────

class StorageError(RestaurantAPIError):
    """Raised when a DynamoDB or S3 operation fails."""
    http_status = 500

    def __init__(self, operation: str, reason: str):
        super().__init__(
            message=f"Storage operation '{operation}' failed: {reason}",
            details={"operation": operation, "reason": reason},
        )


# ── External service errors (502) ────────────────────────────────────────────

class SentimentServiceError(RestaurantAPIError):
    """Raised when the external sentiment API is unreachable or returns garbage."""
    http_status = 502

    def __init__(self, reason: str):
        super().__init__(
            message=f"Sentiment service unavailable: {reason}",
            details={"reason": reason},
        )
