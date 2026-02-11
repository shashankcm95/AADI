from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Session Statuses (Generalized)
STATUS_PENDING = "PENDING_NOT_SENT"
STATUS_SENT = "SENT_TO_DESTINATION"     # Was SENT_TO_RESTAURANT
STATUS_WAITING = "WAITING_FOR_CAPACITY"
STATUS_EXPIRED = "EXPIRED"

RECEIPT_SOFT = "SOFT"
RECEIPT_HARD = "HARD"

STATUS_CANCELED = "CANCELED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_READY = "READY"
STATUS_FULFILLING = "FULFILLING"        # Was SERVING
STATUS_COMPLETED = "COMPLETED"

# Arrival Micro-States
ARRIVAL_UNKNOWN = "UNKNOWN"
ARRIVAL_5_MIN = "5_MIN_OUT"
ARRIVAL_PARKING = "PARKING"
ARRIVAL_DOOR = "AT_DOOR"
ARRIVAL_EXIT = "EXIT_VICINITY"

# Payment Modes (Dual Flow)
PAYMENT_MODE_PREPAID = "PREPAID"
PAYMENT_MODE_AT_RESTAURANT = "PAY_AT_RESTAURANT"

# Fulfillment Stages (Generalized KDS Lanes)
STAGE_INIT = "STAGE_INIT"       # Was LANE_PREP
STAGE_PROCESS = "STAGE_PROCESS" # Was LANE_COOK
STAGE_FINALIZE = "STAGE_FINALIZE" # Was LANE_PLATE
STAGE_HANDOFF = "STAGE_HANDOFF"   # Was LANE_SERVE

@dataclass(frozen=True)
class Resource:
    """Represents a generalized item being requested (food, ticket, service)."""
    id: str             # Was menu_item_id
    qty: int
    name: Optional[str]
    price_cents: int
    work_units: int     # Was prep_units

@dataclass(frozen=True)
class Session:
    """
    Represents a generalized engagement session.
    (Formerly 'Order')
    """
    session_id: str         # Was order_id
    destination_id: str     # Was restaurant_id
    status: str
    
    # Timestamps
    created_at: int
    expires_at: int
    
    # Customer Info
    customer_id: str        # Keeping generic ID
    customer_name: str
    
    # Content
    resources: List[Resource] # Was items
    total_cents: int
    work_units_total: int     # Was prep_units_total
    
    # Geofencing State
    vicinity: bool
    arrival_status: Optional[str] = None
    
    # Scheduling & Capacity
    sent_at: Optional[int] = None
    capacity_window_start: Optional[int] = None
    waiting_since: Optional[int] = None
    suggested_start_at: Optional[int] = None
    
    # Acknowledgement
    receipt_mode: Optional[str] = None
    received_by_destination: Optional[bool] = None # Was received_by_restaurant
    received_at: Optional[int] = None
    
    # Payment Mode (dual flow)
    payment_mode: Optional[str] = None  # PREPAID or PAY_AT_RESTAURANT
    pos_payment_ref: Optional[str] = None  # Reference from POS system
    
    # Arrive Fee
    arrive_fee_cents: int = 0

    @staticmethod
    def from_ddb(item: Dict[str, Any]) -> "Session":
        resources = []
        for it in item.get("items", []):
            resources.append(
                Resource(
                    id=it.get("id", it.get("menu_item_id")), # Handle legacy keys
                    qty=int(it.get("qty", 1)),
                    name=it.get("name"),
                    price_cents=int(it.get("price_cents", 0)),
                    work_units=int(it.get("work_units", it.get("prep_units", 1))),
                )
            )
        return Session(
            session_id=item.get("session_id", item.get("order_id")), # Handle legacy keys
            destination_id=item.get("destination_id", item.get("restaurant_id")),
            status=item["status"],
            created_at=int(item["created_at"]),
            expires_at=int(item["expires_at"]),
            customer_id=item.get("customer_id", "guest"),
            customer_name=item.get("customer_name", "Guest"),
            resources=resources,
            total_cents=int(item.get("total_cents", 0)),
            work_units_total=int(item.get("work_units_total", item.get("prep_units_total", 0))),
            vicinity=bool(item.get("vicinity", False)),
            sent_at=_maybe_int(item.get("sent_at")),
            capacity_window_start=_maybe_int(item.get("capacity_window_start")),
            receipt_mode=item.get("receipt_mode"),
            received_by_destination=item.get("received_by_destination", item.get("received_by_restaurant")),
            received_at=_maybe_int(item.get("received_at")),
            waiting_since=_maybe_int(item.get("waiting_since")),
            suggested_start_at=_maybe_int(item.get("suggested_start_at")),
            payment_mode=item.get("payment_mode"),
            pos_payment_ref=item.get("pos_payment_ref"),
            arrive_fee_cents=int(item.get("arrive_fee_cents", 0)),
            arrival_status=item.get("arrival_status"),
        )

def _maybe_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None
