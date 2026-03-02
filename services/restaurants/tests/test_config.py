import json
import pytest

# conftest.py adds src/ to path and handles module cleanup
from conftest import app as restaurants_app

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
    
    resp = restaurants_app.get_config(event, "r1")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    
    # Should return defaults mixed with overrides
    assert body["max_concurrent_orders"] == 10
    assert body["capacity_window_seconds"] == 300
    assert body["dispatch_trigger_zone"] == "ZONE_1"
    assert body["dispatch_trigger_event"] == "5_MIN_OUT"
    assert body["zone_distances_m"] == {"ZONE_1": 1500, "ZONE_2": 150, "ZONE_3": 30}
    assert body["zone_labels"] == {"ZONE_1": "Zone 1", "ZONE_2": "Zone 2", "ZONE_3": "Zone 3"}
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
            "capacity_window_seconds": 600,
            "dispatch_trigger_zone": "ZONE_2",
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
    
    resp = restaurants_app.update_config(event, "r1")
    assert resp["statusCode"] == 200
    
    # 3. Verify in DB
    item_resp = config_table.get_item(Key={"restaurant_id": "r1"})
    item = item_resp["Item"]
    assert item["max_concurrent_orders"] == 25
    assert item["capacity_window_seconds"] == 600
    assert item["dispatch_trigger_zone"] == "ZONE_2"
    assert item["dispatch_trigger_event"] == "PARKING"
    
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
    resp = restaurants_app.get_config(get_event, "r1")
    body = json.loads(resp["body"])
    assert body["max_concurrent_orders"] == 25
    assert body["capacity_window_seconds"] == 600
    assert body["dispatch_trigger_zone"] == "ZONE_2"
    assert body["dispatch_trigger_event"] == "PARKING"

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
    
    resp = restaurants_app.update_config(event, "r1")
    assert resp["statusCode"] == 403


def test_update_config_rejects_invalid_dispatch_trigger(mock_tables):
    config_table = mock_tables['config']
    config_table.put_item(Item={"restaurant_id": "r1"})

    event = _owner_event(body={"dispatch_trigger_event": "EARLY"})
    resp = restaurants_app.update_config(event, "r1")
    assert resp["statusCode"] == 400
    assert "dispatch_trigger_event" in json.loads(resp["body"])["error"]


def test_update_config_rejects_invalid_dispatch_zone(mock_tables):
    config_table = mock_tables['config']
    config_table.put_item(Item={"restaurant_id": "r1"})

    event = _owner_event(body={"dispatch_trigger_zone": "ZONE_9"})
    resp = restaurants_app.update_config(event, "r1")
    assert resp["statusCode"] == 400
    assert "dispatch_trigger_zone" in json.loads(resp["body"])["error"]


def test_update_config_legacy_event_sets_zone(mock_tables):
    config_table = mock_tables['config']
    config_table.put_item(Item={"restaurant_id": "r1"})

    resp = restaurants_app.update_config(_owner_event(body={"dispatch_trigger_event": "AT_DOOR"}), "r1")
    assert resp["statusCode"] == 200
    item = config_table.get_item(Key={"restaurant_id": "r1"})["Item"]
    assert item["dispatch_trigger_event"] == "AT_DOOR"
    assert item["dispatch_trigger_zone"] == "ZONE_3"


def test_update_config_rejects_mismatched_zone_and_event(mock_tables):
    config_table = mock_tables['config']
    config_table.put_item(Item={"restaurant_id": "r1"})

    resp = restaurants_app.update_config(
        _owner_event(body={"dispatch_trigger_zone": "ZONE_1", "dispatch_trigger_event": "AT_DOOR"}),
        "r1",
    )
    assert resp["statusCode"] == 400
    assert "do not match" in json.loads(resp["body"])["error"]


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


def _admin_event(body=None):
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:role": "admin",
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

    resp = restaurants_app.get_config(_owner_event(), "r1")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["pos_enabled"] is False
    assert body["pos_connections"] == []


def test_update_config_pos_connections_lifecycle(mock_tables):
    """Create POS connections, retrieve with masked secrets, update with masked echo."""
    mock_tables['config'].put_item(Item={"restaurant_id": "r1"})

    # 1. Add a POS connection
    resp = restaurants_app.update_config(_owner_event(body={
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
    resp = restaurants_app.get_config(_owner_event(), "r1")
    body = json.loads(resp["body"])
    assert body["pos_enabled"] is True
    assert len(body["pos_connections"]) == 1
    conn = body["pos_connections"][0]
    assert conn["provider"] == "square"
    assert conn["webhook_secret"] == "***…cret"  # last 4 of "whsec_abc123secret"
    assert conn["connection_id"]  # auto-generated UUID

    # 3. Re-save with masked secret → should preserve original
    conn_id = conn["connection_id"]
    resp = restaurants_app.update_config(_owner_event(body={
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

    resp = restaurants_app.update_config(_owner_event(body={
        "pos_connections": [{"webhook_url": "http://insecure.example.com", "provider": "custom"}]
    }), "r1")
    assert resp["statusCode"] == 400
    assert "HTTPS" in json.loads(resp["body"])["error"]


def test_update_config_pos_rejects_invalid_provider(mock_tables):
    """Invalid POS provider should be rejected."""
    mock_tables['config'].put_item(Item={"restaurant_id": "r1"})

    resp = restaurants_app.update_config(_owner_event(body={
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
    resp = restaurants_app.update_config(_owner_event(body={"pos_connections": connections}), "r1")
    assert resp["statusCode"] == 400
    assert "5" in json.loads(resp["body"])["error"]


def test_get_global_config_admin_defaults(mock_tables):
    resp = restaurants_app.get_global_config(_admin_event())
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["zone_distances_m"] == {"ZONE_1": 1500, "ZONE_2": 150, "ZONE_3": 30}
    assert body["zone_labels"] == {"ZONE_1": "Zone 1", "ZONE_2": "Zone 2", "ZONE_3": "Zone 3"}
    assert body["default_dispatch_trigger_zone"] == "ZONE_1"
    assert body["geofence_sync"] is None


def test_get_global_config_denies_non_admin(mock_tables):
    resp = restaurants_app.get_global_config(_owner_event())
    assert resp["statusCode"] == 403


def test_update_global_config_updates_distances_and_enqueues_resync(mock_tables, monkeypatch):
    import handlers.config as h_config

    sent_messages = []

    class _FakeSQS:
        def send_message(self, QueueUrl, MessageBody):
            sent_messages.append({
                "QueueUrl": QueueUrl,
                "MessageBody": MessageBody,
            })
            return {"MessageId": "msg-1"}

    monkeypatch.setattr(h_config, "_sqs_client", _FakeSQS())
    monkeypatch.setattr(h_config, "GEOFENCE_RESYNC_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/geofence-resync")

    resp = restaurants_app.update_global_config(
        _admin_event(body={
            "zone_distances_m": {"ZONE_1": 1800, "ZONE_3": 45},
            "zone_labels": {"ZONE_1": "Far", "ZONE_2": "Queue", "ZONE_3": "Doorstep"},
        })
    )
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["zone_distances_m"] == {"ZONE_1": 1800, "ZONE_2": 150, "ZONE_3": 45}
    assert body["zone_labels"] == {"ZONE_1": "Far", "ZONE_2": "Queue", "ZONE_3": "Doorstep"}

    global_item = mock_tables["config"].get_item(Key={"restaurant_id": "__GLOBAL__"})["Item"]
    assert global_item["zone_distances_m"] == {"ZONE_1": 1800, "ZONE_2": 150, "ZONE_3": 45}
    assert global_item["zone_labels"] == {"ZONE_1": "Far", "ZONE_2": "Queue", "ZONE_3": "Doorstep"}
    assert body["geofence_sync"]["status"] == "QUEUED"
    assert body["geofence_sync"]["attempted"] == 0
    assert body["geofence_sync"]["updated"] == 0
    assert body["geofence_sync"]["failed"] == 0
    assert body["geofence_sync"]["job_id"]
    assert global_item["geofence_sync"]["job_id"] == body["geofence_sync"]["job_id"]
    assert len(sent_messages) == 1
    payload = json.loads(sent_messages[0]["MessageBody"])
    assert payload["task_type"] == "geofence_resync"
    assert payload["job_id"] == body["geofence_sync"]["job_id"]


def test_update_global_config_returns_error_when_enqueue_fails(mock_tables, monkeypatch):
    import handlers.config as h_config

    class _BrokenSQS:
        def send_message(self, QueueUrl, MessageBody):
            raise RuntimeError("queue unavailable")

    monkeypatch.setattr(h_config, "_sqs_client", _BrokenSQS())
    monkeypatch.setattr(h_config, "GEOFENCE_RESYNC_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/geofence-resync")

    resp = restaurants_app.update_global_config(
        _admin_event(body={"zone_distances_m": {"ZONE_1": 1700}})
    )
    assert resp["statusCode"] == 500
    body = json.loads(resp["body"])
    assert "enqueue failed" in body["error"]
    assert body["geofence_sync"]["status"] == "ENQUEUE_FAILED"
    assert body["geofence_sync"]["job_id"]


def test_update_global_config_rejects_invalid_distance(mock_tables):
    resp = restaurants_app.update_global_config(
        _admin_event(body={"zone_distances_m": {"ZONE_1": "abc"}})
    )
    assert resp["statusCode"] == 400
    assert "ZONE_1" in json.loads(resp["body"])["error"]


def test_update_global_config_rejects_empty_label(mock_tables):
    resp = restaurants_app.update_global_config(
        _admin_event(body={"zone_labels": {"ZONE_1": "  "}})
    )
    assert resp["statusCode"] == 400
    assert "cannot be empty" in json.loads(resp["body"])["error"]


def test_update_global_config_updates_labels_only(mock_tables, monkeypatch):
    import handlers.config as h_config

    class _FakeSQS:
        def send_message(self, QueueUrl, MessageBody):
            return {"MessageId": "msg-1"}

    monkeypatch.setattr(h_config, "_sqs_client", _FakeSQS())
    monkeypatch.setattr(h_config, "GEOFENCE_RESYNC_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/123/geofence-resync")

    resp = restaurants_app.update_global_config(
        _admin_event(body={"zone_labels": {"ZONE_2": "Parking"}})
    )
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["zone_labels"]["ZONE_2"] == "Parking"
    assert body["zone_distances_m"] == {"ZONE_1": 1500, "ZONE_2": 150, "ZONE_3": 30}


def test_update_global_config_denies_non_admin(mock_tables):
    resp = restaurants_app.update_global_config(
        _owner_event(body={"zone_distances_m": {"ZONE_1": 1700}})
    )
    assert resp["statusCode"] == 403
