"""
src/models/tenant.py
Pydantic model representing a registered tenant (restaurant).
Loaded once at startup from config/tenant_registry.json.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Optional
from datetime import datetime, timezone


class TenantFeatures(BaseModel):
    """Feature flags that control which plan capabilities are unlocked."""
    sentiment_analysis: bool = False
    advanced_insights: bool = False


class Tenant(BaseModel):
    """
    Represents one registered restaurant tenant.

    tenant_id        → Partition Key in DynamoDB; must be globally unique.
    plan             → "basic" | "premium" — drives feature gate checks.
    features         → Nested flags derived from the plan at registration time.
    """
    tenant_id: str
    restaurant_name: str
    api_key: str
    plan: str
    features: TenantFeatures = Field(default_factory=TenantFeatures)
    created_at: Optional[str] = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v: str) -> str:
        if v not in ("basic", "premium"):
            raise ValueError("Plan must be 'basic' or 'premium'")
        return v

    # ── Convenience helpers ────────────────────────────────────────────────

    def can_use(self, feature: str) -> bool:
        """Returns True if this tenant has the given feature enabled."""
        return getattr(self.features, feature, False)

    def is_premium(self) -> bool:
        return self.plan == "premium"

    def to_dict(self) -> dict:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "Tenant":
        """Factory — converts a raw JSON registry entry into a Tenant."""
        entry = dict(data)
        if isinstance(entry.get("features"), dict):
            entry["features"] = TenantFeatures(**entry["features"])
        return cls(**entry)