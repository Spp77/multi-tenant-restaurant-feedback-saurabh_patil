"""
Unit Tests: DynamoDBClient (tests/test_dynamodb_client.py)
Coverage target: 90%+
"""
import pytest
from src.storage.dynamodb_client import DynamoDBClient
from src.models.feedback import Feedback
from src.utils.exceptions import StorageError


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_feedback(comment="Great food!", rating=5, tenant_id="tenant-a", feedback_id=None):
    fb = Feedback(comment=comment, rating=rating, tenant_id=tenant_id)
    if feedback_id:
        fb.feedback_id = feedback_id
    return fb


# ── put_item ─────────────────────────────────────────────────────────────────

class TestPutItem:
    def test_put_item_creates_partition_for_new_tenant(self):
        db = DynamoDBClient()
        fb = make_feedback(tenant_id="tenant-a")
        db.put_item(fb)
        assert "tenant-a" in db._table

    def test_put_item_stores_feedback_under_correct_key(self):
        db = DynamoDBClient()
        fb = make_feedback(tenant_id="tenant-a")
        db.put_item(fb)
        assert fb.feedback_id in db._table["tenant-a"]

    def test_put_item_stores_dict_representation(self):
        db = DynamoDBClient()
        fb = make_feedback(comment="Lovely pasta", tenant_id="tenant-a")
        db.put_item(fb)
        stored = db._table["tenant-a"][fb.feedback_id]
        assert stored["comment"] == "Lovely pasta"
        assert stored["tenant_id"] == "tenant-a"

    def test_put_item_multiple_items_same_tenant(self):
        db = DynamoDBClient()
        fb1 = make_feedback(comment="First", tenant_id="tenant-a")
        fb2 = make_feedback(comment="Second", tenant_id="tenant-a")
        db.put_item(fb1)
        db.put_item(fb2)
        assert len(db._table["tenant-a"]) == 2

    def test_put_item_raises_on_empty_tenant_id(self):
        """put_item must enforce the Partition Key constraint."""
        db = DynamoDBClient()
        fb = Feedback(comment="Hello", rating=3, tenant_id="placeholder")
        fb.tenant_id = ""          # bypass Pydantic by direct assignment
        with pytest.raises(StorageError):
            db.put_item(fb)

    def test_put_item_raises_on_empty_feedback_id(self):
        """put_item must enforce the Sort Key constraint."""
        db = DynamoDBClient()
        fb = make_feedback(tenant_id="tenant-x")
        fb.feedback_id = ""        # corrupt the sort key
        with pytest.raises(StorageError):
            db.put_item(fb)

    def test_put_item_overwrites_existing_record(self):
        """Writing the same feedback_id twice should overwrite (upsert semantics)."""
        db = DynamoDBClient()
        fb = make_feedback(comment="Original", tenant_id="tenant-a")
        db.put_item(fb)
        fb.comment = "Updated"
        db.put_item(fb)
        stored = db._table["tenant-a"][fb.feedback_id]
        assert stored["comment"] == "Updated"


# ── get_item ──────────────────────────────────────────────────────────────────

class TestGetItem:
    def test_get_item_returns_stored_record(self):
        db = DynamoDBClient()
        fb = make_feedback(comment="Tasty!", tenant_id="tenant-b")
        db.put_item(fb)
        result = db.get_item("tenant-b", fb.feedback_id)
        assert result is not None
        assert result["comment"] == "Tasty!"

    def test_get_item_returns_none_for_unknown_feedback_id(self):
        db = DynamoDBClient()
        fb = make_feedback(tenant_id="tenant-b")
        db.put_item(fb)
        assert db.get_item("tenant-b", "nonexistent-id") is None

    def test_get_item_returns_none_for_unknown_tenant(self):
        db = DynamoDBClient()
        assert db.get_item("ghost-tenant", "some-id") is None

    def test_get_item_raises_on_empty_tenant_id(self):
        db = DynamoDBClient()
        with pytest.raises(StorageError):
            db.get_item("", "some-id")

    def test_get_item_raises_on_empty_feedback_id(self):
        db = DynamoDBClient()
        with pytest.raises(StorageError):
            db.get_item("tenant-a", "")


# ── query_by_tenant ───────────────────────────────────────────────────────────

class TestQueryByTenant:
    def test_query_returns_all_records_for_tenant(self):
        db = DynamoDBClient()
        for i in range(3):
            db.put_item(make_feedback(comment=f"Item {i}", tenant_id="tenant-c"))
        results = db.query_by_tenant("tenant-c")
        assert len(results) == 3

    def test_query_returns_empty_list_for_unknown_tenant(self):
        db = DynamoDBClient()
        assert db.query_by_tenant("no-such-tenant") == []

    def test_query_raises_on_empty_tenant_id(self):
        db = DynamoDBClient()
        with pytest.raises(StorageError):
            db.query_by_tenant("")

    def test_query_results_are_sorted_by_created_at_descending(self):
        """Verify the sort order mimics DynamoDB Query DESC behaviour."""
        import time
        db = DynamoDBClient()

        fb1 = make_feedback(comment="Older", tenant_id="tenant-d")
        db.put_item(fb1)
        time.sleep(0.01)   # ensure distinct timestamps
        fb2 = make_feedback(comment="Newer", tenant_id="tenant-d")
        db.put_item(fb2)

        results = db.query_by_tenant("tenant-d")
        # Newest first
        assert results[0]["comment"] == "Newer"
        assert results[1]["comment"] == "Older"


# ── Tenant Isolation ──────────────────────────────────────────────────────────

class TestTenantIsolation:
    def test_tenants_cannot_see_each_others_data(self):
        db = DynamoDBClient()
        fb_a = make_feedback(comment="For A only", tenant_id="tenant-a")
        fb_b = make_feedback(comment="For B only", tenant_id="tenant-b")
        db.put_item(fb_a)
        db.put_item(fb_b)

        results_a = db.query_by_tenant("tenant-a")
        results_b = db.query_by_tenant("tenant-b")

        assert len(results_a) == 1
        assert results_a[0]["comment"] == "For A only"
        assert len(results_b) == 1
        assert results_b[0]["comment"] == "For B only"

    def test_get_item_scoped_to_correct_tenant(self):
        db = DynamoDBClient()
        fb = make_feedback(tenant_id="tenant-a")
        db.put_item(fb)
        # Tenant B should NOT be able to retrieve Tenant A's feedback_id
        assert db.get_item("tenant-b", fb.feedback_id) is None
