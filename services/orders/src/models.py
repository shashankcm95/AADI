from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import StrEnum


class OrderStatus(StrEnum):
    """Session lifecycle statuses."""
    PENDING_NOT_SENT = "PENDING_NOT_SENT"
    SENT_TO_DESTINATION = "SENT_TO_DESTINATION"
    WAITING_FOR_CAPACITY = "WAITING_FOR_CAPACITY"
    EXPIRED = "EXPIRED"
    CANCELED = "CANCELED"
    IN_PROGRESS = "IN_PROGRESS"
    READY = "READY"
    FULFILLING = "FULFILLING"
    COMPLETED = "COMPLETED"


class ReceiptMode(StrEnum):
    SOFT = "SOFT"
    HARD = "HARD"


class ArrivalStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    FIVE_MIN_OUT = "5_MIN_OUT"
    PARKING = "PARKING"
    AT_DOOR = "AT_DOOR"
    EXIT_VICINITY = "EXIT_VICINITY"



class PaymentMode(StrEnum):
    AT_RESTAURANT = "PAY_AT_RESTAURANT"





# Backward-compatible aliases — existing code uses these names
STATUS_PENDING = OrderStatus.PENDING_NOT_SENT
STATUS_SENT = OrderStatus.SENT_TO_DESTINATION
STATUS_WAITING = OrderStatus.WAITING_FOR_CAPACITY
STATUS_EXPIRED = OrderStatus.EXPIRED
STATUS_CANCELED = OrderStatus.CANCELED
STATUS_IN_PROGRESS = OrderStatus.IN_PROGRESS
STATUS_READY = OrderStatus.READY
STATUS_FULFILLING = OrderStatus.FULFILLING
STATUS_COMPLETED = OrderStatus.COMPLETED

RECEIPT_SOFT = ReceiptMode.SOFT
RECEIPT_HARD = ReceiptMode.HARD

ARRIVAL_UNKNOWN = ArrivalStatus.UNKNOWN
ARRIVAL_5_MIN = ArrivalStatus.FIVE_MIN_OUT


PAYMENT_MODE_AT_RESTAURANT = PaymentMode.AT_RESTAURANT



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
    
    # Payment mode (current scope: pay at restaurant)
    payment_mode: Optional[str] = None
    pos_payment_ref: Optional[str] = None  # Reference from POS system
    
    # Arrive Fee
    arrive_fee_cents: int = 0
    
    # TTL
    ttl: Optional[int] = None

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
            ttl=_maybe_int(item.get("ttl")),
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
