from typing import Dict, List, Optional, Any
from src.models.feedback import Feedback
from src.utils.exceptions import StorageError


class DynamoDBClient:
    """
    In-memory DynamoDB simulation.
    Layout: { tenant_id: { feedback_id: record } } — mirrors PK/SK structure.
    """

    def __init__(self):
        self._table: Dict[str, Dict[str, Any]] = {}

    def put_item(self, feedback: Feedback) -> None:
        if not feedback.tenant_id:
            raise StorageError("put_item", "Partition Key (tenant_id) cannot be empty.")
        if not feedback.feedback_id:
            raise StorageError("put_item", "Sort Key (feedback_id) cannot be empty.")

        if feedback.tenant_id not in self._table:
            self._table[feedback.tenant_id] = {}

        self._table[feedback.tenant_id][feedback.feedback_id] = feedback.to_dict()

    def get_item(self, tenant_id: str, feedback_id: str) -> Optional[Dict[str, Any]]:
        if not tenant_id or not feedback_id:
            raise StorageError("get_item", "Both tenant_id and feedback_id are required.")

        return self._table.get(tenant_id, {}).get(feedback_id)

    def query_by_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Returns all records for a tenant, sorted by created_at DESC."""
        if not tenant_id:
            raise StorageError("query_by_tenant", "tenant_id is required.")

        return sorted(
            self._table.get(tenant_id, {}).values(),
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )