import json
import importlib
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
for _module in ("db", "handlers", "handlers.customer"):
    sys.modules.pop(_module, None)

import db


def _event(body):
    return {'body': json.dumps(body)}


@pytest.fixture
def customer_handler(monkeypatch):
    global db
    for _module in ("db", "handlers", "handlers.customer"):
        sys.modules.pop(_module, None)
    db = importlib.import_module("db")
    handler = importlib.import_module("handlers.customer")

    orders_table = MagicMock()
    monkeypatch.setattr(db, "orders_table", orders_table)
    monkeypatch.setattr(db, "capacity_table", MagicMock())
    monkeypatch.setattr(db, "config_table", MagicMock())
    return handler, orders_table


def test_duplicate_event_suppressed_after_dispatch(customer_handler, monkeypatch):
    handler, orders_table = customer_handler
    orders_table.get_item.return_value = {
        'Item': {
            'order_id': 'ord_1',
            'session_id': 'ord_1',
            'customer_id': 'cust_1',
            'restaurant_id': 'rest_1',
            'status': 'SENT_TO_DESTINATION',
            'arrival_status': '5_MIN_OUT',
            'last_arrival_update': 1700000000,
            'expires_at': 1700009999,
        }
    }
    monkeypatch.setattr(handler.time, 'time', lambda: 1700000001)

    response = handler.update_vicinity(
        'ord_1',
        _event({'event': '5_MIN_OUT'}),
        customer_id='cust_1',
    )

    assert response['statusCode'] == 200
    payload = json.loads(response['body'])
    assert payload['suppressed'] is True
    assert payload['suppression_reason'] == 'duplicate_event'
    orders_table.update_item.assert_not_called()


def test_stale_arrival_regression_suppressed(customer_handler, monkeypatch):
    handler, orders_table = customer_handler
    orders_table.get_item.return_value = {
        'Item': {
            'order_id': 'ord_1',
            'session_id': 'ord_1',
            'customer_id': 'cust_1',
            'restaurant_id': 'rest_1',
            'status': 'SENT_TO_DESTINATION',
            'arrival_status': 'AT_DOOR',
            'last_arrival_update': 1700000000,
            'expires_at': 1700009999,
        }
    }
    monkeypatch.setattr(handler.time, 'time', lambda: 1700000010)

    response = handler.update_vicinity(
        'ord_1',
        _event({'event': '5_MIN_OUT'}),
        customer_id='cust_1',
    )

    assert response['statusCode'] == 200
    payload = json.loads(response['body'])
    assert payload['suppressed'] is True
    assert payload['suppression_reason'] == 'stale_arrival_regression'
    orders_table.update_item.assert_not_called()


def test_same_location_source_attaches_customer_notice(customer_handler, monkeypatch):
    handler, orders_table = customer_handler
    orders_table.get_item.return_value = {
        'Item': {
            'order_id': 'ord_1',
            'session_id': 'ord_1',
            'customer_id': 'cust_1',
            'restaurant_id': 'rest_1',
            'status': 'PENDING_NOT_SENT',
            'arrival_status': None,
            'expires_at': 1700009999,
        }
    }

    monkeypatch.setattr(handler.time, 'time', lambda: 1700000000)
    monkeypatch.setattr(
        handler.capacity,
        'get_capacity_config',
        lambda _table, _destination_id: {
            'dispatch_trigger_event': '5_MIN_OUT',
            'capacity_window_seconds': 300,
            'max_concurrent_orders': 3,
        },
    )
    monkeypatch.setattr(
        handler.capacity,
        'check_and_reserve_for_arrival',
        lambda **kwargs: {
            'reserved': True,
            'window_start': 1699999800,
            'window_seconds': 300,
        },
    )

    response = handler.update_vicinity(
        'ord_1',
        _event({'event': 'AT_DOOR', 'source': 'same_location_bootstrap'}),
        customer_id='cust_1',
    )

    assert response['statusCode'] == 200
    payload = json.loads(response['body'])
    notice = payload.get('customer_notice') or {}
    assert notice.get('code') == 'ORDER_DISPATCHED_ON_SITE'
    assert 'already in the restaurant zone' in notice.get('message', '')

    assert orders_table.update_item.call_count == 1
    expr_values = orders_table.update_item.call_args.kwargs.get('ExpressionAttributeValues', {})
    assert 'ORDER_DISPATCHED_ON_SITE' in expr_values.values()
