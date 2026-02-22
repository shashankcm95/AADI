import json
import importlib
import os
import sys
from unittest.mock import MagicMock

from botocore.exceptions import ClientError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))
for _module in ("db", "geofence_events"):
    sys.modules.pop(_module, None)

import db


def _event(event_id="evt-1", event_type="ENTER", geofence_id="rest_1|AT_DOOR", device_id="cust_1"):
    return {
        "id": event_id,
        "source": "aws.geo",
        "detail-type": "Location Geofence Event",
        "detail": {
            "EventType": event_type,
            "GeofenceCollection": "stack-arrival-geofences",
            "GeofenceId": geofence_id,
            "DeviceId": device_id,
        },
    }


def _load_handler():
    global db
    for _module in ("db", "geofence_events"):
        sys.modules.pop(_module, None)
    db = importlib.import_module("db")
    return importlib.import_module("geofence_events")


def test_geofence_event_records_shadow(monkeypatch):
    handler = _load_handler()
    orders_table = MagicMock()
    geofence_events_table = MagicMock()
    orders_table.query.return_value = {
        "Items": [{
            "order_id": "ord_1",
            "customer_id": "cust_1",
            "restaurant_id": "rest_1",
            "status": "PENDING_NOT_SENT",
        }]
    }
    monkeypatch.setattr(db, "orders_table", orders_table)
    monkeypatch.setattr(db, "geofence_events_table", geofence_events_table)
    monkeypatch.setenv("LOCATION_GEOFENCE_CUTOVER_ENABLED", "false")
    monkeypatch.setenv("LOCATION_GEOFENCE_COLLECTION_NAME", "stack-arrival-geofences")
    monkeypatch.setattr(handler, "update_vicinity", MagicMock(return_value={"statusCode": 200}))

    response = handler.lambda_handler(_event(), None)
    payload = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert payload["mode"] == "shadow"
    orders_table.update_item.assert_called_once()
    handler.update_vicinity.assert_not_called()


def test_geofence_event_applies_cutover_when_enabled(monkeypatch):
    handler = _load_handler()
    orders_table = MagicMock()
    geofence_events_table = MagicMock()
    orders_table.query.return_value = {
        "Items": [{
            "order_id": "ord_2",
            "customer_id": "cust_1",
            "restaurant_id": "rest_1",
            "status": "WAITING_FOR_CAPACITY",
        }]
    }
    monkeypatch.setattr(db, "orders_table", orders_table)
    monkeypatch.setattr(db, "geofence_events_table", geofence_events_table)
    monkeypatch.setenv("LOCATION_GEOFENCE_CUTOVER_ENABLED", "true")
    monkeypatch.setenv("LOCATION_GEOFENCE_COLLECTION_NAME", "stack-arrival-geofences")

    mock_update = MagicMock(return_value={"statusCode": 200, "body": json.dumps({"status": "SENT_TO_DESTINATION"})})
    monkeypatch.setattr(handler, "update_vicinity", mock_update)

    response = handler.lambda_handler(_event(event_id="evt-2", geofence_id="rest_1|5_MIN_OUT"), None)
    assert response["statusCode"] == 200
    mock_update.assert_called_once()
    # Shadow trail is still recorded even in cutover mode.
    orders_table.update_item.assert_called_once()


def test_geofence_force_shadow_overrides_cutover(monkeypatch):
    handler = _load_handler()
    orders_table = MagicMock()
    geofence_events_table = MagicMock()
    orders_table.query.return_value = {
        "Items": [{
            "order_id": "ord_3",
            "customer_id": "cust_1",
            "restaurant_id": "rest_1",
            "status": "WAITING_FOR_CAPACITY",
        }]
    }
    monkeypatch.setattr(db, "orders_table", orders_table)
    monkeypatch.setattr(db, "geofence_events_table", geofence_events_table)
    monkeypatch.setenv("LOCATION_GEOFENCE_CUTOVER_ENABLED", "true")
    monkeypatch.setenv("LOCATION_GEOFENCE_FORCE_SHADOW", "true")
    monkeypatch.setenv("LOCATION_GEOFENCE_COLLECTION_NAME", "stack-arrival-geofences")

    mock_update = MagicMock(return_value={"statusCode": 200})
    monkeypatch.setattr(handler, "update_vicinity", mock_update)

    response = handler.lambda_handler(_event(event_id="evt-3", geofence_id="rest_1|PARKING"), None)
    payload = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert payload["mode"] == "forced_shadow"
    orders_table.update_item.assert_called_once()
    mock_update.assert_not_called()


def test_geofence_event_deduplicates(monkeypatch):
    handler = _load_handler()
    orders_table = MagicMock()
    geofence_events_table = MagicMock()
    geofence_events_table.put_item.side_effect = ClientError(
        error_response={"Error": {"Code": "ConditionalCheckFailedException", "Message": "duplicate"}},
        operation_name="PutItem",
    )

    monkeypatch.setattr(db, "orders_table", orders_table)
    monkeypatch.setattr(db, "geofence_events_table", geofence_events_table)
    monkeypatch.setenv("LOCATION_GEOFENCE_CUTOVER_ENABLED", "false")
    monkeypatch.setenv("LOCATION_GEOFENCE_COLLECTION_NAME", "stack-arrival-geofences")

    response = handler.lambda_handler(_event(event_id="evt-dup"), None)
    payload = json.loads(response["body"])
    assert payload["reason"] == "duplicate_event"
    orders_table.query.assert_not_called()
