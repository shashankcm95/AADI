import pytest
import json
import os
import importlib.util

APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/app.py'))
spec = importlib.util.spec_from_file_location("kitchen_app", APP_PATH)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

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
