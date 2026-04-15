"""
src/storage/s3_client.py
Mock S3 client — simulates AWS S3 using in-memory dicts.
In production this would be replaced by boto3; the API surface is kept identical
so application code requires zero changes on the swap.

Supported operations:
  put_object   → upload dict/str/bytes to a named bucket
  get_object   → retrieve raw or parsed JSON
  list_objects → list keys under a prefix
  delete_object → remove an object
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from src.utils.exceptions import StorageError

logger = logging.getLogger(__name__)


class S3Client:
    """
    In-memory simulation of an S3 bucket store.

    Internal layout:
        _store = {
            "bucket-name": {
                "prefix/key.json": {
                    "body": <bytes>,
                    "content_type": str,
                    "last_modified": ISO-8601 str,
                    "size_bytes": int,
                }
            }
        }
    """

    def __init__(self):
        self._store: Dict[str, Dict[str, Dict[str, Any]]] = {}

    # ── Internal ───────────────────────────────────────────────────────────

    def _ensure_bucket(self, bucket: str) -> None:
        if bucket not in self._store:
            self._store[bucket] = {}

    # ── Core operations ────────────────────────────────────────────────────

    def put_object(
        self,
        key: str,
        data: Any,
        bucket: str = "default",
        content_type: str = "application/json",
    ) -> bool:
        """
        Upload an object.
        • dict / list  → auto-serialised to UTF-8 JSON bytes
        • str          → encoded to UTF-8 bytes
        • bytes        → stored as-is
        Returns True on success, False on serialisation error.
        """
        if not key:
            raise StorageError("put_object", "S3 object key cannot be empty.")

        self._ensure_bucket(bucket)

        try:
            if isinstance(data, (dict, list)):
                body = json.dumps(data, default=str).encode("utf-8")
            elif isinstance(data, str):
                body = data.encode("utf-8")
            elif isinstance(data, bytes):
                body = data
            else:
                body = json.dumps(data, default=str).encode("utf-8")

            self._store[bucket][key] = {
                "body": body,
                "content_type": content_type,
                "last_modified": datetime.now(timezone.utc).isoformat(),
                "size_bytes": len(body),
            }
            logger.info(f"Mock S3: PUT s3://{bucket}/{key} ({len(body)} bytes)")
            return True

        except (TypeError, ValueError) as exc:
            logger.error(f"Mock S3: serialisation error for key '{key}': {exc}")
            return False

    def get_object(self, key: str, bucket: str = "default") -> Optional[Dict[str, Any]]:
        """
        Retrieve an object.
        Returns None if the key does not exist (matches boto3 ClientError pattern).
        """
        if not key:
            return None

        obj = self._store.get(bucket, {}).get(key)
        if obj is None:
            logger.warning(f"Mock S3: GET miss  s3://{bucket}/{key}")
            return None

        logger.info(f"Mock S3: GET hit   s3://{bucket}/{key}")
        return {
            "Body": obj["body"],
            "ContentType": obj["content_type"],
            "LastModified": obj["last_modified"],
            "ContentLength": obj["size_bytes"],
        }

    def get_json(self, key: str, bucket: str = "default") -> Optional[Any]:
        """Convenience wrapper — auto-deserialises body as JSON."""
        obj = self.get_object(key, bucket)
        if obj is None:
            return None
        try:
            return json.loads(obj["Body"].decode("utf-8"))
        except json.JSONDecodeError as exc:
            logger.error(f"Mock S3: JSON decode error for key '{key}': {exc}")
            return None

    def list_objects(self, prefix: str = "", bucket: str = "default") -> List[Dict[str, Any]]:
        """List all keys in a bucket that start with `prefix`."""
        return [
            {"Key": k, "LastModified": v["last_modified"], "Size": v["size_bytes"]}
            for k, v in self._store.get(bucket, {}).items()
            if k.startswith(prefix)
        ]

    def delete_object(self, key: str, bucket: str = "default") -> bool:
        """Delete an object. Returns True if it existed."""
        if not key:
            raise StorageError("delete_object", "S3 object key cannot be empty.")

        existed = key in self._store.get(bucket, {})
        if existed:
            del self._store[bucket][key]
            logger.info(f"Mock S3: DELETE s3://{bucket}/{key}")
        return existed

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self._store

    def object_count(self, bucket: str = "default") -> int:
        return len(self._store.get(bucket, {}))