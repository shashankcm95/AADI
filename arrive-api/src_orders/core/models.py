from dataclasses import dataclass
from typing import Any, Dict, List, Optional

STATUS_PENDING = "PENDING_NOT_SENT"
STATUS_SENT = "SENT_TO_RESTAURANT"
STATUS_WAITING = "WAITING_FOR_CAPACITY"
STATUS_EXPIRED = "EXPIRED"

RECEIPT_SOFT = "SOFT"
RECEIPT_HARD = "HARD"

STATUS_CANCELED = "CANCELED"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_READY = "READY"
STATUS_COMPLETED = "COMPLETED"

@dataclass(frozen=True)
class OrderItem:
    id: str
    qty: int
    name: Optional[str]
    price_cents: int
    prep_units: int


@dataclass(frozen=True)
class Order:
    order_id: str
    restaurant_id: str
    status: str
    created_at: int
    expires_at: int
    customer_name: str
    items: List[OrderItem]
    total_cents: int
    prep_units_total: int
    vicinity: bool

    # Optional fields (may not exist yet)
    sent_at: Optional[int] = None
    capacity_window_start: Optional[int] = None
    receipt_mode: Optional[str] = None
    received_by_restaurant: Optional[bool] = None
    received_at: Optional[int] = None
    waiting_since: Optional[int] = None
    suggested_start_at: Optional[int] = None

    @staticmethod
    def from_ddb(item: Dict[str, Any]) -> "Order":
        items = []
        for it in item.get("items", []):
            items.append(
                OrderItem(
                    id=it["id"],
                    qty=int(it.get("qty", 1)),
                    name=it.get("name"),
                    price_cents=int(it.get("price_cents", 0)),
                    prep_units=int(it.get("prep_units", 1)),
                )
            )
        return Order(
            order_id=item["order_id"],
            restaurant_id=item["restaurant_id"],
            status=item["status"],
            created_at=int(item["created_at"]),
            expires_at=int(item["expires_at"]),
            customer_name=item.get("customer_name", "Guest"),
            items=items,
            total_cents=int(item.get("total_cents", 0)),
            prep_units_total=int(item.get("prep_units_total", 0)),
            vicinity=bool(item.get("vicinity", False)),
            sent_at=_maybe_int(item.get("sent_at")),
            capacity_window_start=_maybe_int(item.get("capacity_window_start")),
            receipt_mode=item.get("receipt_mode"),
            received_by_restaurant=item.get("received_by_restaurant"),
            received_at=_maybe_int(item.get("received_at")),
            waiting_since=_maybe_int(item.get("waiting_since")),
            suggested_start_at=_maybe_int(item.get("suggested_start_at")),
        )


def _maybe_int(v) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None

