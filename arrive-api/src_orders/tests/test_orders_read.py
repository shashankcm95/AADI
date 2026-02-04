import os
import unittest
from unittest.mock import patch, MagicMock
from src_orders import app


class TestGetOrder(unittest.TestCase):
    def test_get_order_not_found(self):
        with patch.object(app, "_deps") as deps:
            repo = MagicMock()
            repo.get_order.return_value = None
            deps.return_value = (repo, MagicMock(), MagicMock(), MagicMock())
            resp = app.get_order("ord_missing")
            self.assertEqual(resp["statusCode"], 404)
            

    def test_get_order_success_min_fields(self):
        fake = {
            "order_id": "ord_1",
            "restaurant_id": "rst_001",
            "status": "PENDING_NOT_SENT",
            "items": [],
            "expires_at": 123,
        }
        with patch.object(app, "_deps") as deps:
            repo = MagicMock() 
            repo.get_order.return_value = fake
            deps.return_value = (repo, MagicMock(), MagicMock(), MagicMock())
            resp = app.get_order("ord_1")
            self.assertEqual(resp["statusCode"], 200)
            self.assertIn('"order_id": "ord_1"', resp["body"])
            self.assertIn('"restaurant_id": "rst_001"', resp["body"])
            
