"""
Unit Tests: S3Client (tests/test_s3_client.py)
Coverage target: 90%+
"""
import json
import pytest
from src.storage.s3_client import S3Client
from src.utils.exceptions import StorageError


@pytest.fixture
def s3():
    return S3Client()


# ── put_object ────────────────────────────────────────────────────────────────

class TestPutObject:
    def test_put_dict_returns_true(self, s3):
        assert s3.put_object("reports/tenant.json", {"score": 0.9}) is True

    def test_put_string_body(self, s3):
        assert s3.put_object("reports/hello.txt", "hello world") is True

    def test_put_bytes_body(self, s3):
        assert s3.put_object("reports/raw.bin", b"\x00\x01\x02") is True

    def test_put_creates_bucket_implicitly(self, s3):
        s3.put_object("key.json", {"a": 1}, bucket="new-bucket")
        assert s3.bucket_exists("new-bucket")

    def test_put_increments_object_count(self, s3):
        s3.put_object("k1.json", {}, bucket="bkt")
        s3.put_object("k2.json", {}, bucket="bkt")
        assert s3.object_count("bkt") == 2

    def test_put_raises_on_empty_key(self, s3):
        with pytest.raises(StorageError):
            s3.put_object("", {"data": 1})

    def test_put_overwrites_existing_key(self, s3):
        s3.put_object("report.json", {"v": 1})
        s3.put_object("report.json", {"v": 2})
        result = s3.get_json("report.json")
        assert result["v"] == 2


# ── get_object ────────────────────────────────────────────────────────────────

class TestGetObject:
    def test_get_returns_body_dict(self, s3):
        s3.put_object("data.json", {"name": "Pizza Palace"})
        obj = s3.get_object("data.json")
        assert obj is not None
        assert obj["ContentType"] == "application/json"

    def test_get_returns_none_for_missing_key(self, s3):
        assert s3.get_object("nonexistent.json") is None

    def test_get_returns_none_for_empty_key(self, s3):
        assert s3.get_object("") is None

    def test_get_returns_none_for_unknown_bucket(self, s3):
        assert s3.get_object("key.json", bucket="ghost-bucket") is None

    def test_get_includes_metadata(self, s3):
        s3.put_object("meta.json", {"x": 1})
        obj = s3.get_object("meta.json")
        assert "LastModified" in obj
        assert "ContentLength" in obj


# ── get_json ──────────────────────────────────────────────────────────────────

class TestGetJson:
    def test_get_json_deserialises_dict(self, s3):
        payload = {"tenant_id": "pizza-palace-123", "score": 0.95}
        s3.put_object("result.json", payload)
        result = s3.get_json("result.json")
        assert result == payload

    def test_get_json_returns_none_for_missing(self, s3):
        assert s3.get_json("missing.json") is None

    def test_get_json_deserialises_list(self, s3):
        s3.put_object("list.json", [1, 2, 3])
        assert s3.get_json("list.json") == [1, 2, 3]


# ── list_objects ──────────────────────────────────────────────────────────────

class TestListObjects:
    def test_list_returns_all_keys_in_bucket(self, s3):
        for i in range(3):
            s3.put_object(f"items/item-{i}.json", {"i": i}, bucket="listing-test")
        results = s3.list_objects(bucket="listing-test")
        assert len(results) == 3

    def test_list_filters_by_prefix(self, s3):
        s3.put_object("reports/jan.json", {}, bucket="pfx")
        s3.put_object("reports/feb.json", {}, bucket="pfx")
        s3.put_object("archive/old.json", {}, bucket="pfx")
        results = s3.list_objects(prefix="reports/", bucket="pfx")
        assert len(results) == 2
        keys = {r["Key"] for r in results}
        assert "archive/old.json" not in keys

    def test_list_empty_bucket_returns_empty_list(self, s3):
        assert s3.list_objects(bucket="empty-bucket") == []

    def test_list_result_contains_key_and_size(self, s3):
        s3.put_object("file.json", {"a": 1}, bucket="meta-bucket")
        result = s3.list_objects(bucket="meta-bucket")[0]
        assert "Key" in result
        assert "Size" in result
        assert "LastModified" in result


# ── delete_object ─────────────────────────────────────────────────────────────

class TestDeleteObject:
    def test_delete_existing_returns_true(self, s3):
        s3.put_object("to-delete.json", {"x": 1})
        assert s3.delete_object("to-delete.json") is True

    def test_delete_nonexistent_returns_false(self, s3):
        assert s3.delete_object("ghost.json") is False

    def test_delete_removes_from_bucket(self, s3):
        s3.put_object("bye.json", {})
        s3.delete_object("bye.json")
        assert s3.get_object("bye.json") is None

    def test_delete_raises_on_empty_key(self, s3):
        with pytest.raises(StorageError):
            s3.delete_object("")


# ── Tenant isolation (multi-bucket) ──────────────────────────────────────────

class TestMultiBucket:
    def test_objects_are_isolated_by_bucket(self, s3):
        s3.put_object("report.json", {"tenant": "A"}, bucket="bucket-a")
        s3.put_object("report.json", {"tenant": "B"}, bucket="bucket-b")
        assert s3.get_json("report.json", bucket="bucket-a")["tenant"] == "A"
        assert s3.get_json("report.json", bucket="bucket-b")["tenant"] == "B"

    def test_bucket_exists_false_for_new_client(self, s3):
        assert not s3.bucket_exists("never-created")

    def test_object_count_zero_for_unknown_bucket(self, s3):
        assert s3.object_count("no-bucket") == 0
