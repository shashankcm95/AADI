import unittest

from src_orders.core.engine import decide_vicinity_update, decide_ack_upgrade, ensure_not_expired
from src_orders.core.errors import ExpiredError, InvalidStateError, NotFoundError
from src_orders.core.models import (
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_WAITING,
    STATUS_EXPIRED,
    RECEIPT_SOFT,
    RECEIPT_HARD,
)


def _base_order(**overrides):
    # minimal order dict in "storage format"
    o = {
        "order_id": "ord_test",
        "restaurant_id": "rst_001",
        "status": STATUS_PENDING,
        "expires_at": 9999999999,
        "prep_units_total": 2,
        "vicinity": False,
    }
    o.update(overrides)
    return o


class TestEnsureNotExpired(unittest.TestCase):
    def test_not_expired_ok(self):
        order = _base_order(expires_at=200)
        ensure_not_expired(order, now=199)  # should not raise

    def test_expired_raises(self):
        order = _base_order(expires_at=200)
        with self.assertRaises(ExpiredError):
            ensure_not_expired(order, now=201)


class TestDecideVicinityUpdate(unittest.TestCase):
    def test_vicinity_false_noop(self):
        order = _base_order(status=STATUS_PENDING)
        plan = decide_vicinity_update(
            order=order,
            vicinity=False,
            now=100,
            window_seconds=600,
            max_units=20,
            window_start=0,
            reserved_capacity=False,
        )
        self.assertIsNotNone(plan.response)
        self.assertEqual(plan.response["order_id"], order["order_id"])
        self.assertEqual(plan.response["status"], STATUS_PENDING)
        self.assertIsNone(plan.set_fields)
        self.assertIsNone(plan.remove_fields)

    def test_status_not_actionable_noop(self):
        order = _base_order(status=STATUS_SENT)
        plan = decide_vicinity_update(
            order=order,
            vicinity=True,
            now=100,
            window_seconds=600,
            max_units=20,
            window_start=0,
            reserved_capacity=True,
        )
        self.assertEqual(plan.response["status"], STATUS_SENT)
        self.assertIsNone(plan.set_fields)

    def test_pending_reserved_dispatch(self):
        order = _base_order(status=STATUS_PENDING, prep_units_total=2)
        plan = decide_vicinity_update(
            order=order,
            vicinity=True,
            now=123,
            window_seconds=600,
            max_units=20,
            window_start=120,
            reserved_capacity=True,
        )
        self.assertEqual(plan.response["status"], STATUS_SENT)
        self.assertEqual(plan.condition_allowed_statuses, (STATUS_PENDING, STATUS_WAITING))

        self.assertIsNotNone(plan.set_fields)
        self.assertEqual(plan.set_fields["status"], STATUS_SENT)
        self.assertEqual(plan.set_fields["vicinity"], True)
        self.assertEqual(plan.set_fields["sent_at"], 123)
        self.assertEqual(plan.set_fields["capacity_window_start"], 120)
        self.assertEqual(plan.set_fields["receipt_mode"], RECEIPT_SOFT)
        self.assertTrue(plan.set_fields["received_by_restaurant"])
        self.assertEqual(plan.set_fields["received_at"], 123)

        self.assertEqual(plan.remove_fields, ("waiting_since", "suggested_start_at"))

    def test_waiting_reserved_dispatch(self):
        order = _base_order(status=STATUS_WAITING, prep_units_total=2)
        plan = decide_vicinity_update(
            order=order,
            vicinity=True,
            now=500,
            window_seconds=600,
            max_units=20,
            window_start=480,
            reserved_capacity=True,
        )
        self.assertEqual(plan.response["status"], STATUS_SENT)
        self.assertEqual(plan.set_fields["status"], STATUS_SENT)

    def test_pending_blocked_waiting(self):
        order = _base_order(status=STATUS_PENDING)
        plan = decide_vicinity_update(
            order=order,
            vicinity=True,
            now=1000,
            window_seconds=600,
            max_units=0,
            window_start=960,
            reserved_capacity=False,
        )
        self.assertEqual(plan.response["status"], STATUS_WAITING)
        self.assertIsNotNone(plan.set_fields)
        self.assertEqual(plan.set_fields["status"], STATUS_WAITING)
        self.assertEqual(plan.set_fields["vicinity"], True)
        self.assertEqual(plan.set_fields["waiting_since"], 1000)
        self.assertEqual(plan.set_fields["suggested_start_at"], 960 + 600)


class TestDecideAckUpgrade(unittest.TestCase):
    def test_not_found_raises(self):
        with self.assertRaises(NotFoundError):
            decide_ack_upgrade(order=None, restaurant_id="rst_001", now=10)

    def test_wrong_restaurant_raises(self):
        order = _base_order(status=STATUS_SENT, restaurant_id="rst_other", receipt_mode=RECEIPT_SOFT)
        with self.assertRaises(NotFoundError):
            decide_ack_upgrade(order=order, restaurant_id="rst_001", now=10)

    def test_invalid_state_raises(self):
        order = _base_order(status=STATUS_PENDING, receipt_mode=RECEIPT_SOFT)
        with self.assertRaises(InvalidStateError):
            decide_ack_upgrade(order=order, restaurant_id="rst_001", now=10)

    def test_idempotent_when_already_hard(self):
        order = _base_order(status=STATUS_SENT, receipt_mode=RECEIPT_HARD)
        plan = decide_ack_upgrade(order=order, restaurant_id="rst_001", now=111)
        self.assertIsNotNone(plan.response)
        self.assertEqual(plan.response["receipt_mode"], RECEIPT_HARD)
        self.assertIsNone(plan.set_fields)

    def test_upgrade_soft_to_hard(self):
        order = _base_order(status=STATUS_SENT, receipt_mode=RECEIPT_SOFT)
        plan = decide_ack_upgrade(order=order, restaurant_id="rst_001", now=222)
        self.assertEqual(plan.condition_allowed_statuses, (STATUS_SENT,))
        self.assertIsNotNone(plan.set_fields)
        self.assertEqual(plan.set_fields["receipt_mode"], RECEIPT_HARD)
        self.assertEqual(plan.set_fields["received_at"], 222)
        self.assertEqual(plan.response["receipt_mode"], RECEIPT_HARD)
        self.assertEqual(plan.response["received_at"], 222)


if __name__ == "__main__":
    unittest.main()

