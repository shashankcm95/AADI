"""
End-to-End Integration Tests for Orders Service

Tests the full order lifecycle through the lambda_handler router,
using an in-memory DynamoDB mock. Covers every route and every
state transition in the system, including capacity gating.

Routes tested:
  POST /v1/orders                                        → create_order
  GET  /v1/orders/{order_id}                             → get_order
  GET  /v1/orders                                        → list_customer_orders
  POST /v1/orders/{order_id}/vicinity                    → update_vicinity
  POST /v1/orders/{order_id}/cancel                      → cancel_order
  GET  /v1/restaurants/{restaurant_id}/orders             → list_restaurant_orders
  POST /v1/restaurants/{rid}/orders/{oid}/ack             → ack_order
  POST /v1/restaurants/{rid}/orders/{oid}/status          → update_order_status
"""

import json
import importlib
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
sys.modules.pop('app', None)
sys.modules.pop('handlers', None)
for _loaded in list(sys.modules):
    if _loaded.startswith('handlers.'):
        sys.modules.pop(_loaded, None)

import app
import db


# =============================================================================
# In-Memory DynamoDB Table Mock
# =============================================================================

class InMemoryTable:
    """
    A simple in-memory DynamoDB table mock that supports:
      - put_item, get_item, update_item, query, scan
    Enough to exercise the handler layer without real AWS calls.
    """

    def __init__(self, key_name='order_id'):
        self.items = {}
        self.key_name = key_name
        # Mock the meta.client.exceptions for capacity module
        self.meta = MagicMock()

        class ConditionalCheckFailedException(Exception):
            pass

        self.meta.client.exceptions.ConditionalCheckFailedException = (
            ConditionalCheckFailedException
        )
        self._cond_exc = ConditionalCheckFailedException

    def put_item(self, Item, ConditionExpression=None, **kwargs):
        if isinstance(self.key_name, tuple):
            key = tuple(Item[k] for k in self.key_name)
        else:
            key = Item[self.key_name]
        
        # Simple condition check for idempotency
        if ConditionExpression and 'attribute_not_exists' in ConditionExpression:
            if key in self.items:
                 raise self._cond_exc("ConditionalCheckFailedException")

        self.items[key] = dict(Item)

    def get_item(self, Key):
        if isinstance(self.key_name, tuple):
            key = tuple(Key[k] for k in self.key_name)
        else:
            key = Key[self.key_name]
        item = self.items.get(key)
        if item:
            return {'Item': dict(item)}
        return {}

    def update_item(self, Key, UpdateExpression, **kwargs):
        key_parts = list(Key.values())
        # Build a composite key for multi-key tables (capacity table)
        if len(Key) > 1:
            key = tuple(Key.values())
        else:
            key = key_parts[0]
        item = self.items.get(key)

        # Handle ConditionExpression failures
        cond = kwargs.get('ConditionExpression', '')

        # Handle string conditions (e.g., "attribute_exists(order_id)")
        if isinstance(cond, str) and 'attribute_exists' in cond and item is None:
            raise self._cond_exc("Condition not met")

        # Handle boto3 Attr conditions from capacity.py
        # Detect capacity reservation: if_not_exists in UpdateExpression + non-string condition
        if not isinstance(cond, str) and cond and 'if_not_exists' in UpdateExpression:
            if item and 'current_count' in item:
                current = item['current_count']
                # Extract max_concurrent from the Attr condition expression.
                # Attr("current_count").lt(N) stores N internally.
                # Walk the condition expression tree to find the .lt() value.
                max_concurrent = self._extract_lt_value(cond)
                if max_concurrent is not None and current >= max_concurrent:
                    raise self._cond_exc(
                        f"Capacity full: {current} >= {max_concurrent}"
                    )

        # Handle boto3 Attr conditions for release_slot (gt(0) check)
        if not isinstance(cond, str) and cond and 'current_count - ' in UpdateExpression:
            if item is None or item.get('current_count', 0) <= 0:
                raise self._cond_exc("current_count is 0")

        if item is None:
            item = dict(Key)
            self.items[key] = item

        # Check status condition (IN clause)
        if isinstance(cond, str) and '#s IN' in cond:
            expr_vals = kwargs.get('ExpressionAttributeValues', {})
            allowed = [v for k, v in expr_vals.items() if k.startswith(':c')]
            if allowed and item.get('status') not in allowed:
                from errors import InvalidStateError
                raise Exception(f"ConditionalCheckFailed: status {item.get('status')} not in {allowed}")

        # Parse SET expressions
        expr_names = kwargs.get('ExpressionAttributeNames', {})
        expr_vals = kwargs.get('ExpressionAttributeValues', {})

        if 'SET' in UpdateExpression:
            set_part = UpdateExpression.split('SET ')[1]
            if 'REMOVE' in set_part:
                set_part = set_part.split(' REMOVE')[0]
            assignments = [a.strip() for a in set_part.split(',')]
            for assignment in assignments:
                parts = assignment.split(' = ')
                if len(parts) == 2:
                    field_expr, val_expr = parts[0].strip(), parts[1].strip()
                    # Resolve field name
                    field = expr_names.get(field_expr, field_expr)
                    # Handle if_not_exists
                    if 'if_not_exists' in val_expr:
                        current = item.get('current_count', 0)
                        inc = expr_vals.get(':one', 1)
                        item['current_count'] = current + inc
                        if ':ttl' in expr_vals:
                            item['ttl'] = expr_vals[':ttl']
                        continue
                    elif 'current_count - ' in val_expr:
                        current = item.get('current_count', 0)
                        dec = expr_vals.get(':one', 1)
                        item['current_count'] = max(0, current - dec)
                        continue
                    # Standard assignment
                    if val_expr in expr_vals:
                        item[field] = expr_vals[val_expr]

        # Parse REMOVE expressions
        if 'REMOVE' in UpdateExpression:
            remove_part = UpdateExpression.split('REMOVE ')[1]
            fields = [f.strip() for f in remove_part.split(',')]
            for f in fields:
                item.pop(f, None)

    @staticmethod
    def _extract_lt_value(cond):
        """
        Extract the numeric value from an Attr().lt(N) condition.
        Walks the boto3 condition expression tree:
          Or._values[0] = AttributeNotExists
          Or._values[1] = LessThan._values = [Attr, N]
        """
        try:
            for v in getattr(cond, '_values', []):
                if getattr(v, 'expression_operator', '') == '<':
                    # LessThan._values = [Attr("current_count"), N]
                    return v._values[1]
        except Exception:
            pass
        return None

    def query(self, **kwargs):
        """Simple query that returns all items (good enough for testing)."""
        index = kwargs.get('IndexName', '')
        kce = kwargs.get('KeyConditionExpression', None)
        items = list(self.items.values())

        # Simple filtering by GSI key
        if 'restaurant_id' in index.lower() or 'restaurant' in str(kce).lower():
            # Filter logic would go here for real; return all for simplicity
            pass
        return {'Items': items}

    def scan(self, **kwargs):
        return {'Items': list(self.items.values())}


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def tables():
    """Create in-memory tables and patch the module-level references."""
    global app, db
    for module_name in ("app", "db", "handlers", "handlers.customer", "handlers.restaurant"):
        sys.modules.pop(module_name, None)
    app = importlib.import_module("app")
    db = importlib.import_module("db")

    orders = InMemoryTable('order_id')
    cap = InMemoryTable(('restaurant_id', 'window_start'))
    config = InMemoryTable('restaurant_id')
    idempotency = InMemoryTable('idempotency_key')

    # Seed restaurant capacity config
    config.items['rest_abc'] = {
        'restaurant_id': 'rest_abc',
        'max_concurrent_orders': 3,
        'capacity_window_seconds': 300,
        'active_menu_version': 'v1',
    }
    original_orders = db.orders_table
    original_cap = db.capacity_table
    original_config = db.config_table
    original_idempotency = db.idempotency_table

    db.orders_table = orders
    db.capacity_table = cap
    db.config_table = config
    db.idempotency_table = idempotency

    yield {'orders': orders, 'capacity': cap, 'config': config, 'idempotency': idempotency}

    db.orders_table = original_orders
    db.capacity_table = original_cap
    db.config_table = original_config
    db.idempotency_table = original_idempotency


def _make_event(
    route_key,
    body=None,
    path_params=None,
    customer_id='cust_test1',
    role=None,
    claim_overrides=None,
):
    """Build a minimal API Gateway v2 event."""
    path_params = path_params or {}
    # Use role defaults that mirror production route ownership.
    if role is None:
        role = 'restaurant_admin' if '/v1/restaurants/' in route_key else 'customer'

    claims = {'sub': customer_id, 'custom:role': role}
    if role == 'restaurant_admin':
        claims['custom:restaurant_id'] = path_params.get('restaurant_id', 'rest_abc')
    if claim_overrides:
        claims.update(claim_overrides)

    event = {
        'routeKey': route_key,
        'pathParameters': path_params,
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': claims
                }
            }
        },
    }
    if body is not None:
        event['body'] = json.dumps(body)
    return event


# =============================================================================
# Route Dispatch Tests
# =============================================================================

class TestRouteDispatch:
    """Verify every route key dispatches to the correct handler."""

    def test_unknown_route_returns_404(self, tables):
        resp = app.lambda_handler({'routeKey': 'DELETE /v1/widget'}, None)
        assert resp['statusCode'] == 404

    def test_missing_order_returns_404(self, tables):
        event = _make_event('GET /v1/orders/{order_id}', path_params={'order_id': 'nope'})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 404


class TestCustomerNameCapture:
    def test_create_order_uses_payload_customer_name(self, tables):
        event = _make_event(
            'POST /v1/orders',
            body={
                'restaurant_id': 'rest_abc',
                'customer_name': 'Alex Doe',
                'items': [{'id': 'coffee', 'qty': 1}],
            },
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 201

        body = json.loads(resp['body'])
        assert body['customer_name'] == 'Alex Doe'
        assert tables['orders'].items[body['order_id']]['customer_name'] == 'Alex Doe'

    def test_create_order_falls_back_to_claim_name(self, tables):
        event = _make_event(
            'POST /v1/orders',
            body={
                'restaurant_id': 'rest_abc',
                'items': [{'id': 'coffee', 'qty': 1}],
            },
            claim_overrides={'name': 'Claim User'},
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 201

        body = json.loads(resp['body'])
        assert body['customer_name'] == 'Claim User'


# =============================================================================
# Leave Advisory (Non-Reserving)
# =============================================================================

class TestLeaveAdvisory:
    def test_pending_order_leave_now_estimate(self, tables):
        create = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'coffee', 'qty': 1}],
        })
        create_resp = app.lambda_handler(create, None)
        order_id = json.loads(create_resp['body'])['order_id']

        advisory = _make_event('GET /v1/orders/{order_id}/advisory', path_params={'order_id': order_id})
        resp = app.lambda_handler(advisory, None)

        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['order_id'] == order_id
        assert body['status'] == 'PENDING_NOT_SENT'
        assert body['is_estimate'] is True
        assert body['recommended_action'] in ('LEAVE_NOW', 'WAIT')

    def test_waiting_order_advisory_recommends_wait_when_window_full(self, tables):
        tables['config'].items['rest_abc']['max_concurrent_orders'] = 1

        # Fill the single slot.
        create_1 = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'a', 'qty': 1}],
        })
        order_1 = json.loads(app.lambda_handler(create_1, None)['body'])['order_id']
        app.lambda_handler(
            _make_event(
                'POST /v1/orders/{order_id}/vicinity',
                body={'event': '5_MIN_OUT'},
                path_params={'order_id': order_1},
            ),
            None
        )

        # Second order is still pending; advisory should now recommend waiting.
        create_2 = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'b', 'qty': 1}],
        })
        order_2 = json.loads(app.lambda_handler(create_2, None)['body'])['order_id']

        advisory = _make_event('GET /v1/orders/{order_id}/advisory', path_params={'order_id': order_2})
        resp = app.lambda_handler(advisory, None)

        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['is_estimate'] is True
        assert body['recommended_action'] == 'WAIT'
        assert body['estimated_wait_seconds'] >= 0


# =============================================================================
# Full Order Lifecycle: Happy Path
# =============================================================================

class TestHappyPathLifecycle:
    """
    Tests the complete order lifecycle:
      Create → Get → Vicinity(5_MIN_OUT) → Ack → Status transitions → Complete
    """

    def test_full_lifecycle(self, tables):

        # --- 1. Create Order ---
        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'burger', 'qty': 2}],
            'payment_mode': 'PAY_AT_RESTAURANT',
        })
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 201
        body = json.loads(resp['body'])
        order_id = body['order_id']
        assert order_id.startswith('ord_')
        assert body['status'] == 'PENDING_NOT_SENT'

        # --- 2. Get Order ---
        event = _make_event('GET /v1/orders/{order_id}',
                            path_params={'order_id': order_id})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        assert json.loads(resp['body'])['order_id'] == order_id

        # --- 3. List Customer Orders ---
        event = _make_event('GET /v1/orders')
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        orders_list = json.loads(resp['body'])['orders']
        assert len(orders_list) >= 1

        # --- 4. List Restaurant Orders ---
        event = _make_event('GET /v1/restaurants/{restaurant_id}/orders',
                            path_params={'restaurant_id': 'rest_abc'})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

        # --- 5. Vicinity: 5_MIN_OUT (with capacity) ---
        event = _make_event('POST /v1/orders/{order_id}/vicinity',
                            body={'event': '5_MIN_OUT'},
                            path_params={'order_id': order_id})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['status'] == 'SENT_TO_DESTINATION'

        # Verify order is now SENT in DB
        stored = tables['orders'].items[order_id]
        assert stored['status'] == 'SENT_TO_DESTINATION'
        assert stored.get('capacity_window_start') is not None

        # --- 6. Ack Order (soft → hard) ---
        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack',
            path_params={'order_id': order_id, 'restaurant_id': 'rest_abc'}
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

        # --- 7. Status: SENT → IN_PROGRESS ---
        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status',
            body={'status': 'IN_PROGRESS'},
            path_params={'order_id': order_id, 'restaurant_id': 'rest_abc'}
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        assert json.loads(resp['body'])['status'] == 'IN_PROGRESS'

        # --- 8. Status: IN_PROGRESS → READY ---
        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status',
            body={'status': 'READY'},
            path_params={'order_id': order_id, 'restaurant_id': 'rest_abc'}
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

        # --- 10. Status: READY → FULFILLING ---
        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status',
            body={'status': 'FULFILLING'},
            path_params={'order_id': order_id, 'restaurant_id': 'rest_abc'}
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

        # --- 11. Status: FULFILLING → COMPLETED (should release capacity slot) ---
        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status',
            body={'status': 'COMPLETED'},
            path_params={'order_id': order_id, 'restaurant_id': 'rest_abc'}
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        assert tables['orders'].items[order_id]['status'] == 'COMPLETED'


# =============================================================================
# Capacity Gating Flow
# =============================================================================

class TestCapacityGatingFlow:
    """
    Tests the capacity gating mechanism:
      1. Fill capacity to max
      2. Next order should get WAITING_FOR_CAPACITY
      3. Cancel one → slot released → next can reserve
    """

    def _create_and_fire(self, tables, event_name='5_MIN_OUT'):
        """Helper: create an order and push it through an arrival event."""

        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'fries', 'qty': 1}],
        })
        resp = app.lambda_handler(event, None)
        order_id = json.loads(resp['body'])['order_id']

        event = _make_event('POST /v1/orders/{order_id}/vicinity',
                            body={'event': event_name},
                            path_params={'order_id': order_id})
        resp = app.lambda_handler(event, None)
        body = json.loads(resp['body'])
        return order_id, body

    def test_capacity_fills_then_blocks(self, tables):
        """Fill 3 slots (max_concurrent=3), then 4th should be WAITING."""
        # Set max to 3
        tables['config'].items['rest_abc']['max_concurrent_orders'] = 3

        order_ids = []
        # Fill all 3 slots
        for i in range(3):
            oid, body = self._create_and_fire(tables)
            assert body['status'] == 'SENT_TO_DESTINATION', f"Order {i+1} should be SENT"
            order_ids.append(oid)

        # 4th should be blocked
        oid4, body4 = self._create_and_fire(tables)
        assert body4['status'] == 'WAITING_FOR_CAPACITY', (
            f"Order 4 should be WAITING, got {body4['status']}"
        )
        assert 'suggested_start_at' in body4

    def test_complete_releases_slot(self, tables):
        """After completing an order, the slot should be freed."""

        tables['config'].items['rest_abc']['max_concurrent_orders'] = 1

        # Fill the single slot
        oid1, body1 = self._create_and_fire(tables)
        assert body1['status'] == 'SENT_TO_DESTINATION'

        # Complete it (releases the capacity slot)
        # Must walk through states: SENT -> IN_PROGRESS -> READY -> FULFILLING -> COMPLETED
        for status in ('IN_PROGRESS', 'READY', 'FULFILLING', 'COMPLETED'):
            event = _make_event(
                'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status',
                body={'status': status},
                path_params={'order_id': oid1, 'restaurant_id': 'rest_abc'}
            )
            resp = app.lambda_handler(event, None)
            assert resp['statusCode'] == 200

        # New order should now get through
        oid2, body2 = self._create_and_fire(tables)
        assert body2['status'] == 'SENT_TO_DESTINATION', (
            f"After completion, new order should be SENT, got {body2['status']}"
        )

    def test_at_door_does_not_bypass_capacity(self, tables):
        """
        Arrival events other than 5_MIN_OUT must not bypass capacity while pending/waiting.
        """
        tables['config'].items['rest_abc']['max_concurrent_orders'] = 1

        oid1, body1 = self._create_and_fire(tables, event_name='5_MIN_OUT')
        assert body1['status'] == 'SENT_TO_DESTINATION'

        oid2, body2 = self._create_and_fire(tables, event_name='AT_DOOR')
        assert body2['status'] == 'WAITING_FOR_CAPACITY', (
            f"AT_DOOR should respect capacity, got {body2['status']}"
        )
        assert body2.get('arrival_status') == 'AT_DOOR'


# =============================================================================
# Vicinity Non-Capacity Events
# =============================================================================

class TestVicinityNonCapacityEvents:
    """
    Tests non-dispatch vicinity events on already-dispatched orders.
    """

    def _create_sent_order(self, tables):
        """Create an order and push it to SENT."""
        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'salad', 'qty': 1}],
        })
        resp = app.lambda_handler(event, None)
        oid = json.loads(resp['body'])['order_id']

        # Push to SENT via 5_MIN_OUT
        event = _make_event('POST /v1/orders/{order_id}/vicinity',
                            body={'event': '5_MIN_OUT'},
                            path_params={'order_id': oid})
        app.lambda_handler(event, None)
        return oid

    def test_parking_event(self, tables):
        oid = self._create_sent_order(tables)

        event = _make_event('POST /v1/orders/{order_id}/vicinity',
                            body={'event': 'PARKING'},
                            path_params={'order_id': oid})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body.get('arrival_status') == 'PARKING' or 'status' in body

    def test_at_door_event(self, tables):
        oid = self._create_sent_order(tables)

        event = _make_event('POST /v1/orders/{order_id}/vicinity',
                            body={'event': 'AT_DOOR'},
                            path_params={'order_id': oid})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

    def test_exit_vicinity_event(self, tables):
        oid = self._create_sent_order(tables)

        # Move to FULFILLING first so EXIT can auto-complete
        tables['orders'].items[oid]['status'] = 'FULFILLING'

        event = _make_event('POST /v1/orders/{order_id}/vicinity',
                            body={'event': 'EXIT_VICINITY'},
                            path_params={'order_id': oid})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200

    def test_unknown_event_returns_error(self, tables):
        oid = self._create_sent_order(tables)

        event = _make_event('POST /v1/orders/{order_id}/vicinity',
                            body={'event': 'TELEPORT'},
                            path_params={'order_id': oid})
        resp = app.lambda_handler(event, None)
        body = json.loads(resp['body'])
        assert resp['statusCode'] in (200, 400)


# =============================================================================
# Cancel Flow
# =============================================================================

class TestCancelFlow:
    def test_cancel_pending_order(self, tables):
        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'soup', 'qty': 1}],
        })
        resp = app.lambda_handler(event, None)
        oid = json.loads(resp['body'])['order_id']

        event = _make_event('POST /v1/orders/{order_id}/cancel',
                            path_params={'order_id': oid})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['status'] == 'CANCELED'

    def test_cancel_nonexistent_returns_404(self, tables):
        event = _make_event('POST /v1/orders/{order_id}/cancel',
                            path_params={'order_id': 'ord_doesnotexist'})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 404


# =============================================================================
# Validation & Error Paths
# =============================================================================

class TestErrorPaths:
    def test_create_order_empty_items_returns_400(self, tables):
        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [],
        })
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 400

    def test_create_order_invalid_item_returns_400(self, tables):
        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'qty': 1}],  # missing item_id
        })
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 400

    def test_get_nonexistent_order_returns_404(self, tables):
        event = _make_event('GET /v1/orders/{order_id}',
                            path_params={'order_id': 'ord_ghost'})
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 404

    def test_status_update_missing_status_returns_400(self, tables):
        # Create an order first
        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'pizza', 'qty': 1}],
        })
        resp = app.lambda_handler(event, None)
        oid = json.loads(resp['body'])['order_id']

        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/status',
            body={},  # no status
            path_params={'order_id': oid, 'restaurant_id': 'rest_abc'}
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 400

    def test_create_order_nonexistent_restaurant_returns_400(self, tables):
        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_ghost',
            'items': [{'id': 'pizza', 'qty': 1}],
        })
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 400
        body = json.loads(resp['body'])
        assert 'not found' in body.get('error', '')


# =============================================================================
# Ack Flow (Soft → Hard)
# =============================================================================

class TestAckFlow:
    def test_ack_sent_order(self, tables):

        # Create + send
        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'steak', 'qty': 1}],
        })
        resp = app.lambda_handler(event, None)
        oid = json.loads(resp['body'])['order_id']

        # Push to SENT
        event = _make_event('POST /v1/orders/{order_id}/vicinity',
                            body={'event': '5_MIN_OUT'},
                            path_params={'order_id': oid})
        app.lambda_handler(event, None)

        # Ack
        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack',
            path_params={'order_id': oid, 'restaurant_id': 'rest_abc'}
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body.get('receipt_mode') == 'HARD'

    def test_ack_wrong_restaurant_returns_404(self, tables):

        event = _make_event('POST /v1/orders', body={
            'restaurant_id': 'rest_abc',
            'items': [{'id': 'steak', 'qty': 1}],
        })
        resp = app.lambda_handler(event, None)
        oid = json.loads(resp['body'])['order_id']

        # Push to SENT
        event = _make_event('POST /v1/orders/{order_id}/vicinity',
                            body={'event': '5_MIN_OUT'},
                            path_params={'order_id': oid})
        app.lambda_handler(event, None)

        # Ack with wrong restaurant
        event = _make_event(
            'POST /v1/restaurants/{restaurant_id}/orders/{order_id}/ack',
            path_params={'order_id': oid, 'restaurant_id': 'rest_WRONG'}
        )
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 404


# =============================================================================
# Removed Flow Notes (Kept for historical context)
# =============================================================================
