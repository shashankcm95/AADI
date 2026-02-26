import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


SHARED_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../services/shared/python")
)
SRC_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../services/restaurants/src")
)
sys.path.insert(0, SHARED_PATH)
sys.path.insert(0, SRC_PATH)
sys.modules.pop("app", None)

with patch("boto3.resource"), patch("boto3.client"):
    import app


@pytest.fixture
def mock_tables():
    restaurants_table = MagicMock()
    config_table = MagicMock()
    
    # Patch app-level references
    app.restaurants_table = restaurants_table
    app.config_table = config_table
    
    # Patch handlers-level references (critical for create_restaurant)
    import handlers.restaurants
    handlers.restaurants.restaurants_table = restaurants_table
    handlers.restaurants.config_table = config_table
    
    yield restaurants_table, config_table


def _admin_event(body: dict) -> dict:
    return {
        "routeKey": "POST /v1/restaurants",
        "body": json.dumps(body),
        "requestContext": {
            "authorizer": {
                "jwt": {
                    "claims": {
                        "custom:role": "admin"
                    }
                }
            }
        },
    }


def test_create_restaurant_as_admin(mock_tables):
    restaurants_table, config_table = mock_tables
    event = _admin_event(
        {
            "name": "Test Bistro",
            "street": "123 Test St",
            "city": "Austin",
            "state": "TX",
            "zip": "78701",
            "contact_email": "test@example.com",
            "operating_hours": "10:00-23:00",
        }
    )

    with patch("handlers.restaurants.geocode_address", return_value=None):
        response = app.lambda_handler(event, None)

    assert response["statusCode"] == 201
    payload = json.loads(response["body"])
    assert payload["user_status"] in ("CREATED", "LINKED")

    restaurants_table.put_item.assert_called_once()
    config_table.put_item.assert_called_once()

    restaurant_item = restaurants_table.put_item.call_args.kwargs["Item"]
    assert restaurant_item["name"] == "Test Bistro"
    assert restaurant_item["active"] is False
