from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List

from models import (
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_WAITING,
    STATUS_CANCELED,
    STATUS_IN_PROGRESS,
    STATUS_READY,
    STATUS_FULFILLING,
    STATUS_COMPLETED,
    RECEIPT_SOFT,
    RECEIPT_HARD,
    PAYMENT_MODE_AT_RESTAURANT
)

from errors import ExpiredError, InvalidStateError, NotFoundError

# Module-level state machine: maps current status → allowed next statuses
ALLOWED_TRANSITIONS = {
    STATUS_SENT: (STATUS_IN_PROGRESS,),
    STATUS_IN_PROGRESS: (STATUS_READY,),
    STATUS_READY: (STATUS_FULFILLING,),
    STATUS_FULFILLING: (STATUS_COMPLETED,),
}

@dataclass(frozen=True)
class UpdatePlan:
    """
    Describes how storage should update a session.
    """
    # If set, storage should apply a conditional status check before updating
    condition_allowed_statuses: Optional[Tuple[str, ...]] = None

    # Dynamo-style fields
    set_fields: Optional[Dict[str, Any]] = None
    remove_fields: Optional[Tuple[str, ...]] = None

    # Logical response to return to caller
    response: Optional[Dict[str, Any]] = None


def ensure_not_expired(session: Dict[str, Any], now: int) -> None:
    if now > int(session.get("expires_at", 0)):
        raise ExpiredError()


def decide_vicinity_update(
    session: Dict[str, Any],
    vicinity: bool,
    now: int,
    window_seconds: int,
    window_start: int,
    reserved_capacity: bool,
) -> UpdatePlan:
    """
    Pure decision logic for vicinity updates.
    """
    status = session.get("status")
    session_id = session.get("session_id", session.get("order_id"))

    # only act when client says vicinity true
    if vicinity is not True:
        return UpdatePlan(
            response={"session_id": session_id, "status": status}
        )

    # Allow both PENDING and WAITING to dispatch when capacity becomes available
    if status not in (STATUS_PENDING, STATUS_WAITING):
        return UpdatePlan(
            response={"session_id": session_id, "status": status}
        )

    if reserved_capacity:
        return UpdatePlan(
            condition_allowed_statuses=(STATUS_PENDING, STATUS_WAITING),
            set_fields={
                "status": STATUS_SENT,
                "vicinity": True,
                "sent_at": now,
                "capacity_window_start": window_start,
                "received_by_destination": True,
                "received_at": now,
                "receipt_mode": RECEIPT_SOFT,
            },
            remove_fields=("waiting_since", "suggested_start_at"),
            response={"session_id": session_id, "status": STATUS_SENT},
        )

    # blocked
    suggested_start_at = window_start + window_seconds
    return UpdatePlan(
        condition_allowed_statuses=(STATUS_PENDING, STATUS_WAITING),
        set_fields={
            "status": STATUS_WAITING,
            "vicinity": True,
            "waiting_since": now,
            "suggested_start_at": suggested_start_at,
        },
        response={
            "session_id": session_id,
            "status": STATUS_WAITING,
            "suggested_start_at": suggested_start_at
        },
    )


def decide_ack_upgrade(session: Dict[str, Any], destination_id: str, now: int) -> UpdatePlan:
    # Support both old and new keys for compatibility
    curr_dest_id = session.get("destination_id", session.get("restaurant_id"))
    session_id = session.get("session_id", session.get("order_id"))
    
    if not session or curr_dest_id != destination_id:
        raise NotFoundError()

    if session.get("status") != STATUS_SENT:
        raise InvalidStateError()

    if session.get("receipt_mode") == RECEIPT_HARD:
        return UpdatePlan(
            response={"session_id": session_id, "receipt_mode": RECEIPT_HARD}
        )

    return UpdatePlan(
        condition_allowed_statuses=(STATUS_SENT,),
        set_fields={
            "receipt_mode": RECEIPT_HARD,
            "received_at": now,
        },
        response={"session_id": session_id, "receipt_mode": RECEIPT_HARD, "received_at": now},
    )

def decide_cancel(session: Dict[str, Any], now: int) -> UpdatePlan:
    if not session:
        raise NotFoundError()
        
    session_id = session.get("session_id", session.get("order_id"))
    status = session.get("status")

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
        response={"session_id": session_id, "status": STATUS_CANCELED, "canceled_at": now},
    )

def decide_destination_status_update(
    session: Dict[str, Any],
    destination_id: str,
    new_status: str,
    now: int,
) -> UpdatePlan:
    curr_dest_id = session.get("destination_id", session.get("restaurant_id"))
    session_id = session.get("session_id", session.get("order_id"))

    if not session or curr_dest_id != destination_id:
        raise NotFoundError()

    current = session.get("status")

    allowed_targets = (STATUS_IN_PROGRESS, STATUS_READY, STATUS_FULFILLING, STATUS_COMPLETED)
    if new_status not in allowed_targets:
        raise InvalidStateError()

    # Idempotent
    if current == new_status:
        return UpdatePlan(
            response={"session_id": session_id, "status": current}
        )

    if current not in ALLOWED_TRANSITIONS or new_status not in ALLOWED_TRANSITIONS[current]:
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
    elif new_status == STATUS_FULFILLING:
        set_fields["fulfilling_at"] = now # Was serving_at
    elif new_status == STATUS_COMPLETED:
        set_fields["completed_at"] = now

    return UpdatePlan(
        condition_allowed_statuses=(current,),
        set_fields=set_fields,
        response={"session_id": session_id, "status": new_status},
    )

def decide_arrival_update(
    session: Dict[str, Any],
    event_type: str,
    now: int,
    allow_dispatch_transition: bool = True,
) -> UpdatePlan:
    """
    Core logic for Progressive Arrival.
    """
    if not session:
        raise NotFoundError()
        
    session_id = session.get("session_id", session.get("order_id"))
    
    # 1. Determine new Arrival Status
    mapping = {
        "5_MIN_OUT": "5_MIN_OUT",
        "PARKING": "PARKING",
        "AT_DOOR": "AT_DOOR",
        "EXIT_VICINITY": "EXIT_VICINITY"
    }
    new_arrival = mapping.get(event_type)
    if not new_arrival:
        return UpdatePlan(response={"error": "Unknown event type"})

    set_fields = {
        "arrival_status": new_arrival,
        "last_arrival_update": now
    }

    # 2. Side Effects on Session Status (The "Conductor" Logic)
    # If 5_MIN_OUT, PARKING, or AT_DOOR -> Ensure Session is SENT (Fire the Engine)
    # Rationale: If they are parking or at the door, they are certainly ready to be processed.
    if new_arrival in ("5_MIN_OUT", "PARKING", "AT_DOOR"):
        current_status = session.get("status")
        if allow_dispatch_transition and current_status in (STATUS_PENDING, STATUS_WAITING):
            set_fields["status"] = STATUS_SENT  # Force send
            set_fields["sent_at"] = now
            set_fields["vicinity"] = True 
            
    # 3. Auto-Close on EXIT
    condition_statuses = None
    if new_arrival == "EXIT_VICINITY":
        current_status = session.get("status")
        # Only close if we are actually fulfilling
        if current_status == STATUS_FULFILLING:
            set_fields["status"] = STATUS_COMPLETED
            set_fields["completed_at"] = now
            # Guard against concurrent status transitions
            condition_statuses = (STATUS_FULFILLING,)

    return UpdatePlan(
        condition_allowed_statuses=condition_statuses,
        set_fields=set_fields,
        response={"session_id": session_id, "arrival_status": new_arrival, "status": set_fields.get("status", session.get("status"))}
    )




# =============================================================================
# Validation Helpers
# =============================================================================

from errors import ValidationError


MAX_ITEM_QTY = 99


def validate_resources_payload(resources: List[Dict[str, Any]]) -> None:
    """
    Validates resource request payload.
    """
    if not resources or len(resources) == 0:
        raise ValidationError("Session must have at least one resource")

    for r in resources:
        # Check for new key OR legacy key
        if "id" not in r and "menu_item_id" not in r:
            raise ValidationError("Each item must have a valid id")

        if "qty" not in r:
            raise ValidationError("Each item must have qty")
        if r.get("qty", 0) < 1:
            raise ValidationError("Quantity must be at least 1")
        if r.get("qty", 0) > MAX_ITEM_QTY:
            raise ValidationError(f"Item quantity must be at most {MAX_ITEM_QTY}")


def validate_destination_owns_session(session: Dict[str, Any], destination_id: str) -> bool:
    """
    Validates that the destination owns the session.
    """
    curr = session.get("destination_id", session.get("restaurant_id"))
    return curr == destination_id





def calculate_arrive_fee(order_total_cents: int, fee_percent: float = 2.0) -> Dict[str, Any]:
    """
    Calculate the Arrive platform fee, split between restaurant and customer.
    """
    total_fee = round(order_total_cents * fee_percent / 100)
    restaurant_share = total_fee // 2
    customer_share = total_fee - restaurant_share
    return {
        "total_fee": total_fee,
        "restaurant_fee": restaurant_share,
        "customer_fee": customer_share,
    }


def create_session_model(
    session_id: str,
    destination_id: str,
    resources: List[Dict[str, Any]],
    customer_id: str,
    now: int,
    expires_at: int,
    customer_name: str = "Guest",
    ttl: Optional[int] = None,
    receipt_mode: str = RECEIPT_SOFT,
    payment_mode: str = PAYMENT_MODE_AT_RESTAURANT,
) -> Dict[str, Any]:
    """
    Creates a new session model dictionary.
    """
    # Calculate totals, handling both new 'work_units' and old 'prep_units'
    total_cents = 0
    work_units = 0
    
    for r in resources:
        qty = r.get("qty", 1)
        total_cents += r.get("price_cents", 0) * qty
        work_units += r.get("work_units", r.get("prep_units", 1)) * qty

    # Calculate Arrive platform fee (split between restaurant and customer)
    fee = calculate_arrive_fee(total_cents)

    return {
        "session_id": session_id,
        "destination_id": destination_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "items": resources,
        "status": STATUS_PENDING,
        "arrival_status": None,
        "receipt_mode": receipt_mode,
        "payment_mode": payment_mode,
        "created_at": now,
        "expires_at": expires_at,
        "total_cents": total_cents,
        "work_units_total": work_units,
        "arrive_fee_cents": fee["total_fee"],
        "tip_cents": 0,
        "ttl": ttl,
    }
