import unittest

from src_orders.core.engine import (
    decide_vicinity_update,
    decide_ack_upgrade,
    ensure_not_expired,
    decide_cancel,
    decide_restaurant_status_update,
)
from src_orders.core.errors import ExpiredError, InvalidStateError, NotFoundError
from src_orders.core.models import (
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_WAITING,
    STATUS_EXPIRED,
    STATUS_CANCELED,
    STATUS_IN_PROGRESS,
    STATUS_READY,
    STATUS_COMPLETED,
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

class TestDecideCancel(unittest.TestCase):
    def test_cancel_pending_ok(self):
        order = _base_order(status=STATUS_PENDING)
        plan = decide_cancel(order=order, now=100)

        self.assertEqual(plan.condition_allowed_statuses, (STATUS_PENDING, STATUS_WAITING))
        self.assertIsNotNone(plan.set_fields)
        self.assertEqual(plan.set_fields["status"], STATUS_CANCELED)
        self.assertEqual(plan.set_fields["canceled_at"], 100)
        self.assertEqual(plan.remove_fields, ("waiting_since", "suggested_start_at"))

        self.assertIsNotNone(plan.response)
        self.assertEqual(plan.response["status"], STATUS_CANCELED)
        self.assertEqual(plan.response["canceled_at"], 100)

    def test_cancel_waiting_ok(self):
        order = _base_order(status=STATUS_WAITING, waiting_since=50, suggested_start_at=600)
        plan = decide_cancel(order=order, now=200)

        self.assertEqual(plan.set_fields["status"], STATUS_CANCELED)
        self.assertEqual(plan.remove_fields, ("waiting_since", "suggested_start_at"))

    def test_cancel_sent_raises(self):
        order = _base_order(status=STATUS_SENT)
        with self.assertRaises(InvalidStateError):
            decide_cancel(order=order, now=10)

    def test_cancel_not_found_raises(self):
        with self.assertRaises(NotFoundError):
            decide_cancel(order=None, now=10)


class TestDecideRestaurantStatusUpdate(unittest.TestCase):
    def test_not_found_raises(self):
        with self.assertRaises(NotFoundError):
            decide_restaurant_status_update(
                order=None, restaurant_id="rst_001", new_status=STATUS_IN_PROGRESS, now=10
            )

    def test_wrong_restaurant_raises(self):
        order = _base_order(status=STATUS_SENT, restaurant_id="rst_other")
        with self.assertRaises(NotFoundError):
            decide_restaurant_status_update(
                order=order, restaurant_id="rst_001", new_status=STATUS_IN_PROGRESS, now=10
            )

    def test_invalid_target_status_raises(self):
        order = _base_order(status=STATUS_SENT)
        with self.assertRaises(InvalidStateError):
            decide_restaurant_status_update(
                order=order, restaurant_id="rst_001", new_status="BOGUS", now=10
            )

    def test_idempotent_noop(self):
        order = _base_order(status=STATUS_IN_PROGRESS)
        plan = decide_restaurant_status_update(
            order=order, restaurant_id="rst_001", new_status=STATUS_IN_PROGRESS, now=10
        )
        self.assertIsNotNone(plan.response)
        self.assertEqual(plan.response["status"], STATUS_IN_PROGRESS)
        self.assertIsNone(plan.set_fields)
        self.assertIsNone(plan.condition_allowed_statuses)

    def test_sent_to_in_progress_ok(self):
        order = _base_order(status=STATUS_SENT)
        plan = decide_restaurant_status_update(
            order=order, restaurant_id="rst_001", new_status=STATUS_IN_PROGRESS, now=100
        )
        self.assertEqual(plan.condition_allowed_statuses, (STATUS_SENT,))
        self.assertEqual(plan.set_fields["status"], STATUS_IN_PROGRESS)
        self.assertEqual(plan.set_fields["updated_at"], 100)
        self.assertEqual(plan.set_fields["started_at"], 100)
        self.assertEqual(plan.response["status"], STATUS_IN_PROGRESS)

    def test_in_progress_to_ready_ok(self):
        order = _base_order(status=STATUS_IN_PROGRESS)
        plan = decide_restaurant_status_update(
            order=order, restaurant_id="rst_001", new_status=STATUS_READY, now=200
        )
        self.assertEqual(plan.condition_allowed_statuses, (STATUS_IN_PROGRESS,))
        self.assertEqual(plan.set_fields["status"], STATUS_READY)
        self.assertEqual(plan.set_fields["updated_at"], 200)
        self.assertEqual(plan.set_fields["ready_at"], 200)

    def test_ready_to_completed_ok(self):
        order = _base_order(status=STATUS_READY)
        plan = decide_restaurant_status_update(
            order=order, restaurant_id="rst_001", new_status=STATUS_COMPLETED, now=300
        )
        self.assertEqual(plan.condition_allowed_statuses, (STATUS_READY,))
        self.assertEqual(plan.set_fields["status"], STATUS_COMPLETED)
        self.assertEqual(plan.set_fields["updated_at"], 300)
        self.assertEqual(plan.set_fields["completed_at"], 300)

    def test_invalid_transition_raises(self):
        # Can't jump SENT -> READY
        order = _base_order(status=STATUS_SENT)
        with self.assertRaises(InvalidStateError):
            decide_restaurant_status_update(
                order=order, restaurant_id="rst_001", new_status=STATUS_READY, now=10
            )

        # Can't move backward READY -> IN_PROGRESS
        order2 = _base_order(status=STATUS_READY)
        with self.assertRaises(InvalidStateError):
            decide_restaurant_status_update(
                order=order2, restaurant_id="rst_001", new_status=STATUS_IN_PROGRESS, now=10
            )

if __name__ == "__main__":
    unittest.main()

