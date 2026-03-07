
import json
import handlers

# Reuse mock_auth fixture logic manually or use fixture injection
# Pytest will inject mock_db fixture automatically if requested

def test_handle_create_order(mock_db):
    """Verify order creation from POS payload."""
    pos_body = {
        'items': [
            {'name': 'Burger', 'price_cents': 1000, 'qty': 2},
            {'name': 'Coke', 'price_cents': 200, 'qty': 1}
        ],
        'pos_order_ref': 'POS-123'
    }
    key_record = {'restaurant_id': 'rest_1', 'pos_system': 'generic'}
    
    resp = handlers.handle_create_order(pos_body, key_record)
    
    assert resp['statusCode'] == 201
    body = json.loads(resp['body'])
    assert body['arrive_fee_cents'] == 44 # (2000 + 200) * 0.02 = 44
    assert body['status'] == 'PENDING_NOT_SENT'
    
    # Verify DB write
    order_id = body['arrive_order_id']
    item = mock_db['orders'].items[order_id]
    assert item['restaurant_id'] == 'rest_1'
    assert item['total_cents'] == 2200
    assert 'ttl' in item
    assert item['ttl'] > 0


def test_handle_create_order_rejects_non_pay_at_restaurant(mock_db):
    pos_body = {
        'items': [{'name': 'Burger', 'price_cents': 1000, 'qty': 1}],
        'pos_order_ref': 'POS-124',
        'payment_mode': 'PREPAID',
    }
    key_record = {'restaurant_id': 'rest_1', 'pos_system': 'generic'}

    resp = handlers.handle_create_order(pos_body, key_record)
    assert resp['statusCode'] == 400

def test_handle_list_orders(mock_db):
    """Verify listing orders with filtering."""
    # Seed data
    mock_db['orders'].items['o1'] = {'order_id': 'o1', 'restaurant_id': 'rest_1', 'status': 'PENDING_NOT_SENT'}
    mock_db['orders'].items['o2'] = {'order_id': 'o2', 'restaurant_id': 'rest_1', 'status': 'IN_PROGRESS'}
    mock_db['orders'].items['o3'] = {'order_id': 'o3', 'restaurant_id': 'rest_2', 'status': 'PENDING_NOT_SENT'} # Diff rest
    
    key_record = {'restaurant_id': 'rest_1'}
    
    # List all
    resp = handlers.handle_list_orders(key_record, {})
    body = json.loads(resp['body'])
    assert len(body['orders']) == 2
    ids = {o['arrive_order_id'] for o in body['orders']}
    assert 'o1' in ids and 'o2' in ids
    
    # Filter by status
    resp = handlers.handle_list_orders(key_record, {'status': 'IN_PROGRESS'})
    body = json.loads(resp['body'])
    assert len(body['orders']) == 1
    assert body['orders'][0]['arrive_order_id'] == 'o2'

def test_handle_update_status(mock_db):
    """Verify status updates and cross-restaurant protection."""
    order_id = 'o_status'
    mock_db['orders'].items[order_id] = {'order_id': order_id, 'restaurant_id': 'rest_1', 'status': 'SENT_TO_DESTINATION'}
    
    key_record = {'restaurant_id': 'rest_1'}
    
    # Valid Update
    resp = handlers.handle_update_status(order_id, {'status': 'PREPARING'}, key_record)
    assert resp['statusCode'] == 200
    assert mock_db['orders'].items[order_id]['status'] == 'IN_PROGRESS' # Mapped
    
    # Invalid Status
    resp = handlers.handle_update_status(order_id, {'status': 'INVALID'}, key_record)
    assert resp['statusCode'] == 400
    
    # Wrong Restaurant
    key_record_2 = {'restaurant_id': 'rest_2'}
    # Need to trick mock update to fail condition. InMemoryTable mock logic handles this.
    resp = handlers.handle_update_status(order_id, {'status': 'READY'}, key_record_2)
    assert resp['statusCode'] == 403


def test_handle_update_status_rejects_invalid_jump(mock_db):
    order_id = 'o_jump'
    mock_db['orders'].items[order_id] = {'order_id': order_id, 'restaurant_id': 'rest_1', 'status': 'PENDING_NOT_SENT'}

    key_record = {'restaurant_id': 'rest_1'}
    resp = handlers.handle_update_status(order_id, {'status': 'READY'}, key_record)
    assert resp['statusCode'] == 409

def test_handle_force_fire(mock_db):
    """Verify force fire logic."""
    order_id = 'o_fire'
    mock_db['orders'].items[order_id] = {'order_id': order_id, 'restaurant_id': 'rest_1', 'status': 'PENDING_NOT_SENT'}
    
    key_record = {'restaurant_id': 'rest_1'}
    resp = handlers.handle_force_fire(order_id, key_record)
    
    assert resp['statusCode'] == 200
    item = mock_db['orders'].items[order_id]
    assert item['status'] == 'SENT_TO_DESTINATION'
    assert item['receipt_mode'] == 'HARD'
    assert item['vicinity'] is True


def test_handle_force_fire_waiting_for_capacity(mock_db):
    order_id = 'o_fire_waiting'
    mock_db['orders'].items[order_id] = {'order_id': order_id, 'restaurant_id': 'rest_1', 'status': 'WAITING_FOR_CAPACITY'}

    key_record = {'restaurant_id': 'rest_1'}
    resp = handlers.handle_force_fire(order_id, key_record)

    assert resp['statusCode'] == 200
    item = mock_db['orders'].items[order_id]
    assert item['status'] == 'SENT_TO_DESTINATION'


def test_handle_update_status_releases_capacity_on_completed(mock_db):
    order_id = 'o_complete'
    mock_db['orders'].items[order_id] = {
        'order_id': order_id,
        'restaurant_id': 'rest_1',
        'destination_id': 'rest_1',
        'status': 'FULFILLING',
        'capacity_window_start': 900,
    }
    mock_db['capacity'].items[('rest_1', 900)] = {'current_count': 2}

    key_record = {'restaurant_id': 'rest_1'}
    resp = handlers.handle_update_status(order_id, {'status': 'COMPLETED'}, key_record)

    assert resp['statusCode'] == 200
    assert mock_db['orders'].items[order_id]['status'] == 'COMPLETED'
    assert mock_db['capacity'].items[('rest_1', 900)]['current_count'] == 1

def test_handle_sync_menu(mock_db):
    """Verify menu sync."""
    key_record = {'restaurant_id': 'rest_1', 'pos_system': 'clover'}
    body = {'items': [{'id': 'm1', 'name': 'Pizza', 'price': 1500}]}

    prev = handlers.POS_MENU_SYNC_ENABLED
    handlers.POS_MENU_SYNC_ENABLED = True
    try:
        resp = handlers.handle_sync_menu(body, key_record)
        assert resp['statusCode'] == 200

        # Verify DB
        item = mock_db['menus'].items['rest_1']
        assert item['pos_system'] == 'clover'
        assert len(item['items']) == 1
        assert item['items'][0]['name'] == 'Pizza'
    finally:
        handlers.POS_MENU_SYNC_ENABLED = prev


def test_handle_sync_menu_disabled_returns_409(mock_db):
    key_record = {'restaurant_id': 'rest_1', 'pos_system': 'clover'}
    body = {'items': [{'id': 'm1', 'name': 'Pizza', 'price': 1500}]}

    prev = handlers.POS_MENU_SYNC_ENABLED
    handlers.POS_MENU_SYNC_ENABLED = False
    try:
        resp = handlers.handle_sync_menu(body, key_record)
        assert resp['statusCode'] == 409
    finally:
        handlers.POS_MENU_SYNC_ENABLED = prev


def test_handle_sync_menu_empty_items_returns_400(mock_db):
    key_record = {'restaurant_id': 'rest_1', 'pos_system': 'clover'}

    prev = handlers.POS_MENU_SYNC_ENABLED
    handlers.POS_MENU_SYNC_ENABLED = True
    try:
        resp = handlers.handle_sync_menu({'items': []}, key_record)
        assert resp['statusCode'] == 400

        resp = handlers.handle_sync_menu({}, key_record)
        assert resp['statusCode'] == 400
    finally:
        handlers.POS_MENU_SYNC_ENABLED = prev

def test_handle_create_order_empty_items_returns_400(mock_db):
    """Orders with no items should be rejected."""
    key_record = {'restaurant_id': 'rest_1', 'pos_system': 'generic'}

    resp = handlers.handle_create_order({'items': []}, key_record)
    assert resp['statusCode'] == 400

    resp = handlers.handle_create_order({}, key_record)
    assert resp['statusCode'] == 400


def test_handle_webhook(mock_db):
    """Verify webhook routing and idempotency."""
    key_record = {'restaurant_id': 'rest_1'}

    # 1. New Event (Order Created) — must include at least one item
    body = {
        'event_type': 'order.created',
        'webhook_id': 'wh_1',
        'data': {
            'items': [{'name': 'Burger', 'price_cents': 1000, 'qty': 1}],
            'pos_order_ref': 'ref1',
        },
    }

    resp = handlers.handle_webhook(body, key_record)
    assert resp['statusCode'] == 201 # from create_order

    # Verify webhook logged
    assert 'wh_1' in mock_db['webhooks'].items

    # 2. Duplicate Event
    resp = handlers.handle_webhook(body, key_record)
    assert resp['statusCode'] == 200
    assert json.loads(resp['body'])['status'] == 'already_processed'

    # 3. Unknown Event
    body_unk = {'event_type': 'unknown.event', 'webhook_id': 'wh_2'}
    resp = handlers.handle_webhook(body_unk, key_record)
    assert resp['statusCode'] == 200
    assert json.loads(resp['body'])['status'] == 'acknowledged'
