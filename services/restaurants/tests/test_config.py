import pytest
import json
import time
import os

# Note: conftest.py fixtures are automatically available

def test_get_config_defaults(mock_tables):
    import app
    
    # 1. Setup - Mock tables are already injected into app by the fixture
    config_table = mock_tables['config']
    
    # 2. Seed Data
    config_table.put_item(Item={
        "restaurant_id": "r1",
        "configuration": {
            "operating_hours": "9-5"
        }
    })
    
    # 3. Call get_config
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:role": "restaurant_admin",
                        "custom:restaurant_id": "r1"
                    }
                }
            }
        }
    }
    
    resp = app.get_config(event, "r1")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    
    # Should return defaults mixed with overrides
    assert body["max_concurrent_orders"] == 10
    assert body["capacity_window_seconds"] == 300
    assert body["operating_hours"] == "9-5"

def test_update_config_and_get(mock_tables):
    import app
    
    config_table = mock_tables['config']
     
    config_table.put_item(Item={
        "restaurant_id": "r1"
    })
    
    # 2. Call update_config
    event = {
        "body": json.dumps({
            "max_concurrent_orders": 25,
            "capacity_window_seconds": 600
        }),
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:role": "restaurant_admin",
                        "custom:restaurant_id": "r1"
                    }
                }
            }
        }
    }
    
    resp = app.update_config(event, "r1")
    assert resp["statusCode"] == 200
    
    # 3. Verify in DB
    item_resp = config_table.get_item(Key={"restaurant_id": "r1"})
    item = item_resp["Item"]
    assert item["max_concurrent_orders"] == 25
    assert item["capacity_window_seconds"] == 600
    
    # 4. Verify via get_config
    get_event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:role": "restaurant_admin",
                        "custom:restaurant_id": "r1"
                    }
                }
            }
        }
    }
    resp = app.get_config(get_event, "r1")
    body = json.loads(resp["body"])
    assert body["max_concurrent_orders"] == 25
    assert body["capacity_window_seconds"] == 600

def test_update_config_rbac_denial(mock_tables):
    import app
    
    event = {
        "body": "{}",
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:role": "restaurant_admin",
                        "custom:restaurant_id": "r2" # Wrong restaurant
                    }
                }
            }
        }
    }
    
    resp = app.update_config(event, "r1")
    assert resp["statusCode"] == 403
