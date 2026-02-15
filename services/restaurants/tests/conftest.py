
import pytest
import os
import sys
import importlib
from unittest.mock import MagicMock

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Avoid cross-service module collisions when running full-repo pytest.
for module_name in ("app",):
    sys.modules.pop(module_name, None)

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

    def query(self, IndexName=None, KeyConditionExpression=None, ExpressionAttributeValues=None):
        items = []
        # Primitive query mock for GSI_ActiveRestaurants
        if IndexName == 'GSI_ActiveRestaurants':
             # Return all items where is_active == "1"
             for item in self.items.values():
                 if item.get('is_active') == "1":
                     items.append(item)
        elif IndexName == 'GSI_Cuisine':
             target_val = None
             if KeyConditionExpression:
                 try:
                     target_val = KeyConditionExpression._values[1]
                 except:
                     pass
             
             if target_val:
                 for item in self.items.values():
                     if item.get('cuisine') == target_val:
                         items.append(item)
                         
        elif IndexName == 'GSI_PriceTier':
             target_val = None
             try:
                 target_val = KeyConditionExpression._values[1]
             except:
                 pass
                 
             if target_val:
                 for item in self.items.values():
                     if item.get('price_tier') == target_val:
                         items.append(item)
        return {'Items': items}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames=None, ExpressionAttributeValues=None):
        key = Key[self.key_name]
        if key not in self.items:
            self.items[key] = {self.key_name: key}
        
        item = self.items[key]
        
        # 1. Handle SET
        if "SET" in UpdateExpression:
            set_part = UpdateExpression.split("SET")[1].split("REMOVE")[0]
            updates = set_part.split(",")
            for update in updates:
                parts = update.split("=")
                if len(parts) == 2:
                    k = parts[0].strip()
                    v_placeholder = parts[1].strip()
                    
                    if ExpressionAttributeNames and k in ExpressionAttributeNames:
                        k = ExpressionAttributeNames[k]
                    
                    if ExpressionAttributeValues and v_placeholder in ExpressionAttributeValues:
                        val = ExpressionAttributeValues[v_placeholder]
                        item[k] = val

        # 2. Handle REMOVE
        if "REMOVE" in UpdateExpression:
            remove_part = UpdateExpression.split("REMOVE")[1]
            removes = remove_part.split(",")
            for remove in removes:
                k = remove.strip()
                if k in item:
                    del item[k]
                    
        return {'Attributes': item}


@pytest.fixture
def mock_tables():
    restaurants = InMemoryTable('restaurant_id')
    menus = InMemoryTable('restaurant_id') # composite key in real life, but simplified mock
    config = InMemoryTable('restaurant_id')

    # Seed data for test_restaurants_list
    restaurants.items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}
    restaurants.items['r2'] = {'restaurant_id': 'r2', 'name': 'Rest 2', 'active': True}
    restaurants.items['r3'] = {'restaurant_id': 'r3', 'name': 'Rest 3', 'active': True}

    # Patch every visible `app` module reference used by tests.
    module_candidates = {app, importlib.import_module("app")}
    original_state = {}
    for module in module_candidates:
        original_state[module] = (
            getattr(module, "restaurants_table", None),
            getattr(module, "menus_table", None),
            getattr(module, "config_table", None),
        )
        module.restaurants_table = restaurants
        module.menus_table = menus
        module.config_table = config
    
    yield {'restaurants': restaurants, 'menus': menus, 'config': config}
    
    for module, state in original_state.items():
        module.restaurants_table, module.menus_table, module.config_table = state
