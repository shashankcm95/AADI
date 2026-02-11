"""
POS Format Mapper

Translates between POS-native formats (Toast, Square) and
Arrive's domain-neutral Session/Resource format.
"""

from typing import Any, Dict, List


def pos_order_to_session(pos_payload: Dict[str, Any], pos_system: str = "generic") -> Dict[str, Any]:
    """
    Convert a POS order payload into Arrive's session creation format.
    
    Each POS has its own format. This mapper normalizes them.
    """
    if pos_system == "toast":
        return _toast_order_to_session(pos_payload)
    elif pos_system == "square":
        return _square_order_to_session(pos_payload)
    else:
        return _generic_order_to_session(pos_payload)


def session_to_pos_order(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert an Arrive session into a POS-friendly response format.
    Strips internal fields and uses POS-standard naming.
    """
    items = []
    for item in session.get('items', []):
        items.append({
            'name': item.get('name', 'Unknown Item'),
            'quantity': item.get('qty', 1),
            'price_cents': item.get('price_cents', 0),
            'external_id': item.get('id', item.get('menu_item_id')),
        })

    return {
        'arrive_order_id': session.get('order_id', session.get('session_id')),
        'status': session.get('status'),
        'arrival_status': session.get('arrival_status'),
        'customer_name': session.get('customer_name', 'Guest'),
        'items': items,
        'total_cents': session.get('total_cents', 0),
        'arrive_fee_cents': session.get('arrive_fee_cents', 0),
        'payment_mode': session.get('payment_mode', 'PAY_AT_RESTAURANT'),
        'created_at': session.get('created_at'),
        'vicinity': session.get('vicinity', False),
    }


def pos_menu_to_resources(pos_menu: List[Dict[str, Any]], pos_system: str = "generic") -> List[Dict[str, Any]]:
    """
    Convert POS menu items to Arrive's Resource format.
    """
    resources = []
    for item in pos_menu:
        resources.append({
            'id': item.get('id', item.get('external_id', item.get('guid', ''))),
            'name': item.get('name', 'Unnamed'),
            'price_cents': item.get('price_cents', item.get('price', 0)),
            'work_units': item.get('work_units', item.get('prep_time_minutes', 1)),
            'category': item.get('category', 'General'),
            'available': item.get('available', True),
        })
    return resources


# --- POS-Specific Mappers ---

def _toast_order_to_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Toast-specific order format → Arrive format."""
    items = []
    for check in payload.get('checks', [{}]):
        for selection in check.get('selections', []):
            items.append({
                'id': selection.get('guid', selection.get('externalId', '')),
                'name': selection.get('displayName', 'Unknown'),
                'qty': selection.get('quantity', 1),
                'price_cents': int(selection.get('price', 0) * 100),
                'work_units': selection.get('prepTimeMinutes', 1),
            })

    return {
        'restaurant_id': payload.get('restaurantGuid', payload.get('restaurant_id', '')),
        'items': items,
        'customer_name': payload.get('customer', {}).get('firstName', 'Guest'),
        'pos_order_ref': payload.get('guid', ''),
    }


def _square_order_to_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Square-specific order format → Arrive format."""
    items = []
    for line_item in payload.get('line_items', []):
        items.append({
            'id': line_item.get('catalog_object_id', ''),
            'name': line_item.get('name', 'Unknown'),
            'qty': int(line_item.get('quantity', '1')),
            'price_cents': int(line_item.get('base_price_money', {}).get('amount', 0)),
            'work_units': 1,
        })

    return {
        'restaurant_id': payload.get('location_id', payload.get('restaurant_id', '')),
        'items': items,
        'customer_name': payload.get('customer_name', 'Guest'),
        'pos_order_ref': payload.get('id', ''),
    }


def _generic_order_to_session(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generic POS format — pass-through with minimal mapping."""
    items = []
    for item in payload.get('items', []):
        items.append({
            'id': item.get('id', item.get('external_id', '')),
            'name': item.get('name', 'Unknown'),
            'qty': item.get('qty', item.get('quantity', 1)),
            'price_cents': item.get('price_cents', 0),
            'work_units': item.get('work_units', item.get('prep_units', 1)),
        })

    return {
        'restaurant_id': payload.get('restaurant_id', ''),
        'items': items,
        'customer_name': payload.get('customer_name', 'Guest'),
        'pos_order_ref': payload.get('pos_order_ref', ''),
    }
