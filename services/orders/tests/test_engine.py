"""
Comprehensive tests for engine.py decision functions.

Tests cover:
- decide_ack_upgrade: acknowledgement flow
- decide_cancel: cancellation flow
- decide_destination_status_update: full state machine transitions
- decide_arrival_update: progressive arrival events
- create_session_model + calculate_arrive_fee: session creation and fees
- validate_resources_payload: input validation
"""
import pytest

import engine
from engine import (
    decide_ack_upgrade,
    decide_cancel,
    decide_destination_status_update,
    decide_arrival_update,
    decide_vicinity_update,
    create_session_model,
    calculate_arrive_fee,
    validate_resources_payload,
    validate_destination_owns_session,
    ensure_not_expired,
    UpdatePlan,
)
from models import (
    STATUS_PENDING, STATUS_SENT, STATUS_WAITING, STATUS_EXPIRED,
    STATUS_CANCELED, STATUS_IN_PROGRESS, STATUS_READY,
    STATUS_FULFILLING, STATUS_COMPLETED,
    RECEIPT_SOFT, RECEIPT_HARD,
    PAYMENT_MODE_AT_RESTAURANT,
)
from errors import NotFoundError, InvalidStateError, ValidationError, ExpiredError

NOW = 1000


# =============================================================================
# decide_ack_upgrade
# =============================================================================
class TestDecideAckUpgrade:
    def _session(self, **overrides):
        base = {
            "session_id": "s1",
            "destination_id": "r1",
            "status": STATUS_SENT,
            "receipt_mode": RECEIPT_SOFT,
        }
        base.update(overrides)
        return base

    def test_soft_to_hard_ack(self):
        plan = decide_ack_upgrade(self._session(), "r1", NOW)
        assert plan.set_fields["receipt_mode"] == RECEIPT_HARD
        assert plan.set_fields["received_at"] == NOW
        assert plan.condition_allowed_statuses == (STATUS_SENT,)

    def test_already_hard_is_idempotent(self):
        plan = decide_ack_upgrade(self._session(receipt_mode=RECEIPT_HARD), "r1", NOW)
        assert plan.set_fields is None  # No storage change
        assert plan.response["receipt_mode"] == RECEIPT_HARD

    def test_wrong_destination_raises_not_found(self):
        with pytest.raises(NotFoundError):
            decide_ack_upgrade(self._session(), "wrong_restaurant", NOW)

    def test_not_sent_raises_invalid_state(self):
        with pytest.raises(InvalidStateError):
            decide_ack_upgrade(self._session(status=STATUS_PENDING), "r1", NOW)

    def test_completed_raises_invalid_state(self):
        with pytest.raises(InvalidStateError):
            decide_ack_upgrade(self._session(status=STATUS_COMPLETED), "r1", NOW)

    def test_legacy_keys(self):
        """Test with old restaurant_id/order_id keys."""
        session = {
            "order_id": "o1",
            "restaurant_id": "r1",
            "status": STATUS_SENT,
            "receipt_mode": RECEIPT_SOFT,
        }
        plan = decide_ack_upgrade(session, "r1", NOW)
        assert plan.set_fields["receipt_mode"] == RECEIPT_HARD
        assert plan.response["session_id"] == "o1"


# =============================================================================
# decide_cancel
# =============================================================================
class TestDecideCancel:
    def test_cancel_pending(self):
        session = {"session_id": "s1", "status": STATUS_PENDING}
        plan = decide_cancel(session, NOW)
        assert plan.set_fields["status"] == STATUS_CANCELED
        assert plan.set_fields["canceled_at"] == NOW
        assert plan.condition_allowed_statuses == (STATUS_PENDING, STATUS_WAITING)
        assert "waiting_since" in plan.remove_fields

    def test_cancel_waiting(self):
        session = {"session_id": "s1", "status": STATUS_WAITING}
        plan = decide_cancel(session, NOW)
        assert plan.set_fields["status"] == STATUS_CANCELED

    def test_cancel_sent_raises_invalid_state(self):
        session = {"session_id": "s1", "status": STATUS_SENT}
        with pytest.raises(InvalidStateError):
            decide_cancel(session, NOW)

    def test_cancel_in_progress_raises_invalid_state(self):
        session = {"session_id": "s1", "status": STATUS_IN_PROGRESS}
        with pytest.raises(InvalidStateError):
            decide_cancel(session, NOW)

    def test_cancel_completed_raises_invalid_state(self):
        session = {"session_id": "s1", "status": STATUS_COMPLETED}
        with pytest.raises(InvalidStateError):
            decide_cancel(session, NOW)

    def test_cancel_none_session_raises_not_found(self):
        with pytest.raises(NotFoundError):
            decide_cancel(None, NOW)

    def test_cancel_response_includes_session_id(self):
        session = {"session_id": "abc", "status": STATUS_PENDING}
        plan = decide_cancel(session, NOW)
        assert plan.response["session_id"] == "abc"
        assert plan.response["status"] == STATUS_CANCELED


# =============================================================================
# decide_destination_status_update (State Machine)
# =============================================================================
class TestDecideDestinationStatusUpdate:
    def _session(self, status, **overrides):
        base = {"session_id": "s1", "destination_id": "r1", "status": status}
        base.update(overrides)
        return base

    # --- Legal Transitions ---
    def test_sent_to_in_progress(self):
        plan = decide_destination_status_update(
            self._session(STATUS_SENT), "r1", STATUS_IN_PROGRESS, NOW
        )
        assert plan.set_fields["status"] == STATUS_IN_PROGRESS
        assert plan.set_fields["started_at"] == NOW
        assert plan.condition_allowed_statuses == (STATUS_SENT,)

    def test_in_progress_to_ready(self):
        plan = decide_destination_status_update(
            self._session(STATUS_IN_PROGRESS), "r1", STATUS_READY, NOW
        )
        assert plan.set_fields["status"] == STATUS_READY
        assert plan.set_fields["ready_at"] == NOW

    def test_ready_to_fulfilling(self):
        plan = decide_destination_status_update(
            self._session(STATUS_READY), "r1", STATUS_FULFILLING, NOW
        )
        assert plan.set_fields["status"] == STATUS_FULFILLING
        assert plan.set_fields["fulfilling_at"] == NOW

    def test_fulfilling_to_completed(self):
        plan = decide_destination_status_update(
            self._session(STATUS_FULFILLING), "r1", STATUS_COMPLETED, NOW
        )
        assert plan.set_fields["status"] == STATUS_COMPLETED
        assert plan.set_fields["completed_at"] == NOW

    # --- Idempotent (same status) ---
    def test_idempotent_same_status(self):
        plan = decide_destination_status_update(
            self._session(STATUS_IN_PROGRESS), "r1", STATUS_IN_PROGRESS, NOW
        )
        assert plan.set_fields is None
        assert plan.response["status"] == STATUS_IN_PROGRESS

    # --- Illegal Transitions ---
    def test_skip_step_raises_invalid(self):
        """Can't jump from SENT straight to READY."""
        with pytest.raises(InvalidStateError):
            decide_destination_status_update(
                self._session(STATUS_SENT), "r1", STATUS_READY, NOW
            )

    def test_backward_raises_invalid(self):
        """Can't go from READY back to IN_PROGRESS."""
        with pytest.raises(InvalidStateError):
            decide_destination_status_update(
                self._session(STATUS_READY), "r1", STATUS_IN_PROGRESS, NOW
            )

    def test_pending_cant_transition(self):
        """PENDING is not in the destination update state machine."""
        with pytest.raises(InvalidStateError):
            decide_destination_status_update(
                self._session(STATUS_PENDING), "r1", STATUS_IN_PROGRESS, NOW
            )

    def test_invalid_target_status(self):
        """Target like CANCELED is not allowed via destination update."""
        with pytest.raises(InvalidStateError):
            decide_destination_status_update(
                self._session(STATUS_SENT), "r1", STATUS_CANCELED, NOW
            )

    def test_wrong_destination_raises_not_found(self):
        with pytest.raises(NotFoundError):
            decide_destination_status_update(
                self._session(STATUS_SENT), "wrong", STATUS_IN_PROGRESS, NOW
            )


# =============================================================================
# decide_arrival_update (Progressive Arrival)
# =============================================================================
class TestDecideArrivalUpdate:
    def _session(self, status, **overrides):
        base = {"session_id": "s1", "status": status}
        base.update(overrides)
        return base

    def test_5_min_out_from_pending_fires_engine(self):
        plan = decide_arrival_update(self._session(STATUS_PENDING), "5_MIN_OUT", NOW)
        assert plan.set_fields["arrival_status"] == "5_MIN_OUT"
        assert plan.set_fields["status"] == STATUS_SENT
        assert plan.set_fields["sent_at"] == NOW
        assert plan.set_fields["vicinity"] is True

    def test_5_min_out_from_waiting_fires_engine(self):
        plan = decide_arrival_update(self._session(STATUS_WAITING), "5_MIN_OUT", NOW)
        assert plan.set_fields["status"] == STATUS_SENT

    def test_5_min_out_from_sent_no_status_change(self):
        """Already SENT, 5_MIN_OUT should not re-fire."""
        plan = decide_arrival_update(self._session(STATUS_SENT), "5_MIN_OUT", NOW)
        assert plan.set_fields["arrival_status"] == "5_MIN_OUT"
        assert "status" not in plan.set_fields  # No status override

    def test_parking_event(self):
        plan = decide_arrival_update(self._session(STATUS_SENT), "PARKING", NOW)
        assert plan.set_fields["arrival_status"] == "PARKING"
        assert plan.set_fields["last_arrival_update"] == NOW

    def test_at_door_event(self):
        plan = decide_arrival_update(self._session(STATUS_IN_PROGRESS), "AT_DOOR", NOW)
        assert plan.set_fields["arrival_status"] == "AT_DOOR"

    def test_exit_vicinity_auto_completes_fulfilling(self):
        plan = decide_arrival_update(self._session(STATUS_FULFILLING), "EXIT_VICINITY", NOW)
        assert plan.set_fields["status"] == STATUS_COMPLETED
        assert plan.set_fields["completed_at"] == NOW

    def test_exit_vicinity_does_not_complete_other_statuses(self):
        """Only FULFILLING should auto-complete on EXIT."""
        plan = decide_arrival_update(self._session(STATUS_IN_PROGRESS), "EXIT_VICINITY", NOW)
        assert "status" not in plan.set_fields or plan.set_fields.get("status") != STATUS_COMPLETED

    def test_unknown_event_type(self):
        plan = decide_arrival_update(self._session(STATUS_SENT), "UNKNOWN_EVENT", NOW)
        assert plan.response.get("error") == "Unknown event type"

    def test_none_session_raises_not_found(self):
        with pytest.raises(NotFoundError):
            decide_arrival_update(None, "5_MIN_OUT", NOW)

    def test_response_includes_current_status(self):
        plan = decide_arrival_update(self._session(STATUS_SENT), "AT_DOOR", NOW)
        assert plan.response["arrival_status"] == "AT_DOOR"
        assert plan.response["status"] == STATUS_SENT


# =============================================================================
# calculate_arrive_fee
# =============================================================================
class TestCalculateArriveFee:
    def test_standard_fee(self):
        fee = calculate_arrive_fee(4000)  # $40 order, 2% default
        assert fee["total_fee"] == 80  # 80 cents
        assert fee["restaurant_fee"] == 40
        assert fee["customer_fee"] == 40

    def test_odd_split(self):
        fee = calculate_arrive_fee(4100)  # $41 → 82c total → 41 + 41
        assert fee["total_fee"] == 82
        assert fee["restaurant_fee"] == 41
        assert fee["customer_fee"] == 41

    def test_zero_order(self):
        fee = calculate_arrive_fee(0)
        assert fee["total_fee"] == 0
        assert fee["restaurant_fee"] == 0
        assert fee["customer_fee"] == 0

    def test_custom_percent(self):
        fee = calculate_arrive_fee(10000, fee_percent=3.0)  # $100 × 3%
        assert fee["total_fee"] == 300
        assert fee["restaurant_fee"] + fee["customer_fee"] == 300

    def test_small_order(self):
        fee = calculate_arrive_fee(100)  # $1 order, 2% = 2 cents
        assert fee["total_fee"] == 2
        assert fee["restaurant_fee"] == 1
        assert fee["customer_fee"] == 1


# =============================================================================
# create_session_model
# =============================================================================
class TestCreateSessionModel:
    def test_basic_session(self):
        resources = [
            {"id": "item1", "qty": 2, "price_cents": 500, "work_units": 3},
            {"id": "item2", "qty": 1, "price_cents": 800, "work_units": 5},
        ]
        model = create_session_model(
            session_id="s1",
            destination_id="r1",
            resources=resources,
            customer_id="c1",
            now=NOW,
            expires_at=NOW + 3600,
        )

        assert model["session_id"] == "s1"
        assert model["destination_id"] == "r1"
        assert model["customer_id"] == "c1"
        assert model["status"] == STATUS_PENDING
        assert model["total_cents"] == 1800  # (500*2 + 800*1)
        assert model["work_units_total"] == 11  # (3*2 + 5*1)
        assert model["tip_cents"] == 0
        assert model["receipt_mode"] == RECEIPT_SOFT  # default
        assert model["payment_mode"] == PAYMENT_MODE_AT_RESTAURANT  # default
        assert model["arrive_fee_cents"] > 0

    def test_fee_calculation_integrated(self):
        """Verify that arrive_fee_cents matches calculate_arrive_fee output."""
        resources = [{"id": "x", "qty": 1, "price_cents": 5000, "work_units": 1}]
        model = create_session_model("s3", "r1", resources, "c1", NOW, NOW + 3600)
        expected_fee = calculate_arrive_fee(5000)
        assert model["arrive_fee_cents"] == expected_fee["total_fee"]

    def test_legacy_prep_units_key(self):
        """Should fallback to 'prep_units' if 'work_units' is missing."""
        resources = [{"id": "x", "qty": 2, "price_cents": 100, "prep_units": 4}]
        model = create_session_model("s4", "r1", resources, "c1", NOW, NOW + 3600)
        assert model["work_units_total"] == 8  # 4 * 2

    def test_ttl_passed_through(self):
        """Verify ttl is included in the model."""
        ttl_val = NOW + 999
        model = create_session_model(
            "s5", "r1", [{"id": "x", "qty": 1}], "c1", NOW, NOW + 3600, ttl=ttl_val
        )
        assert model["ttl"] == ttl_val


# =============================================================================
# validate_resources_payload
# =============================================================================
class TestValidateResourcesPayload:
    def test_valid_payload(self):
        validate_resources_payload([{"id": "item1", "qty": 2}])  # No exception

    def test_empty_list_raises(self):
        with pytest.raises(ValidationError):
            validate_resources_payload([])

    def test_none_raises(self):
        with pytest.raises(ValidationError):
            validate_resources_payload(None)

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            validate_resources_payload([{"qty": 1}])

    def test_missing_qty_raises(self):
        with pytest.raises(ValidationError):
            validate_resources_payload([{"id": "a"}])

    def test_zero_qty_raises(self):
        with pytest.raises(ValidationError):
            validate_resources_payload([{"id": "a", "qty": 0}])

    def test_negative_qty_raises(self):
        with pytest.raises(ValidationError):
            validate_resources_payload([{"id": "a", "qty": -1}])

    def test_legacy_menu_item_id_works(self):
        """Old 'menu_item_id' key should still be accepted."""
        validate_resources_payload([{"menu_item_id": "burger", "qty": 1}])


# =============================================================================
# validate_destination_owns_session
# =============================================================================
class TestValidateDestinationOwnsSession:
    def test_matching(self):
        assert validate_destination_owns_session({"destination_id": "r1"}, "r1") is True

    def test_non_matching(self):
        assert validate_destination_owns_session({"destination_id": "r1"}, "r2") is False

    def test_legacy_key(self):
        assert validate_destination_owns_session({"restaurant_id": "r1"}, "r1") is True


# =============================================================================
# ensure_not_expired
# =============================================================================
class TestEnsureNotExpired:
    def test_not_expired(self):
        ensure_not_expired({"expires_at": NOW + 100}, NOW)  # No exception

    def test_expired_raises(self):
        with pytest.raises(ExpiredError):
            ensure_not_expired({"expires_at": NOW - 1}, NOW)

    def test_exactly_expired_raises(self):
        # now > expires_at, so when now == expires_at + 1
        with pytest.raises(ExpiredError):
            ensure_not_expired({"expires_at": NOW}, NOW + 1)
