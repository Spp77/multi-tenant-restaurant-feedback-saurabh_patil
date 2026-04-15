from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, timezone

VALID_PLANS = ("basic", "premium")


class TenantFeatures(BaseModel):
    """Feature flags that control which plan capabilities are unlocked."""
    sentiment_analysis: bool = False
    advanced_insights:  bool = False


class Tenant(BaseModel):
    """
    Registered restaurant tenant.

    ``tenant_id`` is the Partition Key in DynamoDB — must be globally unique.
    ``plan`` drives all feature gate checks via the ``features`` flags.
    """
    tenant_id:       str
    restaurant_name: str
    api_key:         str
    plan:            str
    features:        TenantFeatures = Field(default_factory=TenantFeatures)
    created_at:      Optional[str]  = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v: str) -> str:
        if v not in VALID_PLANS:
            raise ValueError(f"Plan must be one of {VALID_PLANS}")
        return v

    def can_use(self, feature: str) -> bool:
        """Return True if this tenant's plan includes ``feature``."""
        return getattr(self.features, feature, False)

    def is_premium(self) -> bool:
        """Return True if tenant is on the premium plan."""
        return self.plan == "premium"

    def to_dict(self) -> dict:
        """Return a plain dict suitable for storage or JSON serialisation."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "Tenant":
        """
        Factory — converts a raw JSON registry entry into a Tenant.

        Handles the case where ``features`` arrives as a plain dict
        rather than a ``TenantFeatures`` instance.
        """
        entry = dict(data)
        if isinstance(entry.get("features"), dict):
            entry["features"] = TenantFeatures(**entry["features"])
        return cls(**entry)