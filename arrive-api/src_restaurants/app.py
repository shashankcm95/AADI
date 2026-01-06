import json
import os
import boto3
from decimal import Decimal


ddb = boto3.resource("dynamodb")

RESTAURANTS_TABLE = os.environ["RESTAURANTS_TABLE"]
MENUS_TABLE = os.environ["MENUS_TABLE"]
CONFIG_TABLE = os.environ["RESTAURANT_CONFIG_TABLE"]

def _json_default(o):
    if isinstance(o, Decimal):
        # Convert DynamoDB Decimals to int if whole number, else float
        if o % 1 == 0:
            return int(o)
        return float(o)
    return str(o)

def _resp(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }

def lambda_handler(event, context):
    path = event.get("rawPath") or event.get("path") or ""
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "")

    if method == "GET" and path == "/v1/restaurants":
        return list_restaurants()

    # /v1/restaurants/{id}/menu
    if method == "GET" and path.startswith("/v1/restaurants/") and path.endswith("/menu"):
        parts = path.split("/")
        # ["", "v1", "restaurants", "{id}", "menu"]
        if len(parts) >= 5:
            restaurant_id = parts[3]
            return get_active_menu(restaurant_id)

    return _resp(404, {"error": {"code": "NOT_FOUND", "message": "Route not found"}})


def list_restaurants():
    table = ddb.Table(RESTAURANTS_TABLE)

    # OK for Sprint 1: tiny dataset. Later we’ll add a GSI or a separate index table.
    resp = table.scan()
    items = resp.get("Items", [])

    return _resp(200, {"restaurants": items})


def get_active_menu(restaurant_id: str):
    cfg_table = ddb.Table(CONFIG_TABLE)
    cfg = cfg_table.get_item(Key={"restaurant_id": restaurant_id}).get("Item")

    if not cfg or "active_menu_version" not in cfg:
        return _resp(404, {"error": {"code": "MENU_NOT_FOUND", "message": "No active menu configured"}})

    menu_version = cfg["active_menu_version"]

    menu_table = ddb.Table(MENUS_TABLE)
    menu_item = menu_table.get_item(
        Key={"restaurant_id": restaurant_id, "menu_version": menu_version}
    ).get("Item")

    if not menu_item:
        return _resp(404, {"error": {"code": "MENU_NOT_FOUND", "message": "Menu not found for active version"}})

    return _resp(
        200,
        {
            "restaurant_id": restaurant_id,
            "menu_version": menu_version,
            "menu": menu_item.get("menu", {}),
        },
    )

