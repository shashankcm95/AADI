
import pytest
import os
import sys
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import app

# ---------------------------------------------------------------------------
# In-Memory DynamoDB Table Mock
# ---------------------------------------------------------------------------
class InMemoryTable:
    def __init__(self, key_name='restaurant_id'):
        self.items = {}
        self.key_name = key_name

    def put_item(self, Item, **kwargs):
        key = Item[self.key_name]
        self.items[key] = dict(Item)

    def get_item(self, Key):
        key = Key[self.key_name]
        item = self.items.get(key)
        if item:
            return {'Item': dict(item)}
        return {}

    def scan(self, FilterExpression=None, ExpressionAttributeValues=None):
        items = list(self.items.values())
        if FilterExpression == 'active = :a':
            val = ExpressionAttributeValues[':a']
            items = [i for i in items if i.get('active') == val]
        return {'Items': items}


@pytest.fixture
def mock_tables():
    restaurants = InMemoryTable('restaurant_id')
    menus = InMemoryTable('restaurant_id') # composite key in real life, but simplified mock
    config = InMemoryTable('restaurant_id')

    # Seed data for test_restaurants_list
    restaurants.items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}
    restaurants.items['r2'] = {'restaurant_id': 'r2', 'name': 'Rest 2', 'active': True}
    restaurants.items['r3'] = {'restaurant_id': 'r3', 'name': 'Rest 3', 'active': True}

    # Patch modules
    app.restaurants_table = restaurants
    app.menus_table = menus
    app.config_table = config
    
    yield {'restaurants': restaurants, 'menus': menus, 'config': config}
    
    # No cleanup needed as we modified the module variables directly and they will be reset next run or we can reset them if needed. 
    # But for now this is sufficient.
