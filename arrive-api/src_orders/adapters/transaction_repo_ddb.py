import os
import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError

class TransactionRepoDdb:
    def __init__(self, capacity_table_name: str, orders_table_name: str):
        self._cap_table = capacity_table_name
        self._orders_table = orders_table_name
        self._client = boto3.client("dynamodb")
        self._serializer = TypeSerializer()

    def _av(self, v):
        # Helper to serialize python types to DynamoDB types
        return self._serializer.serialize(v)

    def atomic_dispatch(
        self,
        *,
        restaurant_id: str,
        window_start: int,
        add_units: int,
        max_units: int,
        ttl: int,
        order_id: str,
        order_update_kwargs: dict,
    ) -> bool:
        """
        Attempts to atomically:
        1. Reserve capacity in CAPACITY_TABLE
        2. Update order status in ORDERS_TABLE (using provided kwargs)

        Returns:
            True if transaction succeeded (Capacity reserved + Order updated)
            False if transaction was canceled (Capacity full or Order condition failed)
        
        Raises:
            ClientError: For any non-condition-check errors (e.g. throughput, auth)
        """
        
        # 1. Prepare Capacity Update (Same logic as CapacityRepo)
        # Condition: (New Item AND add <= max) OR (Existing Item AND used + add <= max)
        cap_update = {
            "TableName": self._cap_table,
            "Key": {
                "restaurant_id": {"S": restaurant_id},
                "window_start": {"N": str(window_start)},
            },
            "UpdateExpression": "SET #ttl = :ttl ADD used_units :add",
            "ExpressionAttributeNames": {"#ttl": "ttl"},
            "ConditionExpression": (
                "(attribute_not_exists(used_units) AND :add <= :max) "
                "OR (used_units <= :limit)"
            ),
            "ExpressionAttributeValues": {
                ":add": {"N": str(add_units)},
                ":max": {"N": str(max_units)},
                ":limit": {"N": str(max_units - add_units)},
                ":ttl": {"N": str(ttl)},
            },
        }

        # 2. Prepare Order Update (From kwargs)
        # We need to manually serialize values because we are using low-level client
        order_update = {
            "TableName": self._orders_table,
            "Key": {"order_id": {"S": order_id}},
            "UpdateExpression": order_update_kwargs["UpdateExpression"],
        }
        
        if "ConditionExpression" in order_update_kwargs:
            order_update["ConditionExpression"] = order_update_kwargs["ConditionExpression"]
            
        if "ExpressionAttributeNames" in order_update_kwargs:
            order_update["ExpressionAttributeNames"] = order_update_kwargs["ExpressionAttributeNames"]
            
        if "ExpressionAttributeValues" in order_update_kwargs:
            # Re-serialize the resource-style values (e.g. "SENT") to client-style ({"S": "SENT"})
            # kwargs values come from dynamo_apply which returns python types if used with Table resource,
            # but wait - dynamo_apply is generic. 
            # If build_update_item_kwargs was designed for Table.update_item, it returns native python types in 'ExpressionAttributeValues'.
            # transact_write_items requires {"S": "foo"} format.
            order_update["ExpressionAttributeValues"] = {
                k: self._av(v) for k, v in order_update_kwargs["ExpressionAttributeValues"].items()
            }

        try:
            self._client.transact_write_items(
                TransactItems=[
                    {"Update": cap_update},
                    {"Update": order_update},
                ]
            )
            return True
        except ClientError as e:
            code = (e.response.get("Error") or {}).get("Code")
            if code in ("TransactionCanceledException", "ConditionalCheckFailedException"):
                # One of the conditions failed (Capacity full OR Order state changed)
                return False
            raise
