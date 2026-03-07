
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


# =============================================================================
# _validate_transition Unit Tests
# =============================================================================

def test_validate_transition_idempotent():
    """Same status → empty string (accepted)."""
    assert handlers._validate_transition('IN_PROGRESS', 'IN_PROGRESS') == ''
    assert handlers._validate_transition('COMPLETED', 'COMPLETED') == ''
    assert handlers._validate_transition('PENDING_NOT_SENT', 'PENDING_NOT_SENT') == ''


def test_validate_transition_pending_to_sent():
    """PENDING_NOT_SENT → SENT_TO_DESTINATION is valid."""
    assert handlers._validate_transition('PENDING_NOT_SENT', 'SENT_TO_DESTINATION') == ''


def test_validate_transition_waiting_to_sent():
    """WAITING_FOR_CAPACITY → SENT_TO_DESTINATION is valid."""
    assert handlers._validate_transition('WAITING_FOR_CAPACITY', 'SENT_TO_DESTINATION') == ''


def test_validate_transition_chain_transitions():
    """Each valid chain transition should succeed."""
    assert handlers._validate_transition('SENT_TO_DESTINATION', 'IN_PROGRESS') == ''
    assert handlers._validate_transition('IN_PROGRESS', 'READY') == ''
    assert handlers._validate_transition('READY', 'FULFILLING') == ''
    assert handlers._validate_transition('FULFILLING', 'COMPLETED') == ''


def test_validate_transition_invalid_jump():
    """Skipping chain steps should fail."""
    result = handlers._validate_transition('PENDING_NOT_SENT', 'READY')
    assert 'Invalid transition' in result
    assert 'PENDING_NOT_SENT' in result
    assert 'READY' in result


def test_validate_transition_backward_jump():
    """Going backward in the chain should fail."""
    result = handlers._validate_transition('COMPLETED', 'PENDING_NOT_SENT')
    assert 'Invalid transition' in result


def test_validate_transition_sent_from_invalid_source():
    """SENT_TO_DESTINATION only allowed from PENDING or WAITING."""
    result = handlers._validate_transition('IN_PROGRESS', 'SENT_TO_DESTINATION')
    assert 'Invalid transition' in result


def test_validate_transition_empty_target():
    """Empty target status → 'Missing status'."""
    assert handlers._validate_transition('PENDING_NOT_SENT', '') == 'Missing status'
    assert handlers._validate_transition('PENDING_NOT_SENT', None) == 'Missing status'


def test_validate_transition_none_current():
    """None/empty current status is stringified and handled."""
    # None current → str(None or '') → ''
    result = handlers._validate_transition(None, 'SENT_TO_DESTINATION')
    assert 'Invalid transition' in result

    result = handlers._validate_transition('', 'SENT_TO_DESTINATION')
    assert 'Invalid transition' in result


# =============================================================================
# handle_get_menu Tests
# =============================================================================

def test_handle_get_menu_happy_path(mock_db):
    """Menu exists in DB → returns menu items."""
    mock_db['menus'].items['rest_1'] = {
        'restaurant_id': 'rest_1',
        'menu_version': 'latest',
        'items': [
            {'id': 'm1', 'name': 'Burger', 'price_cents': 1200},
            {'id': 'm2', 'name': 'Fries', 'price_cents': 500},
        ]
    }

    key_record = {'restaurant_id': 'rest_1'}
    resp = handlers.handle_get_menu(key_record)

    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert body['restaurant_id'] == 'rest_1'
    assert len(body['menu']) == 2
    assert body['menu'][0]['name'] == 'Burger'


def test_handle_get_menu_no_menu_in_db(mock_db):
    """No menu record → returns empty menu."""
    key_record = {'restaurant_id': 'rest_no_menu'}
    resp = handlers.handle_get_menu(key_record)

    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert body['menu'] == []
    assert body['restaurant_id'] == 'rest_no_menu'


def test_handle_get_menu_table_is_none(mock_db):
    """menus_table is None → returns empty menu (not 500)."""
    original = handlers.menus_table
    handlers.menus_table = None
    try:
        key_record = {'restaurant_id': 'rest_1'}
        resp = handlers.handle_get_menu(key_record)

        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['menu'] == []
    finally:
        handlers.menus_table = original


def test_handle_get_menu_db_exception(mock_db):
    """DynamoDB exception → returns empty menu (graceful degradation)."""
    from unittest.mock import MagicMock

    original = handlers.menus_table
    failing_table = MagicMock()
    failing_table.get_item.side_effect = Exception("DynamoDB timeout")
    handlers.menus_table = failing_table
    try:
        key_record = {'restaurant_id': 'rest_1'}
        resp = handlers.handle_get_menu(key_record)

        assert resp['statusCode'] == 200
        body = json.loads(resp['body'])
        assert body['menu'] == []
    finally:
        handlers.menus_table = original


# =============================================================================
# POS Error Path Tests
# =============================================================================

def test_handle_create_order_missing_pos_order_ref(mock_db):
    """Missing pos_order_ref defaults to empty string, order still created."""
    pos_body = {
        'items': [{'name': 'Burger', 'price_cents': 1000, 'qty': 1}],
        # No pos_order_ref
    }
    key_record = {'restaurant_id': 'rest_1', 'pos_system': 'generic'}
    resp = handlers.handle_create_order(pos_body, key_record)
    assert resp['statusCode'] == 201
    body = json.loads(resp['body'])
    assert body['pos_order_ref'] == ''


def test_handle_update_status_order_not_found(mock_db):
    """Status update on nonexistent order → 404."""
    key_record = {'restaurant_id': 'rest_1'}
    resp = handlers.handle_update_status('nonexistent', {'status': 'PREPARING'}, key_record)
    assert resp['statusCode'] == 404
    assert 'not found' in json.loads(resp['body']).get('error', '').lower()


def test_handle_force_fire_wrong_restaurant(mock_db):
    """Force fire with wrong restaurant → 403."""
    order_id = 'o_fire_wrong'
    mock_db['orders'].items[order_id] = {
        'order_id': order_id, 'restaurant_id': 'rest_1', 'status': 'PENDING_NOT_SENT'
    }
    key_record = {'restaurant_id': 'rest_2'}
    resp = handlers.handle_force_fire(order_id, key_record)
    assert resp['statusCode'] == 403
    assert 'does not belong' in json.loads(resp['body']).get('error', '').lower()


def test_handle_force_fire_completed_order(mock_db):
    """Force fire on COMPLETED order → 409 (invalid transition)."""
    order_id = 'o_fire_completed'
    mock_db['orders'].items[order_id] = {
        'order_id': order_id, 'restaurant_id': 'rest_1', 'status': 'COMPLETED'
    }
    key_record = {'restaurant_id': 'rest_1'}
    resp = handlers.handle_force_fire(order_id, key_record)
    assert resp['statusCode'] == 409
    assert 'Invalid transition' in json.loads(resp['body']).get('error', '')


def test_handle_force_fire_order_not_found(mock_db):
    """Force fire on nonexistent order → 404."""
    key_record = {'restaurant_id': 'rest_1'}
    resp = handlers.handle_force_fire('nonexistent', key_record)
    assert resp['statusCode'] == 404


def test_handle_sync_menu_table_is_none(mock_db):
    """Menu sync when menus_table is None → graceful error."""
    original = handlers.menus_table
    handlers.menus_table = None
    prev = handlers.POS_MENU_SYNC_ENABLED
    handlers.POS_MENU_SYNC_ENABLED = True
    try:
        key_record = {'restaurant_id': 'rest_1', 'pos_system': 'clover'}
        body = {'items': [{'id': 'm1', 'name': 'Pizza', 'price': 1500}]}
        resp = handlers.handle_sync_menu(body, key_record)
        # Should still succeed — menu sync writes to table, but if table is None, code handles it
        assert resp['statusCode'] in (200, 500)
    finally:
        handlers.menus_table = original
        handlers.POS_MENU_SYNC_ENABLED = prev


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


# =============================================================================
# Webhook Edge Cases
# =============================================================================

def test_handle_webhook_order_status_changed(mock_db):
    """order.status_changed event routes to update_status."""
    # Seed an order first
    order_id = 'o_webhook_status'
    mock_db['orders'].items[order_id] = {
        'order_id': order_id, 'restaurant_id': 'rest_1', 'status': 'SENT_TO_DESTINATION'
    }

    key_record = {'restaurant_id': 'rest_1'}
    body = {
        'event_type': 'order.status_changed',
        'webhook_id': 'wh_status_1',
        'data': {
            'order_id': order_id,
            'status': 'PREPARING',
        },
    }
    resp = handlers.handle_webhook(body, key_record)
    assert resp['statusCode'] == 200
    assert mock_db['orders'].items[order_id]['status'] == 'IN_PROGRESS'


def test_handle_webhook_order_updated(mock_db):
    """order.updated event routes to update_status."""
    order_id = 'o_webhook_updated'
    mock_db['orders'].items[order_id] = {
        'order_id': order_id, 'restaurant_id': 'rest_1', 'status': 'IN_PROGRESS'
    }

    key_record = {'restaurant_id': 'rest_1'}
    body = {
        'event_type': 'order.updated',
        'webhook_id': 'wh_updated_1',
        'data': {
            'order_id': order_id,
            'status': 'READY',
        },
    }
    resp = handlers.handle_webhook(body, key_record)
    assert resp['statusCode'] == 200
    assert mock_db['orders'].items[order_id]['status'] == 'READY'


def test_handle_webhook_missing_webhook_id(mock_db):
    """Missing webhook_id → auto-generated, still processes."""
    key_record = {'restaurant_id': 'rest_1'}
    body = {
        'event_type': 'order.created',
        # No webhook_id
        'data': {
            'items': [{'name': 'Salad', 'price_cents': 800, 'qty': 1}],
            'pos_order_ref': 'ref_no_wh',
        },
    }
    resp = handlers.handle_webhook(body, key_record)
    assert resp['statusCode'] == 201  # Order still created

    # Verify a webhook log entry was created with auto-generated ID
    wh_keys = [k for k in mock_db['webhooks'].items.keys() if k.startswith('wh_')]
    assert len(wh_keys) >= 1


def test_handle_webhook_missing_data_field(mock_db):
    """order.created with missing data uses body as fallback."""
    key_record = {'restaurant_id': 'rest_1'}
    body = {
        'event_type': 'order.created',
        'webhook_id': 'wh_no_data',
        # No 'data' key — body itself is used
        'items': [{'name': 'Coffee', 'price_cents': 400, 'qty': 1}],
        'pos_order_ref': 'ref_fallback',
    }
    resp = handlers.handle_webhook(body, key_record)
    assert resp['statusCode'] == 201
