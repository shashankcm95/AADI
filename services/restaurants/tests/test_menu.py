import pytest
import json
from decimal import Decimal
import app

# ── Helper ──
def _owner_event(rest_id="r1", body=None):
    event = {
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:role": "restaurant_admin",
                        "custom:restaurant_id": rest_id,
                        "cognito:username": "owner"
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
                        "cognito:username": "admin"
                    }
                }
            }
        }
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event

# ── Tests ──

def test_get_menu_success(mock_tables):
    mock_tables['menus'].put_item(Item={
        "restaurant_id": "r1",
        "menu_version": "latest",
        "items": [
            {"id": "1", "name": "Burger", "price": Decimal("10.50")}
        ]
    })
    
    resp = app.get_menu("r1")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Burger"
    assert body["items"][0]["price"] == 10.5  # Decimal serialized to float

def test_get_menu_empty_default(mock_tables):
    resp = app.get_menu("r99")  # Non-existent
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["items"] == []

def test_update_menu_success_owner(mock_tables):
    payload = {
        "items": [
            {"name": "Pizza", "price": "15.00", "description": "Yum"}
        ]
    }
    resp = app.update_menu(_owner_event("r1", payload), "r1")
    assert resp["statusCode"] == 200
    
    # Verify DB
    item_resp = mock_tables['menus'].get_item(Key={"restaurant_id": "r1", "menu_version": "latest"})
    item = item_resp["Item"]
    assert len(item["items"]) == 1
    assert item["items"][0]["name"] == "Pizza"
    assert item["items"][0]["price"] == Decimal("15.00")
    assert item["updated_by"] == "owner"
    assert "id" in item["items"][0]  # UUID generated

def test_update_menu_success_admin(mock_tables):
    payload = {"items": [{"name": "Salad", "price": 10}]}
    resp = app.update_menu(_admin_event(payload), "r1")
    assert resp["statusCode"] == 200
    
    item_resp = mock_tables['menus'].get_item(Key={"restaurant_id": "r1", "menu_version": "latest"})
    assert item_resp["Item"]["updated_by"] == "admin"

def test_update_menu_rbac_denial(mock_tables):
    # Wrong owner
    fields = {"items": []}
    resp = app.update_menu(_owner_event("r2", fields), "r1")
    assert resp["statusCode"] == 403

def test_update_menu_validation(mock_tables):
    # Not a list
    resp = app.update_menu(_owner_event("r1", {"items": "not-list"}), "r1")
    assert resp["statusCode"] == 400
    
    # Missing name/price -> skipped (not error, verify logic)
    payload = {
        "items": [
            {"name": "Good", "price": 1},
            {"name": "Bad"},  # No price
            {"price": 5}      # No name
        ]
    }
    resp = app.update_menu(_owner_event("r1", payload), "r1")
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["count"] == 1  # Only "Good" saved
    
    # DB verify
    item = mock_tables['menus'].get_item(Key={"restaurant_id": "r1", "menu_version": "latest"})["Item"]
    assert len(item["items"]) == 1
    assert item["items"][0]["name"] == "Good"

def test_update_menu_price_parsing(mock_tables):
    payload = {
        "items": [
            {"name": "Item 1", "price": "$10.50"},
            {"name": "Item 2", "price": "1,000.00"},
            {"name": "Item 3", "price": "invalid"}  # Should be skipped
        ]
    }
    resp = app.update_menu(_owner_event("r1", payload), "r1")
    assert resp["statusCode"] == 200
    
    item = mock_tables['menus'].get_item(Key={"restaurant_id": "r1", "menu_version": "latest"})["Item"]
    assert len(item["items"]) == 2
    assert item["items"][0]["price"] == Decimal("10.50")
    assert item["items"][1]["price"] == Decimal("1000.00")
