import json
import importlib
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
sys.modules.pop('app', None)
sys.modules.pop('handlers', None)
for _loaded in list(sys.modules):
    if _loaded.startswith('handlers.'):
        sys.modules.pop(_loaded, None)

import app
import db


def _event(route_key, role, path_params=None, body=None, assigned_restaurant_id=None):
    path_params = path_params or {}
    claims = {
        "sub": "user_123",
    }
    if role is not None:
        claims["custom:role"] = role
    if role == "restaurant_admin":
        claims["custom:restaurant_id"] = (
            assigned_restaurant_id
            or path_params.get("restaurant_id")
            or "rest_1"
        )
    return {
        "routeKey": route_key,
        "pathParameters": path_params,
        "body": json.dumps(body) if body is not None else None,
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": claims
                }
            }
        },
    }


@pytest.fixture(autouse=True)
def mock_tables():
    global app, db
    for module_name in ("app", "db", "handlers", "handlers.customer", "handlers.restaurant"):
        sys.modules.pop(module_name, None)
    app = importlib.import_module("app")
    db = importlib.import_module("db")

    original_orders = db.orders_table
    original_capacity = db.capacity_table
    original_config = db.config_table
    original_idempotency = db.idempotency_table

    db.orders_table = MagicMock()
    db.capacity_table = MagicMock()
    db.config_table = MagicMock()
    db.idempotency_table = MagicMock()

    yield

    db.orders_table = original_orders
    db.capacity_table = original_capacity
    db.config_table = original_config
    db.idempotency_table = original_idempotency


def test_customer_cannot_access_restaurant_queue():
    event = _event(
        "GET /v1/restaurants/{restaurant_id}/orders",
        role="customer",
        path_params={"restaurant_id": "rest_1"},
    )
    resp = app.lambda_handler(event, None)
    assert resp["statusCode"] == 403


def test_restaurant_admin_cannot_access_other_restaurant_queue():
    event = _event(
        "GET /v1/restaurants/{restaurant_id}/orders",
        role="restaurant_admin",
        path_params={"restaurant_id": "rest_2"},
        assigned_restaurant_id="rest_1",
    )
    resp = app.lambda_handler(event, None)
    assert resp["statusCode"] == 403


def test_restaurant_admin_can_access_own_restaurant_queue():
    db.orders_table.query.return_value = {"Items": []}
    event = _event(
        "GET /v1/restaurants/{restaurant_id}/orders",
        role="restaurant_admin",
        path_params={"restaurant_id": "rest_1"},
        assigned_restaurant_id="rest_1",
    )
    resp = app.lambda_handler(event, None)
    assert resp["statusCode"] == 200


def test_restaurant_admin_cannot_call_customer_create_order():
    event = _event(
        "POST /v1/orders",
        role="restaurant_admin",
        body={"restaurant_id": "rest_1", "items": [{"id": "i1", "qty": 1}]},
        assigned_restaurant_id="rest_1",
    )
    resp = app.lambda_handler(event, None)
    assert resp["statusCode"] == 403


def test_roleless_user_can_call_customer_create_order():
    event = _event(
        "POST /v1/orders",
        role=None,
        body={"restaurant_id": "rest_1", "items": [{"id": "i1", "qty": 1}]},
    )
    resp = app.lambda_handler(event, None)
    assert resp["statusCode"] != 403


def test_customer_cannot_call_restaurant_status_update():
    event = _event(
        "POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status",
        role="customer",
        path_params={"restaurant_id": "rest_1", "order_id": "ord_1"},
        body={"status": "IN_PROGRESS"},
    )
    resp = app.lambda_handler(event, None)
    assert resp["statusCode"] == 403
