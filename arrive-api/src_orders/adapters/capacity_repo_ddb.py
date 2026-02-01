import boto3


class CapacityRepoDdb:
    def __init__(self, table_name: str):
        self._table = boto3.resource("dynamodb").Table(table_name)

    def try_reserve_capacity(
        self,
        restaurant_id: str,
        window_start: int,
        add_units: int,
        max_units: int,
        ttl_seconds: int = 6 * 3600,
    ) -> bool:
        ttl = window_start + ttl_seconds

        try:
            self._table.update_item(
                Key={"restaurant_id": restaurant_id, "window_start": window_start},
                UpdateExpression="SET #ttl = :ttl ADD used_units :add",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ConditionExpression=(
                    "(attribute_not_exists(used_units) AND :add <= :max) "
                    "OR (used_units <= :limit)"
                ),
                ExpressionAttributeValues={
                    ":add": add_units,
                    ":max": max_units,
                    ":limit": max_units - add_units,
                    ":ttl": ttl,
                },
            )
            return True
        except Exception as e:
            # Keep lightweight; capacity full is expected in normal operation.
            print(f"CAPACITY_RESERVE_ERROR: {type(e).__name__}: {e}")
            return False

