from __future__ import annotations

from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError


class IdempotencyConflictError(Exception):
    """Idempotency-Key was reused with a different request body."""


class IdempotencyRepoDdb:
    """DynamoDB-backed idempotency store.

    Expected item shape:
      - idempotency_key (PK, S)
      - request_hash (S)
      - response_status (N)
      - response_body (S)
      - created_at (N)
      - ttl (N)

    Notes:
      * We store the *final* response once computed.
      * On retries, we return the stored response if the request hash matches.
    """

    def __init__(self, table_name: str):
        self._table = boto3.resource("dynamodb").Table(table_name)

    def get(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        res = self._table.get_item(Key={"idempotency_key": idempotency_key})
        return res.get("Item")

    def put_response_if_absent(
        self,
        idempotency_key: str,
        request_hash: str,
        response_status: int,
        response_body: str,
        created_at: int,
        ttl: int,
    ) -> bool:
        """Store the computed response.

        Returns True if inserted, False if the key already existed.
        """
        try:
            self._table.put_item(
                Item={
                    "idempotency_key": idempotency_key,
                    "request_hash": request_hash,
                    "response_status": int(response_status),
                    "response_body": response_body,
                    "created_at": int(created_at),
                    "ttl": int(ttl),
                },
                ConditionExpression="attribute_not_exists(idempotency_key)",
            )
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def assert_same_request(self, item: Dict[str, Any], request_hash: str) -> None:
        if not item:
            return
        if item.get("request_hash") != request_hash:
            raise IdempotencyConflictError()