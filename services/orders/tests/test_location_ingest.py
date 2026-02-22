import json
import importlib
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
for _module in ("db", "handlers", "handlers.customer", "location_bridge"):
    sys.modules.pop(_module, None)

import db
from errors import NotFoundError


def _event(body):
    return {
        'body': json.dumps(body),
    }


@pytest.fixture
def customer_handler(monkeypatch):
    global db
    for _module in ("db", "handlers", "handlers.customer", "location_bridge"):
        sys.modules.pop(_module, None)
    db = importlib.import_module("db")
    handler = importlib.import_module("handlers.customer")
    bridge = importlib.import_module("location_bridge")

    orders_table = MagicMock()
    monkeypatch.setattr(db, "orders_table", orders_table)
    monkeypatch.setattr(
        bridge,
        "publish_device_position",
        lambda **kwargs: {"published": True, "tracker_enabled": True},
    )

    return handler, orders_table


def test_ingest_location_persists_and_publishes(customer_handler):
    handler, orders_table = customer_handler
    orders_table.get_item.return_value = {
        'Item': {
            'order_id': 'ord_1',
            'customer_id': 'cust_1',
            'restaurant_id': 'rest_1',
            'status': 'PENDING_NOT_SENT',
        }
    }

    response = handler.ingest_location(
        'ord_1',
        _event({
            'latitude': 30.2672,
            'longitude': -97.7431,
            'accuracy_m': 12.5,
            'speed_mps': 6.2,
            'sample_time': 1700000000123,
        }),
        customer_id='cust_1',
    )

    assert response['statusCode'] == 202
    payload = json.loads(response['body'])
    assert payload['published_to_location'] is True
    assert payload['received'] is True

    kwargs = orders_table.update_item.call_args.kwargs
    values = kwargs['ExpressionAttributeValues']
    assert values[':lat'] == Decimal('30.2672')
    assert values[':lon'] == Decimal('-97.7431')
    assert values[':acc'] == Decimal('12.5')
    assert values[':speed'] == Decimal('6.2')
    # Converted from milliseconds to seconds.
    assert values[':sample'] == 1700000000


def test_ingest_location_rejects_bad_payload(customer_handler):
    handler, _ = customer_handler
    response = handler.ingest_location('ord_1', _event({'latitude': 'NaN'}), customer_id='cust_1')
    assert response['statusCode'] == 400


def test_ingest_location_enforces_ownership(customer_handler):
    handler, orders_table = customer_handler
    orders_table.get_item.return_value = {
        'Item': {
            'order_id': 'ord_1',
            'customer_id': 'cust_owner',
            'restaurant_id': 'rest_1',
        }
    }

    with pytest.raises(NotFoundError):
        handler.ingest_location(
            'ord_1',
            _event({'latitude': 30.26, 'longitude': -97.74}),
            customer_id='cust_other',
        )
