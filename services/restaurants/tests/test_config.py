import pytest
import json
import time
import os
import sys

# conftest.py adds src/ to path and handles module cleanup
import app

def test_get_config_defaults(mock_tables):
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


# ── Helper ──
def _owner_event(body=None):
    """Build a restaurant_admin event for r1."""
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
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def test_get_config_includes_pos_defaults(mock_tables):
    """get_config returns pos_enabled=false and empty pos_connections by default."""
    mock_tables['config'].put_item(Item={"restaurant_id": "r1"})

    resp = app.get_config(_owner_event(), "r1")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["pos_enabled"] is False
    assert body["pos_connections"] == []


def test_update_config_pos_connections_lifecycle(mock_tables):
    """Create POS connections, retrieve with masked secrets, update with masked echo."""
    mock_tables['config'].put_item(Item={"restaurant_id": "r1"})

    # 1. Add a POS connection
    resp = app.update_config(_owner_event(body={
        "pos_enabled": True,
        "pos_connections": [
            {
                "label": "Square - Dine In",
                "provider": "square",
                "webhook_url": "https://api.squareup.com/v2/orders",
                "webhook_secret": "whsec_abc123secret",
                "enabled": True,
            }
        ]
    }), "r1")
    assert resp["statusCode"] == 200

    # 2. GET should return masked secret
    resp = app.get_config(_owner_event(), "r1")
    body = json.loads(resp["body"])
    assert body["pos_enabled"] is True
    assert len(body["pos_connections"]) == 1
    conn = body["pos_connections"][0]
    assert conn["provider"] == "square"
    assert conn["webhook_secret"] == "***…cret"  # last 4 of "whsec_abc123secret"
    assert conn["connection_id"]  # auto-generated UUID

    # 3. Re-save with masked secret → should preserve original
    conn_id = conn["connection_id"]
    resp = app.update_config(_owner_event(body={
        "pos_connections": [
            {
                "connection_id": conn_id,
                "label": "Square - Updated",
                "provider": "square",
                "webhook_url": "https://api.squareup.com/v2/orders",
                "webhook_secret": "***…cret",  # Masked value sent back
                "enabled": True,
            }
        ]
    }), "r1")
    assert resp["statusCode"] == 200

    # 4. Verify original secret was preserved
    raw = mock_tables['config'].get_item(Key={"restaurant_id": "r1"})["Item"]
    assert raw["pos_connections"][0]["webhook_secret"] == "whsec_abc123secret"
    assert raw["pos_connections"][0]["label"] == "Square - Updated"


def test_update_config_pos_rejects_http_url(mock_tables):
    """Non-HTTPS webhook URLs should be rejected."""
    mock_tables['config'].put_item(Item={"restaurant_id": "r1"})

    resp = app.update_config(_owner_event(body={
        "pos_connections": [{"webhook_url": "http://insecure.example.com", "provider": "custom"}]
    }), "r1")
    assert resp["statusCode"] == 400
    assert "HTTPS" in json.loads(resp["body"])["error"]


def test_update_config_pos_rejects_invalid_provider(mock_tables):
    """Invalid POS provider should be rejected."""
    mock_tables['config'].put_item(Item={"restaurant_id": "r1"})

    resp = app.update_config(_owner_event(body={
        "pos_connections": [{"webhook_url": "https://ok.com", "provider": "stripe"}]
    }), "r1")
    assert resp["statusCode"] == 400
    assert "provider" in json.loads(resp["body"])["error"]


def test_update_config_pos_rejects_too_many_connections(mock_tables):
    """More than 5 POS connections should be rejected."""
    mock_tables['config'].put_item(Item={"restaurant_id": "r1"})

    connections = [
        {"webhook_url": f"https://hook{i}.com", "provider": "custom"}
        for i in range(6)
    ]
    resp = app.update_config(_owner_event(body={"pos_connections": connections}), "r1")
    assert resp["statusCode"] == 400
    assert "5" in json.loads(resp["body"])["error"]

