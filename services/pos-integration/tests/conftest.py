
import pytest
import os
import sys
import json
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

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
        
        # Condition checks
        if ConditionExpression == 'restaurant_id = :rid':
            rid = ExpressionAttributeValues[':rid']
            if not item or item.get('restaurant_id') != rid:
                raise self._cond_exc("Condition Failed")
        
        if 'AND (#s = :allowed OR #s = :allowed2)' in (ConditionExpression or ''):
             # Force Fire condition check
             rid = ExpressionAttributeValues[':rid']
             allowed = [ExpressionAttributeValues[':allowed'], ExpressionAttributeValues[':allowed2']]
             if not item or item.get('restaurant_id') != rid or item.get('status') not in allowed:
                 raise self._cond_exc("Condition Failed")

        if not item:
             # For some updates we might create? But usually update implies existence in these handlers
             # except menus sync? No menus sync uses put_item.
             # So we assume item exists or raise error if we were strict. 
             # But let's create emptiness for robust mock.
             item = dict(Key)
             self.items[key] = item

        # Apply updates (Simple SET parsing)
        if 'SET' in UpdateExpression:
             # Crude parsing for test needs
             vals = ExpressionAttributeValues or {}
             if ':status' in vals: item['status'] = vals[':status']
             if ':now' in vals: 
                 item['updated_at'] = vals[':now']
                 if 'sent_at = :now' in UpdateExpression: item['sent_at'] = vals[':now']
             if ':v' in vals: item['vicinity'] = vals[':v']
             if ':rm' in vals: item['receipt_mode'] = vals[':rm']


@pytest.fixture
def mock_db():
    orders = InMemoryTable('order_id')
    menus = InMemoryTable('restaurant_id')
    webhooks = InMemoryTable('webhook_id')

    # Patch modules
    local_orders = handlers.orders_table
    local_menus = handlers.menus_table
    local_hooks = handlers.webhook_logs_table
    local_dynamodb = handlers.dynamodb
    
    # Create a mock for the dynamo resource to host the exception class
    mock_ddb_resource = MagicMock()
    # Ensure the exception class matches what InMemoryTable raises
    mock_ddb_resource.meta.client.exceptions.ConditionalCheckFailedException = ConditionalCheckFailedException
    
    handlers.orders_table = orders
    handlers.menus_table = menus
    handlers.webhook_logs_table = webhooks
    handlers.dynamodb = mock_ddb_resource
    
    yield {'orders': orders, 'menus': menus, 'webhooks': webhooks}
    
    handlers.orders_table = local_orders
    handlers.menus_table = local_menus
    handlers.webhook_logs_table = local_hooks
    handlers.dynamodb = local_dynamodb

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
