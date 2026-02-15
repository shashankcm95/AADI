import os
import sys
import json
import pytest

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import app

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
