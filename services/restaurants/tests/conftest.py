
import pytest
import os
import sys
import importlib

# Add src to path (insert at front so it takes priority)
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src'))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# Aggressively clear any cross-service modules to avoid collisions
# (e.g. orders service leaves 'app', 'utils', 'handlers' in sys.modules)
_MODULES_TO_CLEAR = [k for k in sys.modules if k in (
    'app', 'utils', 'handlers', 'db', 'models', 'engine', 'errors', 'logger',
) or k.startswith('handlers.')]
for _m in _MODULES_TO_CLEAR:
    sys.modules.pop(_m, None)

import app
import utils
from handlers import restaurants as h_restaurants
from handlers import menu as h_menu
from handlers import config as h_config
from handlers import favorites as h_favorites
from handlers import images as h_images

# ---------------------------------------------------------------------------
# In-Memory DynamoDB Table Mock
# ---------------------------------------------------------------------------
class InMemoryTable:
    def __init__(self, key_name='restaurant_id', sort_key_name=None):
        self.items = {}
        self.key_name = key_name
        self.sort_key_name = sort_key_name

    def _storage_key_from_item(self, item):
        if self.sort_key_name:
            return (item[self.key_name], item[self.sort_key_name])
        return item[self.key_name]

    def _storage_key_from_key(self, key):
        if self.sort_key_name:
            return (key[self.key_name], key[self.sort_key_name])
        return key[self.key_name]

    def put_item(self, Item, **kwargs):
        key = self._storage_key_from_item(Item)
        self.items[key] = dict(Item)

    def get_item(self, Key):
        key = self._storage_key_from_key(Key)
        item = self.items.get(key)
        if item:
            return {'Item': dict(item)}
        return {}

    def delete_item(self, Key):
        key = self._storage_key_from_key(Key)
        self.items.pop(key, None)
        return {}

    def scan(self, FilterExpression=None, ExpressionAttributeValues=None):
        items = list(self.items.values())
        if FilterExpression == 'active = :a':
            val = ExpressionAttributeValues[':a']
            items = [i for i in items if i.get('active') == val]
        return {'Items': items}

    def query(self, IndexName=None, KeyConditionExpression=None, ExpressionAttributeValues=None, **kwargs):
        items = []
        target_val = None
        if KeyConditionExpression:
            try:
                target_val = KeyConditionExpression._values[1]
            except Exception:
                target_val = None

        if IndexName == 'GSI_ActiveRestaurants':
             for item in self.items.values():
                 if item.get('is_active') == "1":
                     items.append(item)
        elif IndexName == 'GSI_Cuisine':
             if target_val:
                 for item in self.items.values():
                     if item.get('cuisine') == target_val:
                         items.append(item)

        elif IndexName == 'GSI_PriceTier':
             if target_val:
                 for item in self.items.values():
                     if item.get('price_tier') == target_val:
                         items.append(item)
        elif self.sort_key_name and target_val is not None:
            for item in self.items.values():
                if item.get(self.key_name) == target_val:
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


# Table attribute names shared by all modules that need patching.
_TABLE_ATTRS = ('restaurants_table', 'menus_table', 'config_table', 'favorites_table')

# All modules whose table references must be patched for tests.
_MODULES_TO_PATCH = [app, utils, h_restaurants, h_menu, h_config, h_favorites, h_images]


@pytest.fixture
def mock_tables():
    restaurants = InMemoryTable('restaurant_id')
    menus = InMemoryTable('restaurant_id', 'menu_version')
    config = InMemoryTable('restaurant_id')
    favorites = InMemoryTable('customer_id', 'restaurant_id')

    # Seed data for test_restaurants_list
    restaurants.items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}
    restaurants.items['r2'] = {'restaurant_id': 'r2', 'name': 'Rest 2', 'active': True}
    restaurants.items['r3'] = {'restaurant_id': 'r3', 'name': 'Rest 3', 'active': True}

    tables = {
        'restaurants_table': restaurants,
        'menus_table': menus,
        'config_table': config,
        'favorites_table': favorites,
    }

    # Save originals then patch every module.
    original_state = {}
    for module in _MODULES_TO_PATCH:
        original_state[id(module)] = {attr: getattr(module, attr, None) for attr in _TABLE_ATTRS}
        for attr in _TABLE_ATTRS:
            if hasattr(module, attr):
                setattr(module, attr, tables[attr])

    yield {'restaurants': restaurants, 'menus': menus, 'config': config, 'favorites': favorites}

    # Restore originals.
    for module in _MODULES_TO_PATCH:
        saved = original_state[id(module)]
        for attr in _TABLE_ATTRS:
            if attr in saved:
                setattr(module, attr, saved[attr])
