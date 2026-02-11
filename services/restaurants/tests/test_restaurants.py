import pytest
import json
from src import app

def test_restaurants_health_check():
    event = {
        'routeKey': 'GET /v1/restaurants/health'
    }
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'healthy'

def test_restaurants_list():
    event = {
        'routeKey': 'GET /v1/restaurants'
    }
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'restaurants' in body
    assert len(body['restaurants']) == 3
