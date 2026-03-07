import os
import sys
import json
import pytest

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from conftest import app as restaurants_app


def _customer_event(route_key, restaurant_id=None, customer_id='cust_1', include_role=True):
    path_params = {}
    if restaurant_id:
        path_params['restaurant_id'] = restaurant_id

    claims = {
        'sub': customer_id,
    }
    if include_role:
        claims['custom:role'] = 'customer'

    return {
        'routeKey': route_key,
        'pathParameters': path_params,
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': claims
                }
            }
        }
    }


def _admin_event(route_key, restaurant_id=None, body=None):
    path_params = {}
    if restaurant_id:
        path_params['restaurant_id'] = restaurant_id

    return {
        'routeKey': route_key,
        'pathParameters': path_params,
        'body': json.dumps(body or {}),
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'custom:role': 'admin',
                        'sub': 'admin_1',
                    }
                }
            }
        }
    }


def _restaurant_admin_event(route_key, assigned_restaurant_id, restaurant_id=None, body=None):
    path_params = {}
    if restaurant_id:
        path_params['restaurant_id'] = restaurant_id

    return {
        'routeKey': route_key,
        'pathParameters': path_params,
        'body': json.dumps(body or {}),
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'custom:role': 'restaurant_admin',
                        'custom:restaurant_id': assigned_restaurant_id,
                        'sub': 'rest_admin_1',
                    }
                }
            }
        }
    }


def test_restaurants_health_check():
    event = {
        'routeKey': 'GET /v1/restaurants/health'
    }
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'healthy'


def test_global_config_routes_admin(mock_tables, monkeypatch):
    import handlers.config as h_config
    import utils as _utils

    class _FakeSQS:
        def send_message(self, QueueUrl, MessageBody):
            return {"MessageId": "msg-1"}

    monkeypatch.setattr(_utils, "_sqs_client", _FakeSQS())
    monkeypatch.setattr(h_config, "GEOFENCE_RESYNC_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/geofence-resync")

    get_response = restaurants_app.lambda_handler(
        _admin_event('GET /v1/admin/global-config'),
        None,
    )
    assert get_response['statusCode'] == 200
    get_body = json.loads(get_response['body'])
    assert get_body['zone_distances_m']['ZONE_1'] == 1500

    put_response = restaurants_app.lambda_handler(
        _admin_event(
            'PUT /v1/admin/global-config',
            body={'zone_distances_m': {'ZONE_1': 1700}},
        ),
        None,
    )
    assert put_response['statusCode'] == 200


def test_global_config_routes_non_admin_denied(mock_tables):
    response = restaurants_app.lambda_handler(
        _restaurant_admin_event('GET /v1/admin/global-config', assigned_restaurant_id='r1'),
        None,
    )
    assert response['statusCode'] == 403

def test_get_single_restaurant_by_id(mock_tables):
    """BL-003: GET /v1/restaurants/{id} returns the restaurant."""
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}

    event = _admin_event('GET /v1/restaurants/{restaurant_id}', restaurant_id='r1')
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['restaurant_id'] == 'r1'
    assert body['name'] == 'Rest 1'


def test_get_single_restaurant_not_found(mock_tables):
    """BL-003: GET /v1/restaurants/{id} returns 404 for unknown ID."""
    event = _admin_event('GET /v1/restaurants/{restaurant_id}', restaurant_id='missing')
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'not found' in body['error'].lower()


def test_get_restaurant_admin_can_read_any(mock_tables):
    """Admin can read any restaurant regardless of assignment."""
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}
    mock_tables['restaurants'].items['r2'] = {'restaurant_id': 'r2', 'name': 'Rest 2', 'active': False}

    for rid in ('r1', 'r2'):
        event = _admin_event('GET /v1/restaurants/{restaurant_id}', restaurant_id=rid)
        response = restaurants_app.lambda_handler(event, None)
        assert response['statusCode'] == 200


def test_get_restaurant_admin_cannot_read_other(mock_tables):
    """restaurant_admin scoped to r1 cannot read r2."""
    mock_tables['restaurants'].items['r2'] = {'restaurant_id': 'r2', 'name': 'Rest 2', 'active': True}

    event = _restaurant_admin_event(
        'GET /v1/restaurants/{restaurant_id}',
        assigned_restaurant_id='r1',
        restaurant_id='r2',
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 403


def test_get_restaurant_admin_can_read_own(mock_tables):
    """restaurant_admin scoped to r1 can read r1."""
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}

    event = _restaurant_admin_event(
        'GET /v1/restaurants/{restaurant_id}',
        assigned_restaurant_id='r1',
        restaurant_id='r1',
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['restaurant_id'] == 'r1'


def test_get_restaurant_customer_cannot_see_inactive(mock_tables):
    """Customer gets 404 for an inactive restaurant."""
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': False}

    event = _customer_event('GET /v1/restaurants/{restaurant_id}', restaurant_id='r1')
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 404


def test_get_restaurant_customer_can_see_active(mock_tables):
    """Customer can read an active restaurant."""
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}

    event = _customer_event('GET /v1/restaurants/{restaurant_id}', restaurant_id='r1')
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200


def test_get_restaurant_customer_hides_internal_fields(mock_tables):
    """Customer reads should not expose internal/sensitive fields."""
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Rest 1',
        'active': True,
        'is_active': '1',
        'contact_email': 'owner@example.com',
        'restaurant_image_keys': ['restaurants/r1/1.jpg'],
        'vicinity_zone': {'radius': 5000},
    }

    event = _customer_event('GET /v1/restaurants/{restaurant_id}', restaurant_id='r1')
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['restaurant_id'] == 'r1'
    assert 'contact_email' not in body
    assert 'restaurant_image_keys' not in body
    assert 'vicinity_zone' not in body
    assert 'is_active' not in body


def test_get_restaurant_admin_keeps_internal_fields(mock_tables):
    """Admin reads should retain internal fields for operational use."""
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Rest 1',
        'active': True,
        'is_active': '1',
        'contact_email': 'owner@example.com',
        'restaurant_image_keys': ['restaurants/r1/1.jpg'],
    }

    event = _admin_event('GET /v1/restaurants/{restaurant_id}', restaurant_id='r1')
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['contact_email'] == 'owner@example.com'
    assert body['restaurant_image_keys'] == ['restaurants/r1/1.jpg']
    assert body['is_active'] == '1'


def test_restaurants_list(mock_tables):
    # Seed data
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True, 'is_active': '1'}
    mock_tables['restaurants'].items['r2'] = {'restaurant_id': 'r2', 'name': 'Rest 2', 'active': True, 'is_active': '1'}
    mock_tables['restaurants'].items['r3'] = {'restaurant_id': 'r3', 'name': 'Rest 3', 'active': True, 'is_active': '1'}
    
    event = {
        'routeKey': 'GET /v1/restaurants'
    }
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'restaurants' in body
    assert len(body['restaurants']) == 3


def test_restaurants_list_customer_hides_internal_fields(mock_tables):
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Rest 1',
        'active': True,
        'is_active': '1',
        'contact_email': 'owner@example.com',
        'restaurant_image_keys': ['restaurants/r1/1.jpg'],
        'vicinity_zone': {'radius': 5000},
    }
    event = _customer_event('GET /v1/restaurants')
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert len(body['restaurants']) >= 1
    r = next(rest for rest in body['restaurants'] if rest['restaurant_id'] == 'r1')
    assert 'contact_email' not in r
    assert 'restaurant_image_keys' not in r
    assert 'vicinity_zone' not in r
    assert 'is_active' not in r


def test_restaurants_list_only_active(mock_tables):
    # Seed mixed data
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True, 'is_active': '1'}
    mock_tables['restaurants'].items['r2'] = {'restaurant_id': 'r2', 'name': 'Rest 2', 'active': False} # No is_active
    
    event = {
        'routeKey': 'GET /v1/restaurants'
    }
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert len(body['restaurants']) == 1
    assert body['restaurants'][0]['restaurant_id'] == 'r1'

def test_update_restaurant_active_flag(mock_tables):
    # Seed inactive restaurant
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': False}
    
    # Update to active
    event = {
        'routeKey': 'PUT /v1/restaurants/{restaurant_id}',
        'pathParameters': {'restaurant_id': 'r1'},
        'body': json.dumps({'active': True}),
        'requestContext': {'authorizer': {'jwt': {'claims': {'custom:role': 'admin'}}}}
    }
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    
    # Check DB
    item = mock_tables['restaurants'].items['r1']
    assert item['active'] is True
    assert item['is_active'] == '1'
    
    # Update to inactive
    event['body'] = json.dumps({'active': False})
    restaurants_app.lambda_handler(event, None)
    
    # Check DB
    item = mock_tables['restaurants'].items['r1']
    assert item['active'] is False
    assert 'is_active' not in item

def test_restaurants_filter_by_cuisine(mock_tables):
    # Seed data
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Pizza Place', 'active': True, 'cuisine': 'Italian'}
    mock_tables['restaurants'].items['r2'] = {'restaurant_id': 'r2', 'name': 'Burger Joint', 'active': True, 'cuisine': 'American'}
    
    event = {
        'routeKey': 'GET /v1/restaurants',
        'queryStringParameters': {'cuisine': 'Italian'}
    }
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert len(body['restaurants']) == 1
    assert body['restaurants'][0]['name'] == 'Pizza Place'

def test_restaurants_filter_by_price_tier(mock_tables):
    # Seed data
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Cheap Eats', 'active': True, 'price_tier': 1}
    mock_tables['restaurants'].items['r2'] = {'restaurant_id': 'r2', 'name': 'Fancy Dining', 'active': True, 'price_tier': 4}
    
    event = {
        'routeKey': 'GET /v1/restaurants',
        'queryStringParameters': {'price_tier': '1'}
    }
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert len(body['restaurants']) == 1
    assert body['restaurants'][0]['name'] == 'Cheap Eats'


def test_customer_favorites_lifecycle(mock_tables):
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True, 'is_active': '1'}

    add_event = _customer_event('PUT /v1/favorites/{restaurant_id}', restaurant_id='r1')
    add_response = restaurants_app.lambda_handler(add_event, None)
    assert add_response['statusCode'] == 200

    list_event = _customer_event('GET /v1/favorites')
    list_response = restaurants_app.lambda_handler(list_event, None)
    assert list_response['statusCode'] == 200
    body = json.loads(list_response['body'])
    assert len(body['favorites']) == 1
    assert body['favorites'][0]['restaurant_id'] == 'r1'
    assert body['favorites'][0]['customer_id'] == 'cust_1'

    delete_event = _customer_event('DELETE /v1/favorites/{restaurant_id}', restaurant_id='r1')
    delete_response = restaurants_app.lambda_handler(delete_event, None)
    assert delete_response['statusCode'] == 200

    list_after_delete = restaurants_app.lambda_handler(list_event, None)
    assert list_after_delete['statusCode'] == 200
    body = json.loads(list_after_delete['body'])
    assert body['favorites'] == []


def test_customer_favorites_reject_unknown_restaurant(mock_tables):
    event = _customer_event('PUT /v1/favorites/{restaurant_id}', restaurant_id='missing')
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 404


def test_customer_favorites_reject_non_customer_role(mock_tables):
    event = {
        'routeKey': 'GET /v1/favorites',
        'requestContext': {'authorizer': {'jwt': {'claims': {'custom:role': 'admin', 'sub': 'admin_1'}}}}
    }
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 403


def test_customer_favorites_roleless_user_allowed(mock_tables):
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True, 'is_active': '1'}

    add_event = _customer_event('PUT /v1/favorites/{restaurant_id}', restaurant_id='r1', include_role=False)
    add_response = restaurants_app.lambda_handler(add_event, None)
    assert add_response['statusCode'] == 200


def test_create_image_upload_url_admin_success(mock_tables, monkeypatch):
    import utils as _utils
    from handlers import images as _h_images
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}
    monkeypatch.setattr(_utils, 'RESTAURANT_IMAGES_BUCKET', 'test-bucket')
    monkeypatch.setattr(_h_images, 'RESTAURANT_IMAGES_BUCKET', 'test-bucket')

    class MockS3:
        @staticmethod
        def generate_presigned_url(_op, Params=None, ExpiresIn=None):
            key = Params['Key']
            return f"https://uploads.example.com/{key}?ttl={ExpiresIn}"

    monkeypatch.setattr(_utils, 's3_client', MockS3())
    monkeypatch.setattr(_h_images, 's3_client', MockS3())

    event = _admin_event(
        'POST /v1/restaurants/{restaurant_id}/images/upload-url',
        restaurant_id='r1',
        body={
            'file_name': 'cover.png',
            'content_type': 'image/png',
        },
    )
    response = restaurants_app.lambda_handler(event, None)

    assert response['statusCode'] == 200
    payload = json.loads(response['body'])
    assert payload['object_key'].startswith('restaurants/r1/')
    assert payload['object_key'].endswith('.png')
    assert 'upload_url' in payload
    assert 'preview_url' in payload
    assert payload['expires_in_seconds'] == 900


def test_create_image_upload_url_denies_other_restaurant_admin(mock_tables):
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}

    event = _restaurant_admin_event(
        'POST /v1/restaurants/{restaurant_id}/images/upload-url',
        assigned_restaurant_id='r2',
        restaurant_id='r1',
        body={
            'file_name': 'cover.png',
            'content_type': 'image/png',
        },
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 403


def test_create_image_upload_url_rejects_when_limit_reached(mock_tables, monkeypatch):
    import utils as _utils
    from handlers import images as _h_images
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Rest 1',
        'active': True,
        'restaurant_image_keys': [f'restaurants/r1/{idx}.jpg' for idx in range(5)],
    }
    monkeypatch.setattr(_utils, 'RESTAURANT_IMAGES_BUCKET', 'test-bucket')
    monkeypatch.setattr(_h_images, 'RESTAURANT_IMAGES_BUCKET', 'test-bucket')

    event = _restaurant_admin_event(
        'POST /v1/restaurants/{restaurant_id}/images/upload-url',
        assigned_restaurant_id='r1',
        restaurant_id='r1',
        body={
            'file_name': 'cover.png',
            'content_type': 'image/png',
        },
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 400
    assert 'maximum of 5' in json.loads(response['body'])['error']


def test_update_restaurant_rejects_more_than_five_images(mock_tables):
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Rest 1',
        'active': True,
        'street': '123 Main',
        'city': 'Town',
        'state': 'CA',
        'zip': '94000',
        'location': {'lat': 1, 'lon': 1},
    }

    keys = [f"restaurants/r1/{idx}.jpg" for idx in range(6)]
    event = _admin_event(
        'PUT /v1/restaurants/{restaurant_id}',
        restaurant_id='r1',
        body={'restaurant_image_keys': keys},
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 400
    assert 'maximum of 5' in json.loads(response['body'])['error']


def test_update_restaurant_sets_image_keys_for_owner(mock_tables):
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Rest 1',
        'active': True,
        'street': '123 Main',
        'city': 'Town',
        'state': 'CA',
        'zip': '94000',
        'location': {'lat': 1, 'lon': 1},
    }

    event = _restaurant_admin_event(
        'PUT /v1/restaurants/{restaurant_id}',
        assigned_restaurant_id='r1',
        restaurant_id='r1',
        body={
            'restaurant_image_keys': [
                'restaurants/r1/a.jpg',
                'restaurants/r1/b.jpg',
            ]
        },
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    assert mock_tables['restaurants'].items['r1']['restaurant_image_keys'] == [
        'restaurants/r1/a.jpg',
        'restaurants/r1/b.jpg',
    ]


def test_update_restaurant_syncs_geofence(mock_tables, monkeypatch):
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Rest 1',
        'active': True,
        'street': '123 Main',
        'city': 'Town',
        'state': 'CA',
        'zip': '94000',
        'location': {'lat': 1, 'lon': 1},
    }

    import handlers.restaurants as h_rest
    from unittest.mock import MagicMock
    mock_sync = MagicMock(return_value=True)
    monkeypatch.setattr(h_rest, 'upsert_restaurant_geofences', mock_sync)
    monkeypatch.setattr(h_rest, 'geocode_address', lambda *_: {'lat': 30.0, 'lon': -97.0})

    event = _admin_event(
        'PUT /v1/restaurants/{restaurant_id}',
        restaurant_id='r1',
        body={'street': '500 Market St'},
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    mock_sync.assert_called_once()


def test_delete_restaurant_success_admin(mock_tables, monkeypatch):
    """Admin can delete restaurant and its associated data."""
    # Seed data
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Rest 1',
        'contact_email': 'owner@test.com',
        'active': True
    }
    # Seed config table if it exists in mock logic
    if 'config' in mock_tables:
        mock_tables['config'].items['r1'] = {'restaurant_id': 'r1', 'config': {}}

    # Mock Cognito
    class MockCognito:
        def list_users(self, **kwargs):
            return {'Users': [{'Username': 'owner@test.com'}]}
        
        def admin_delete_user(self, **kwargs):
            pass

    import handlers.restaurants as h_rest
    monkeypatch.setattr(h_rest, 'cognito', MockCognito())
    monkeypatch.setattr(h_rest, 'USER_POOL_ID', 'pool-1')
    from unittest.mock import MagicMock
    mock_delete_geofences = MagicMock(return_value=True)
    monkeypatch.setattr(h_rest, 'delete_restaurant_geofences', mock_delete_geofences)

    # Execute
    event = _admin_event('DELETE /v1/restaurants/{restaurant_id}', restaurant_id='r1')
    response = restaurants_app.lambda_handler(event, None)

    # Verify
    assert response['statusCode'] == 200
    assert 'r1' not in mock_tables['restaurants'].items
    mock_delete_geofences.assert_called_once_with('r1')
    if 'config' in mock_tables:
        assert 'r1' not in mock_tables['config'].items


def test_delete_restaurant_denies_non_admin(mock_tables):
    """Restaurant admin cannot delete their own restaurant."""
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1'}
    
    event = _restaurant_admin_event(
        'DELETE /v1/restaurants/{restaurant_id}',
        assigned_restaurant_id='r1', # Owner
        restaurant_id='r1'
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 403


def test_delete_restaurant_cognito_cleanup_failure_non_blocking(mock_tables, monkeypatch):
    """Failure to delete Cognito user should not block restaurant deletion."""
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'contact_email': 'fail@test.com'}
    
    class MockCognitoError:
        def list_users(self, **kwargs):
            raise Exception("Cognito Down")
        # admin_delete_user might be called if list_users succeeds, but here list_users fails first

    import handlers.restaurants as h_rest
    monkeypatch.setattr(h_rest, 'cognito', MockCognitoError())
    monkeypatch.setattr(h_rest, 'USER_POOL_ID', 'pool-1')

    event = _admin_event('DELETE /v1/restaurants/{restaurant_id}', restaurant_id='r1')
    response = restaurants_app.lambda_handler(event, None)
    
    # Needs to still succeed
    assert response['statusCode'] == 200
    assert 'r1' not in mock_tables['restaurants'].items


def test_restaurant_admin_cannot_self_reactivate(mock_tables):
    """BL-002: restaurant_admin cannot flip their own restaurant back to active."""
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1', 'name': 'Rest 1', 'active': False,
    }

    event = _restaurant_admin_event(
        'PUT /v1/restaurants/{restaurant_id}',
        assigned_restaurant_id='r1',
        restaurant_id='r1',
        body={'active': True, 'name': 'Rest 1 Updated'},
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200  # name update succeeds

    # active field must NOT have been flipped
    item = mock_tables['restaurants'].items['r1']
    assert item.get('active') is not True


def test_admin_can_reactivate_restaurant(mock_tables):
    """BL-002: platform admin CAN reactivate a restaurant."""
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1', 'name': 'Rest 1', 'active': False,
    }

    event = _admin_event(
        'PUT /v1/restaurants/{restaurant_id}',
        restaurant_id='r1',
        body={'active': True},
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200

    item = mock_tables['restaurants'].items['r1']
    assert item.get('active') is True


def test_create_restaurant_happy_path(mock_tables, monkeypatch):
    """Create restaurant with valid body → 201 with restaurant_id."""
    import handlers.restaurants as h_rest
    from unittest.mock import MagicMock

    monkeypatch.setattr(h_rest, 'geocode_address', lambda *_: {'lat': 30.0, 'lon': -97.0})
    monkeypatch.setattr(h_rest, 'upsert_restaurant_geofences', MagicMock(return_value=True))
    monkeypatch.setattr(h_rest, 'USER_POOL_ID', '')  # No Cognito in test

    event = _admin_event(
        'POST /v1/restaurants',
        body={
            'name': 'Test Burger Joint',
            'street': '123 Main St',
            'city': 'Austin',
            'state': 'TX',
            'zip': '78701',
            'cuisine': 'American',
            'price_tier': 2,
        },
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 201
    body = json.loads(response['body'])
    assert 'restaurant_id' in body
    assert body['user_status'] in ('CREATED', 'LINKED')

    # Verify restaurant in DB
    rid = body['restaurant_id']
    item = mock_tables['restaurants'].items[rid]
    assert item['name'] == 'Test Burger Joint'
    assert item['cuisine'] == 'American'
    assert item['location'] == {'lat': 30.0, 'lon': -97.0}

    # Verify config also created
    config = mock_tables['config'].items.get(rid)
    assert config is not None
    assert config['max_concurrent_orders'] == 10


def test_create_restaurant_missing_name_returns_400(mock_tables, monkeypatch):
    """Create restaurant without name → 400."""
    event = _admin_event('POST /v1/restaurants', body={'street': '123 Main'})
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'name' in body.get('error', '').lower()


def test_create_restaurant_non_admin_denied(mock_tables):
    """Non-admin role cannot create restaurants."""
    event = _restaurant_admin_event(
        'POST /v1/restaurants',
        assigned_restaurant_id='r1',
        body={'name': 'Hacker Restaurant'},
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 403


def test_create_restaurant_rejects_malformed_email(mock_tables, monkeypatch):
    """BL-006: Invalid email format in contact_email returns 400."""
    import handlers.restaurants as h_rest
    monkeypatch.setattr(h_rest, 'USER_POOL_ID', 'pool-1')

    event = _admin_event(
        'POST /v1/restaurants',
        body={'name': 'Test Restaurant', 'contact_email': 'test"quote@example.com'},
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'email' in body['error'].lower()


def test_update_restaurant_ignores_contact_email_in_body(mock_tables):
    """contact_email is immutable — update should preserve the original value."""
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Original Name',
        'contact_email': 'original@example.com',
        'street': '', 'city': '', 'state': '', 'zip': '',
        'active': True,
    }

    event = _admin_event(
        'PUT /v1/restaurants/{restaurant_id}',
        restaurant_id='r1',
        body={'name': 'Updated Name', 'contact_email': 'hacker@evil.com'},
    )
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200

    item = mock_tables['restaurants'].items['r1']
    assert item['contact_email'] == 'original@example.com'
    assert item['name'] == 'Updated Name'


def test_admin_list_pagination_first_page(mock_tables):
    """BL-011: admin GET /v1/restaurants with limit=2 on 3-item table returns 2 items + next_token."""
    # conftest pre-seeds r1, r2, r3
    event = _admin_event('GET /v1/restaurants')
    event['queryStringParameters'] = {'limit': '2'}
    response = restaurants_app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert len(body['restaurants']) == 2
    assert 'next_token' in body


def test_admin_list_pagination_second_page(mock_tables):
    """BL-011: passing next_token from first page returns the remaining item with no next_token."""
    # First page
    event = _admin_event('GET /v1/restaurants')
    event['queryStringParameters'] = {'limit': '2'}
    first_resp = restaurants_app.lambda_handler(event, None)
    assert first_resp['statusCode'] == 200
    first_body = json.loads(first_resp['body'])
    next_token = first_body['next_token']

    # Second page
    event2 = _admin_event('GET /v1/restaurants')
    event2['queryStringParameters'] = {'limit': '2', 'next_token': next_token}
    second_resp = restaurants_app.lambda_handler(event2, None)
    assert second_resp['statusCode'] == 200
    second_body = json.loads(second_resp['body'])
    assert len(second_body['restaurants']) == 1
    assert 'next_token' not in second_body
