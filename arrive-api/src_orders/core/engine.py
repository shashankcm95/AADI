from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .models import (
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

from .errors import ExpiredError, InvalidStateError, NotFoundError


@dataclass(frozen=True)
class UpdatePlan:
    """
    Describes how storage should update an order.
    """
    # If set, storage should apply a conditional status check before updating
    condition_allowed_statuses: Optional[Tuple[str, ...]] = None

    # Dynamo-style fields
    set_fields: Optional[Dict[str, Any]] = None
    remove_fields: Optional[Tuple[str, ...]] = None

    # Logical response to return to caller
    response: Optional[Dict[str, Any]] = None


def ensure_not_expired(order: Dict[str, Any], now: int) -> None:
    if now > int(order.get("expires_at", 0)):
        raise ExpiredError()


def decide_vicinity_update(
    order: Dict[str, Any],
    vicinity: bool,
    now: int,
    window_seconds: int,
    max_units: int,
    window_start: int,
    reserved_capacity: bool,
) -> UpdatePlan:
    """
    Pure decision logic for vicinity updates.
    - order is a dict (storage format)
    - reserved_capacity is the result of the storage-level atomic reservation attempt
    """
    status = order.get("status")

    # only act when client says vicinity true
    if vicinity is not True:
        return UpdatePlan(
            response={"order_id": order["order_id"], "status": status}
        )

    # Allow both PENDING and WAITING to dispatch when capacity becomes available
    if status not in (STATUS_PENDING, STATUS_WAITING):
        return UpdatePlan(
            response={"order_id": order["order_id"], "status": status}
        )

    if reserved_capacity:
        return UpdatePlan(
            condition_allowed_statuses=(STATUS_PENDING, STATUS_WAITING),
            set_fields={
                "status": STATUS_SENT,
                "vicinity": True,
                "sent_at": now,
                "capacity_window_start": window_start,
                "received_by_restaurant": True,
                "received_at": now,
                "receipt_mode": RECEIPT_SOFT,
            },
            remove_fields=("waiting_since", "suggested_start_at"),
            response={"order_id": order["order_id"], "status": STATUS_SENT},
        )

    # blocked
    suggested_start_at = window_start + window_seconds
    return UpdatePlan(
        set_fields={
            "status": STATUS_WAITING,
            "vicinity": True,
            "waiting_since": now,
            "suggested_start_at": suggested_start_at,
        },
        response={
            "order_id": order["order_id"],
            "status": STATUS_WAITING,
            "suggested_start_at": suggested_start_at
        },
    )


def decide_ack_upgrade(order: Dict[str, Any], restaurant_id: str, now: int) -> UpdatePlan:
    if not order or order.get("restaurant_id") != restaurant_id:
        raise NotFoundError()

    if order.get("status") != STATUS_SENT:
        raise InvalidStateError()

    if order.get("receipt_mode") == RECEIPT_HARD:
        return UpdatePlan(
            response={"order_id": order["order_id"], "receipt_mode": RECEIPT_HARD}
        )

    return UpdatePlan(
        condition_allowed_statuses=(STATUS_SENT,),
        set_fields={
            "receipt_mode": RECEIPT_HARD,
            "received_at": now,
        },
        response={"order_id": order["order_id"], "receipt_mode": RECEIPT_HARD, "received_at": now},
    )

def decide_cancel(order: Dict[str, Any], now: int) -> UpdatePlan:
    if not order:
        raise NotFoundError()

    status = order.get("status")

    if status not in (STATUS_PENDING, STATUS_WAITING):
        # Not cancelable once sent/in-progress/etc.
        raise InvalidStateError()

    return UpdatePlan(
        condition_allowed_statuses=(STATUS_PENDING, STATUS_WAITING),
        set_fields={
            "status": STATUS_CANCELED,
            "canceled_at": now,
        },
        remove_fields=("waiting_since", "suggested_start_at"),
        response={"order_id": order["order_id"], "status": STATUS_CANCELED, "canceled_at": now},
    )

def decide_restaurant_status_update(
    order: Dict[str, Any],
    restaurant_id: str,
    new_status: str,
    now: int,
) -> UpdatePlan:
    if not order or order.get("restaurant_id") != restaurant_id:
        raise NotFoundError()

    current = order.get("status")

    allowed_targets = (STATUS_IN_PROGRESS, STATUS_READY, STATUS_COMPLETED)
    if new_status not in allowed_targets:
        raise InvalidStateError()

    # Idempotent
    if current == new_status:
        return UpdatePlan(
            response={"order_id": order["order_id"], "status": current}
        )

    # Legal transitions
    allowed_next = {
        STATUS_SENT: (STATUS_IN_PROGRESS,),
        STATUS_IN_PROGRESS: (STATUS_READY,),
        STATUS_READY: (STATUS_COMPLETED,),
    }

    if current not in allowed_next or new_status not in allowed_next[current]:
        raise InvalidStateError()

    set_fields: Dict[str, Any] = {
        "status": new_status,
        "updated_at": now,
    }

    # Useful timestamps per transition
    if new_status == STATUS_IN_PROGRESS:
        set_fields["started_at"] = now
    elif new_status == STATUS_READY:
        set_fields["ready_at"] = now
    elif new_status == STATUS_COMPLETED:
        set_fields["completed_at"] = now

    return UpdatePlan(
        condition_allowed_statuses=(current,),
        set_fields=set_fields,
        response={"order_id": order["order_id"], "status": new_status},
    )
