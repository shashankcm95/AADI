import json
import unittest
from unittest.mock import patch, MagicMock

from src_orders import app


class _FakeIdempRepo:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def assert_same_request(self, item, request_hash):
        # mimic adapter behavior
        if item and item.get("request_hash") != request_hash:
            raise app.IdempotencyConflictError()

    def put_response_if_absent(self, idempotency_key, request_hash, response_status, response_body, created_at, ttl):
        if idempotency_key in self.store:
            return False
        self.store[idempotency_key] = {
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "response_status": response_status,
            "response_body": response_body,
            "created_at": created_at,
            "ttl": ttl,
        }
        return True


class TestCreateOrderIdempotency(unittest.TestCase):
    def _event(self, body: dict, idem_key: str):
        return {
            "rawPath": "/v1/orders",
            "requestContext": {"http": {"method": "POST"}},
            "headers": {"Idempotency-Key": idem_key, "Content-Type": "application/json"},
            "body": json.dumps(body),
        }

    def test_same_idempotency_key_returns_same_response(self):
        fake_idemp = _FakeIdempRepo()

        orders_repo = MagicMock()
        config_repo = MagicMock()
        capacity_repo = MagicMock()

        body = {
            "restaurant_id": "rst_001",
            "customer_name": "Test",
            "items": [{"id": "it_001", "qty": 1, "name": "Turkey", "price_cents": 100, "prep_units": 2}],
        }

        with patch.object(app, "_deps", return_value=(orders_repo, config_repo, capacity_repo)), \
             patch.object(app, "_idemp_repo", return_value=fake_idemp), \
             patch.object(app.uuid, "uuid4") as u4, \
             patch.object(app.time, "time", return_value=1700000000):

            u4.return_value.hex = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

            # First request: should create new order (put_order called)
            resp1 = app.lambda_handler(self._event(body, "k1"), None)
            self.assertEqual(resp1["statusCode"], 201)
            self.assertEqual(orders_repo.put_order.call_count, 1)

            # Second request: same key + same payload should return cached response
            resp2 = app.lambda_handler(self._event(body, "k1"), None)
            self.assertEqual(resp2["statusCode"], 201)
            self.assertEqual(resp2["body"], resp1["body"])
            self.assertEqual(orders_repo.put_order.call_count, 1)  # still 1 (no double create)

    def test_same_idempotency_key_different_payload_409(self):
        fake_idemp = _FakeIdempRepo()

        orders_repo = MagicMock()
        config_repo = MagicMock()
        capacity_repo = MagicMock()

        body1 = {
            "restaurant_id": "rst_001",
            "customer_name": "Test",
            "items": [{"id": "it_001", "qty": 1, "name": "Turkey", "price_cents": 100, "prep_units": 2}],
        }
        body2 = {
            "restaurant_id": "rst_001",
            "customer_name": "Test_CHANGED",
            "items": [{"id": "it_001", "qty": 1, "name": "Turkey", "price_cents": 100, "prep_units": 2}],
        }

        with patch.object(app, "_deps", return_value=(orders_repo, config_repo, capacity_repo)), \
             patch.object(app, "_idemp_repo", return_value=fake_idemp), \
             patch.object(app.uuid, "uuid4") as u4, \
             patch.object(app.time, "time", return_value=1700000000):

            u4.return_value.hex = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

            resp1 = app.lambda_handler(self._event(body1, "k1"), None)
            self.assertEqual(resp1["statusCode"], 201)
            self.assertEqual(orders_repo.put_order.call_count, 1)

            # Same key, different body should conflict
            resp2 = app.lambda_handler(self._event(body2, "k1"), None)
            self.assertEqual(resp2["statusCode"], 409)
            self.assertIn("IDEMPOTENCY_KEY_REUSED", resp2["body"])
            self.assertEqual(orders_repo.put_order.call_count, 1)  # no second create


if __name__ == "__main__":
    unittest.main()
