from typing import Tuple
import boto3


class ConfigRepoDdb:
    def __init__(self, table_name: str):
        self._table = boto3.resource("dynamodb").Table(table_name)

    def get_capacity_config(self, restaurant_id: str) -> Tuple[int, int]:
        item = self._table.get_item(Key={"restaurant_id": restaurant_id}).get("Item") or {}
        window_seconds = int(item.get("capacity_window_seconds", 600))
        max_units = int(item.get("max_prep_units_per_window", 20))
        return window_seconds, max_units

