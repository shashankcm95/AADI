import os
import sys
import json
import pytest

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import app


def _customer_event(route_key, restaurant_id=None, customer_id='cust_1'):
    path_params = {}
    if restaurant_id:
        path_params['restaurant_id'] = restaurant_id

    return {
        'routeKey': route_key,
        'pathParameters': path_params,
        'requestContext': {
            'authorizer': {
                'jwt': {
                    'claims': {
                        'custom:role': 'customer',
                        'sub': customer_id,
                    }
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
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'healthy'

def test_restaurants_list(mock_tables):
    # Seed data
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True, 'is_active': '1'}
    mock_tables['restaurants'].items['r2'] = {'restaurant_id': 'r2', 'name': 'Rest 2', 'active': True, 'is_active': '1'}
    mock_tables['restaurants'].items['r3'] = {'restaurant_id': 'r3', 'name': 'Rest 3', 'active': True, 'is_active': '1'}
    
    event = {
        'routeKey': 'GET /v1/restaurants'
    }
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'restaurants' in body
    assert len(body['restaurants']) == 3

def test_restaurants_list_only_active(mock_tables):
    # Seed mixed data
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True, 'is_active': '1'}
    mock_tables['restaurants'].items['r2'] = {'restaurant_id': 'r2', 'name': 'Rest 2', 'active': False} # No is_active
    
    event = {
        'routeKey': 'GET /v1/restaurants'
    }
    response = app.lambda_handler(event, None)
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
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    
    # Check DB
    item = mock_tables['restaurants'].items['r1']
    assert item['active'] is True
    assert item['is_active'] == '1'
    
    # Update to inactive
    event['body'] = json.dumps({'active': False})
    app.lambda_handler(event, None)
    
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
    response = app.lambda_handler(event, None)
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
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert len(body['restaurants']) == 1
    assert body['restaurants'][0]['name'] == 'Cheap Eats'


def test_customer_favorites_lifecycle(mock_tables):
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True, 'is_active': '1'}

    add_event = _customer_event('PUT /v1/favorites/{restaurant_id}', restaurant_id='r1')
    add_response = app.lambda_handler(add_event, None)
    assert add_response['statusCode'] == 200

    list_event = _customer_event('GET /v1/favorites')
    list_response = app.lambda_handler(list_event, None)
    assert list_response['statusCode'] == 200
    body = json.loads(list_response['body'])
    assert len(body['favorites']) == 1
    assert body['favorites'][0]['restaurant_id'] == 'r1'
    assert body['favorites'][0]['customer_id'] == 'cust_1'

    delete_event = _customer_event('DELETE /v1/favorites/{restaurant_id}', restaurant_id='r1')
    delete_response = app.lambda_handler(delete_event, None)
    assert delete_response['statusCode'] == 200

    list_after_delete = app.lambda_handler(list_event, None)
    assert list_after_delete['statusCode'] == 200
    body = json.loads(list_after_delete['body'])
    assert body['favorites'] == []


def test_customer_favorites_reject_unknown_restaurant(mock_tables):
    event = _customer_event('PUT /v1/favorites/{restaurant_id}', restaurant_id='missing')
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 404


def test_customer_favorites_reject_non_customer_role(mock_tables):
    event = {
        'routeKey': 'GET /v1/favorites',
        'requestContext': {'authorizer': {'jwt': {'claims': {'custom:role': 'admin', 'sub': 'admin_1'}}}}
    }
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 403


def test_create_image_upload_url_admin_success(mock_tables, monkeypatch):
    mock_tables['restaurants'].items['r1'] = {'restaurant_id': 'r1', 'name': 'Rest 1', 'active': True}
    monkeypatch.setattr(app, 'RESTAURANT_IMAGES_BUCKET', 'test-bucket')

    class MockS3:
        @staticmethod
        def generate_presigned_url(_op, Params=None, ExpiresIn=None):
            key = Params['Key']
            return f"https://uploads.example.com/{key}?ttl={ExpiresIn}"

    monkeypatch.setattr(app, 's3_client', MockS3())

    event = _admin_event(
        'POST /v1/restaurants/{restaurant_id}/images/upload-url',
        restaurant_id='r1',
        body={
            'file_name': 'cover.png',
            'content_type': 'image/png',
        },
    )
    response = app.lambda_handler(event, None)

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
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 403


def test_create_image_upload_url_rejects_when_limit_reached(mock_tables, monkeypatch):
    mock_tables['restaurants'].items['r1'] = {
        'restaurant_id': 'r1',
        'name': 'Rest 1',
        'active': True,
        'restaurant_image_keys': [f'restaurants/r1/{idx}.jpg' for idx in range(5)],
    }
    monkeypatch.setattr(app, 'RESTAURANT_IMAGES_BUCKET', 'test-bucket')

    event = _restaurant_admin_event(
        'POST /v1/restaurants/{restaurant_id}/images/upload-url',
        assigned_restaurant_id='r1',
        restaurant_id='r1',
        body={
            'file_name': 'cover.png',
            'content_type': 'image/png',
        },
    )
    response = app.lambda_handler(event, None)
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
    response = app.lambda_handler(event, None)
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
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    assert mock_tables['restaurants'].items['r1']['restaurant_image_keys'] == [
        'restaurants/r1/a.jpg',
        'restaurants/r1/b.jpg',
    ]
