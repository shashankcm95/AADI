import pytest
import json
from src import app

def test_kitchen_health_check():
    event = {
        'rawPath': '/v1/kitchen/health',
        'requestContext': {
            'http': {
                'method': 'GET'
            }
        }
    }
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['message'] == 'Hello from Kitchen Service'
    assert body['status'] == 'healthy'

def test_kitchen_not_found():
    event = {
        'rawPath': '/v1/kitchen/unknown',
        'requestContext': {
            'http': {
                'method': 'GET'
            }
        }
    }
    response = app.lambda_handler(event, None)
    assert response['statusCode'] == 404
