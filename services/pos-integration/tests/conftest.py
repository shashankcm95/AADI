
import pytest
import os
import sys
import json
import importlib
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Avoid cross-service module collisions when running full-repo pytest.
for module_name in ("app", "handlers", "auth", "pos_mapper"):
    sys.modules.pop(module_name, None)

import app
import handlers

# Global exception class for consistency
class ConditionalCheckFailedException(Exception):
    pass

# ---------------------------------------------------------------------------
# In-Memory DynamoDB Table Mock (Simpler version for POS tests)
# ---------------------------------------------------------------------------
class InMemoryTable:
    def __init__(self, key_name='order_id'):
        self.items = {}
        self.key_name = key_name
        self.meta = MagicMock()
        
        # Mock exceptions
        from botocore.exceptions import ClientError
        self._client_error = ClientError
        self.meta.client.exceptions.ConditionalCheckFailedException = ConditionalCheckFailedException
        self._cond_exc = ConditionalCheckFailedException

    def put_item(self, Item, ConditionExpression=None, **kwargs):
        key = Item[self.key_name]
        
        # Simple condition check
        if ConditionExpression == 'attribute_not_exists(webhook_id)':
             if key in self.items:
                 raise self._cond_exc("ConditionalCheckFailedException")

        self.items[key] = dict(Item)

    def get_item(self, Key):
        key = Key[self.key_name]
        item = self.items.get(key)
        if item:
            return {'Item': dict(item)}
        return {}

    def scan(self, FilterExpression=None, ExpressionAttributeValues=None):
        # Very simple scan mock - filtering by restaurant_id
        items = list(self.items.values())
        if FilterExpression == 'restaurant_id = :rid':
            rid = ExpressionAttributeValues[':rid']
            items = [i for i in items if i.get('restaurant_id') == rid]
        return {'Items': items}

    def query(self, IndexName=None, KeyConditionExpression=None, ExpressionAttributeValues=None, **kwargs):
        # Mock query support for GSI_RestaurantStatus
        items = list(self.items.values())
        
        # Parse simple key condition: restaurant_id = :rid
        if 'restaurant_id = :rid' in KeyConditionExpression:
             rid = ExpressionAttributeValues[':rid']
             items = [i for i in items if i.get('restaurant_id') == rid]
             
             # Optional sort key filter: AND status = :status
             if 'AND #s = :status' in KeyConditionExpression or 'AND status = :status' in KeyConditionExpression:
                 status = ExpressionAttributeValues.get(':status')
                 if status:
                     items = [i for i in items if i.get('status') == status]

        return {'Items': items, 'Count': len(items)}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues=None, ConditionExpression=None, **kwargs):
        key = Key[self.key_name]
        item = self.items.get(key)
        names = kwargs.get('ExpressionAttributeNames') or {}
        values = ExpressionAttributeValues or {}
        
        # Condition checks
        cond = ConditionExpression or ''
        if 'restaurant_id = :rid' in cond:
            rid = values.get(':rid')
            if not item or item.get('restaurant_id') != rid:
                raise self._cond_exc("Condition Failed")

        if '#s = :allowed' in cond:
            allowed = values.get(':allowed')
            if not item or item.get('status') != allowed:
                raise self._cond_exc("Condition Failed")
        elif '#s = :allowed1' in cond and '#s = :allowed2' in cond:
            allowed = {values.get(':allowed1'), values.get(':allowed2')}
            if not item or item.get('status') not in allowed:
                raise self._cond_exc("Condition Failed")
        elif 'AND (#s = :allowed OR #s = :allowed2)' in cond:
            # Backward compatibility for older test expressions
            allowed = {values.get(':allowed'), values.get(':allowed2')}
            if not item or item.get('status') not in allowed:
                raise self._cond_exc("Condition Failed")

        if not item:
             # For some updates we might create? But usually update implies existence in these handlers
             # except menus sync? No menus sync uses put_item.
             # So we assume item exists or raise error if we were strict. 
             # But let's create emptiness for robust mock.
             item = dict(Key)
             self.items[key] = item

        # Apply updates (supports generic aliased SET syntax)
        if 'SET' in UpdateExpression:
             set_expr = UpdateExpression.split('SET', 1)[1].strip()
             for assignment in set_expr.split(','):
                 clause = assignment.strip()
                 if not clause or '=' not in clause:
                     continue
                 left, right = [x.strip() for x in clause.split('=', 1)]
                 field_name = names.get(left, left)
                 if right in values:
                     item[field_name] = values[right]


class InMemoryCapacityTable:
    def __init__(self):
        self.items = {}

    def update_item(self, Key, UpdateExpression, ConditionExpression=None, ExpressionAttributeValues=None, **kwargs):
        restaurant_id = Key['restaurant_id']
        window_start = Key['window_start']
        composite = (restaurant_id, int(window_start))
        item = self.items.get(composite) or {}
        current = int(item.get('current_count', 0))
        if current <= 0:
            raise ConditionalCheckFailedException("Condition Failed")
        decrement = int((ExpressionAttributeValues or {}).get(':one', 1))
        item['current_count'] = max(0, current - decrement)
        self.items[composite] = item


@pytest.fixture
def mock_db():
    active_handlers = importlib.import_module("handlers")

    orders = InMemoryTable('order_id')
    menus = InMemoryTable('restaurant_id')
    webhooks = InMemoryTable('webhook_id')
    capacity = InMemoryCapacityTable()

    # Patch modules
    local_orders = active_handlers.orders_table
    local_menus = active_handlers.menus_table
    local_hooks = active_handlers.webhook_logs_table
    local_capacity = active_handlers.capacity_table
    local_dynamodb = active_handlers.dynamodb
    
    # Create a mock for the dynamo resource to host the exception class
    mock_ddb_resource = MagicMock()
    # Ensure the exception class matches what InMemoryTable raises
    mock_ddb_resource.meta.client.exceptions.ConditionalCheckFailedException = ConditionalCheckFailedException
    
    active_handlers.orders_table = orders
    active_handlers.menus_table = menus
    active_handlers.webhook_logs_table = webhooks
    active_handlers.capacity_table = capacity
    active_handlers.dynamodb = mock_ddb_resource
    
    yield {'orders': orders, 'menus': menus, 'webhooks': webhooks, 'capacity': capacity}
    
    active_handlers.orders_table = local_orders
    active_handlers.menus_table = local_menus
    active_handlers.webhook_logs_table = local_hooks
    active_handlers.capacity_table = local_capacity
    active_handlers.dynamodb = local_dynamodb

@pytest.fixture
def mock_auth():
    """Helper to create authenticated events"""
    def _create_event(route_key, body=None, api_key='valid-key', path_params=None, query_params=None):
        return {
            'routeKey': route_key,
            'headers': {'X-POS-API-Key': api_key},
            'body': json.dumps(body) if body else None,
            'pathParameters': path_params,
            'queryStringParameters': query_params
        }
    return _create_event
