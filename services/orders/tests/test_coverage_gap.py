
import pytest
import json
import os
import sys
from unittest.mock import MagicMock, patch
from decimal import Decimal

# Import source modules
import logging
# Suppress logging during tests
logging.getLogger().setLevel(logging.CRITICAL)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
sys.modules.pop('app', None)
sys.modules.pop('handlers', None)
for _loaded in list(sys.modules):
    if _loaded.startswith('handlers.'):
        sys.modules.pop(_loaded, None)

import app
from models import Session, _maybe_int
from errors import NotFoundError, InvalidStateError, ValidationError, ExpiredError

# ---------------------------------------------------------------------------
# App Router Exception Tests
# ---------------------------------------------------------------------------
def test_router_exceptions():
    """Verify app.lambda_handler maps custom exceptions to correct HTTP codes."""
    
    # helper
    def _test_exc(exc, expected_code):
        with patch.object(app, 'create_order', side_effect=exc):
            event = {
                'routeKey': 'POST /v1/orders',
                'requestContext': {
                    'authorizer': {
                        'jwt': {
                            'claims': {'sub': 'cust_1', 'custom:role': 'customer'}
                        }
                    }
                }
            }
            resp = app.lambda_handler(event, None)
            assert resp['statusCode'] == expected_code
            
    _test_exc(NotFoundError("foo"), 404)
    _test_exc(InvalidStateError("foo"), 409)
    _test_exc(ExpiredError("foo"), 409)
    _test_exc(ValidationError("foo"), 400)
    _test_exc(Exception("Generic"), 500)

def test_router_unknown_route():
    event = {'routeKey': 'GET /v1/unknown'}
    resp = app.lambda_handler(event, None)
    assert resp['statusCode'] == 404
    assert 'Route not found' in resp['body']

# ---------------------------------------------------------------------------
# Models Hydration Tests
# ---------------------------------------------------------------------------
def test_maybe_int():
    assert _maybe_int(None) is None
    assert _maybe_int(10) == 10
    assert _maybe_int("10") == 10
    assert _maybe_int("abc") is None # Exception path
    assert _maybe_int([1,2]) is None # Exception path

def test_session_hydration_legacy_keys():
    """Verify Session.from_ddb handles legacy keys correctly."""
    item = {
        # Legacy/alternate keys
        'order_id': 'o1', # session_id
        'restaurant_id': 'r1', # destination_id
        'status': 'PENDING_NOT_SENT',
        'created_at': 1000,
        'expires_at': 2000,
        'customer_id': 'c1',
        'items': [
            {
                'menu_item_id': 'm1', # id
                'qty': 2,
                'name': 'Burger',
                'prep_units': 5 # work_units
            }
        ],
        'prep_units_total': 10, # work_units_total
        'received_by_restaurant': True # received_by_destination
    }
    
    s = Session.from_ddb(item)
    
    assert s.session_id == 'o1'
    assert s.destination_id == 'r1'
    assert s.work_units_total == 10
    assert s.received_by_destination is True
    assert len(s.resources) == 1
    res = s.resources[0]
    assert res.id == 'm1'
    assert res.work_units == 5
    assert res.price_cents == 0 # Default

def test_session_hydration_defaults():
    """Verify robust handling of missing optional fields."""
    item = {
        'session_id': 'o2',
        'destination_id': 'r2',
        'status': 'COMPLETED',
        'created_at': 1000,
        'expires_at': 2000,
    }
    s = Session.from_ddb(item)
    assert s.customer_name == 'Guest'
    assert s.resources == []
    assert s.vicinity is False
    assert s.arrive_fee_cents == 0
