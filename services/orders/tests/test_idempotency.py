
import json
import time
import pytest
import sys
import os

# Import app logic
sys.path.append(os.path.join(os.path.dirname(__file__), '../src'))
import app
import db

# Reuse fixtures from test_e2e.py (assuming pytest discovers them if in same package? No, needs imports or conftest)
# But test_e2e.py defines its own fixtures locally (which I patched).
# I should import the InMemoryTable class or redefine it?
# Since test_e2e.py is a test file, I can't import from it easily.
# I'll rely on conftest.py if possible, but conftest doesn't have the table.
# I'll redefine the fixtures here or move them to conftest.py. 
# Moving to conftest.py is cleaner but risky to break existing tests if not careful.
# I'll just redefine the crucial parts for this test file to be self-contained and robust.

from unittest.mock import MagicMock
from botocore.exceptions import ClientError

class InMemoryTable:
    def __init__(self, key_name='order_id'):
        self.items = {}
        self.key_name = key_name
        self.meta = MagicMock()
        # Ensure we don't break capacity tests if we shared this class
        # But for this file, we only need ClientError support
        pass

    def put_item(self, Item, ConditionExpression=None, **kwargs):
        key = Item[self.key_name]
        # Condition check for attribute_not_exists (Locking)
        if ConditionExpression and 'attribute_not_exists' in ConditionExpression:
            if key in self.items:
                 raise ClientError(
                     {'Error': {'Code': 'ConditionalCheckFailedException'}},
                     'PutItem'
                 )
        self.items[key] = dict(Item)

    def get_item(self, Key, **kwargs):
        key = Key[self.key_name]
        item = self.items.get(key)
        if item:
            return {'Item': dict(item)}
        return {}

    def update_item(self, Key, UpdateExpression, **kwargs):
        key = Key[self.key_name]
        item = self.items.get(key)
        if not item:
            # Upsert
            item = dict(Key)
            self.items[key] = item
        
        # Simple SET parser for our use case check
        if 'SET' in UpdateExpression:
            expr_vals = kwargs.get('ExpressionAttributeValues', {})
            # We expect SET #s = :s, body = :b
            if ':s' in expr_vals:
                item['status'] = expr_vals[':s']
            if ':b' in expr_vals:
                item['body'] = expr_vals[':b']
            
    def delete_item(self, Key):
        key = Key[self.key_name]
        self.items.pop(key, None)

@pytest.fixture
def mock_tables():
    orders = InMemoryTable('order_id')
    idemp = InMemoryTable('idempotency_key')
    
    # Patch db
    orig_orders = db.orders_table
    orig_idemp = db.idempotency_table
    
    db.orders_table = orders
    db.idempotency_table = idemp
    
    yield {'orders': orders, 'idempotency': idemp}
    
    db.orders_table = orig_orders
    db.idempotency_table = orig_idemp

def _make_event(body=None, headers=None):
    return {
        'routeKey': 'POST /v1/orders',
        'body': json.dumps(body) if body else None,
        'headers': headers or {},
        'requestContext': {
            'authorizer': {'jwt': {'claims': {'sub': 'cust_1'}}}
        }
    }

class TestIdempotency:
    
    def test_create_order_with_idempotency_key(self, mock_tables):
        """First request creates order, second returns cached response."""
        key = "uniq-key-1"
        body = {'restaurant_id': 'rest_1', 'items': [{'id': 'burger', 'qty': 1}]}
        
        # 1. First Request
        event = _make_event(body, headers={'Idempotency-Key': key})
        resp1 = app.lambda_handler(event, None)
        assert resp1['statusCode'] == 201
        order1 = json.loads(resp1['body'])
        order_id1 = order1['order_id']

        # Verify idempotency record exists
        stored = mock_tables['idempotency'].items[key]
        assert stored['status'] == 'COMPLETED'
        assert json.loads(stored['body'])['order_id'] == order_id1

        # 2. Duplicate Request
        resp2 = app.lambda_handler(event, None)
        assert resp2['statusCode'] == 201
        order2 = json.loads(resp2['body'])
        
        # Should be identical
        assert order2['order_id'] == order_id1
        
        # Verify db.orders_table has only 1 order
        assert len(mock_tables['orders'].items) == 1

    def test_concurrent_request_returns_409(self, mock_tables):
        """Simulate concurrent request where lock is held but not completed."""
        key = "uniq-key-2"
        # Manually insert PROCESSING record
        mock_tables['idempotency'].items[key] = {
            'idempotency_key': key,
            'status': 'PROCESSING',
            'created_at': int(time.time()),
            'ttl': int(time.time()) + 999
        }
        
        body = {'restaurant_id': 'rest_1', 'items': [{'id': 'burger', 'qty': 1}]}
        event = _make_event(body, headers={'Idempotency-Key': key})
        
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 409
        assert 'Request in progress' in resp['body']

    def test_failure_releases_lock(self, mock_tables):
        """If creation fails, lock should be deleted."""
        key = "uniq-key-fail"
        body = {'restaurant_id': 'rest_1', 'items': []} # Invalid items -> ValidationError
        
        event = _make_event(body, headers={'Idempotency-Key': key})
        
        # Should return 400
        resp = app.lambda_handler(event, None)
        assert resp['statusCode'] == 400
        
        # Verify idempotency record is gone
        assert key not in mock_tables['idempotency'].items
