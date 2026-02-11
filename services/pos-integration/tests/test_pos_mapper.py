"""
POS Mapper Unit Tests
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pos_mapper import (
    pos_order_to_session,
    session_to_pos_order,
    pos_menu_to_resources,
)


# --- pos_order_to_session ---

def test_generic_order_mapping():
    payload = {
        'restaurant_id': 'rest_001',
        'items': [
            {'id': 'item1', 'name': 'Burger', 'qty': 2, 'price_cents': 1299, 'work_units': 3},
            {'id': 'item2', 'name': 'Fries', 'qty': 1, 'price_cents': 499, 'work_units': 1},
        ],
        'customer_name': 'Alice',
    }
    result = pos_order_to_session(payload, 'generic')
    assert result['restaurant_id'] == 'rest_001'
    assert result['customer_name'] == 'Alice'
    assert len(result['items']) == 2
    assert result['items'][0]['name'] == 'Burger'
    assert result['items'][0]['qty'] == 2


def test_toast_order_mapping():
    payload = {
        'restaurantGuid': 'toast_rest_001',
        'guid': 'toast_order_123',
        'customer': {'firstName': 'Bob'},
        'checks': [{
            'selections': [
                {'guid': 'sel1', 'displayName': 'Chicken Sandwich', 'quantity': 1, 'price': 12.99},
                {'guid': 'sel2', 'displayName': 'Lemonade', 'quantity': 2, 'price': 3.50},
            ]
        }],
    }
    result = pos_order_to_session(payload, 'toast')
    assert result['restaurant_id'] == 'toast_rest_001'
    assert result['customer_name'] == 'Bob'
    assert result['pos_order_ref'] == 'toast_order_123'
    assert len(result['items']) == 2
    assert result['items'][0]['name'] == 'Chicken Sandwich'
    assert result['items'][0]['price_cents'] == 1299
    assert result['items'][1]['price_cents'] == 350


def test_square_order_mapping():
    payload = {
        'location_id': 'sq_loc_001',
        'id': 'sq_order_456',
        'customer_name': 'Charlie',
        'line_items': [
            {'catalog_object_id': 'cat1', 'name': 'Pasta', 'quantity': '1', 'base_price_money': {'amount': 1599}},
        ],
    }
    result = pos_order_to_session(payload, 'square')
    assert result['restaurant_id'] == 'sq_loc_001'
    assert result['pos_order_ref'] == 'sq_order_456'
    assert result['items'][0]['price_cents'] == 1599
    assert result['items'][0]['qty'] == 1


# --- session_to_pos_order ---

def test_session_to_pos_order():
    session = {
        'order_id': 'ord_001',
        'status': 'SENT_TO_DESTINATION',
        'arrival_status': '5_MIN_OUT',
        'customer_name': 'Diana',
        'items': [{'name': 'Salad', 'qty': 1, 'price_cents': 899, 'id': 'item1'}],
        'total_cents': 899,
        'arrive_fee_cents': 18,
        'payment_mode': 'PREPAID',
        'created_at': 1700000000,
        'vicinity': True,
    }
    result = session_to_pos_order(session)
    assert result['arrive_order_id'] == 'ord_001'
    assert result['status'] == 'SENT_TO_DESTINATION'
    assert result['arrive_fee_cents'] == 18
    assert result['payment_mode'] == 'PREPAID'
    assert result['vicinity'] is True
    assert len(result['items']) == 1


# --- pos_menu_to_resources ---

def test_menu_conversion():
    pos_menu = [
        {'id': 'm1', 'name': 'Burger', 'price_cents': 1299, 'work_units': 3, 'category': 'Mains'},
        {'id': 'm2', 'name': 'Fries', 'price_cents': 499, 'work_units': 1, 'category': 'Sides'},
    ]
    resources = pos_menu_to_resources(pos_menu)
    assert len(resources) == 2
    assert resources[0]['name'] == 'Burger'
    assert resources[0]['work_units'] == 3
    assert resources[1]['available'] is True
