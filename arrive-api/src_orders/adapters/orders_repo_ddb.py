from typing import Any, Dict, List, Optional
import boto3
from boto3.dynamodb.conditions import Key


class OrdersRepoDdb:
    def __init__(self, table_name: str):
        self._table = boto3.resource("dynamodb").Table(table_name)

    def put_order(self, item: Dict[str, Any]) -> None:
        self._table.put_item(Item=item)

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        return self._table.get_item(Key={"order_id": order_id}).get("Item")

    def update_order(self, **kwargs):
        # passthrough helper to allow direct update_item usage
        return self._table.update_item(**kwargs)

    def query_by_restaurant_status(self, restaurant_id: str, status: str) -> List[Dict[str, Any]]:
        res = self._table.query(
            IndexName="GSI_RestaurantStatus",
            KeyConditionExpression=Key("restaurant_id").eq(restaurant_id) & Key("status").eq(status),
        )
        return res.get("Items", [])

