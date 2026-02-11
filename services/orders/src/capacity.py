"""
Capacity Gating — Domain-Agnostic Core

Manages time-windowed capacity slots for any destination.
The core operates on abstract concepts:
  - destination_id: the entity with limited capacity (restaurant, venue, counter)
  - window_start:   epoch boundary for the capacity window
  - max_concurrent:  slots available per window

Dining-specific helpers layer on top without polluting the core.

DynamoDB CapacityTable schema:
  PK: restaurant_id (S)  — kept as-is for backward compat; semantically = destination_id
  SK: window_start (N)   — epoch seconds, floored to window boundary
  Attrs: current_count (N), ttl (N)
"""

import time
from typing import Any, Dict, Optional
from boto3.dynamodb.conditions import Attr


# =============================================================================
# Core — Domain-Agnostic Capacity Primitives
# =============================================================================

# Defaults when a destination has no explicit config
DEFAULT_MAX_CONCURRENT = 10
DEFAULT_WINDOW_SECONDS = 300  # 5 minutes
DEFAULT_TTL_PADDING = 3600    # Keep rows 1 hour past window end


def get_window_start(now: int, window_seconds: int) -> int:
    """
    Floor `now` to the nearest window boundary.

    >>> get_window_start(1007, 300)
    900
    >>> get_window_start(900, 300)
    900
    """
    return (now // window_seconds) * window_seconds


def try_reserve_slot(
    table,
    destination_id: str,
    window_start: int,
    max_concurrent: int,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ttl_padding: int = DEFAULT_TTL_PADDING,
) -> bool:
    """
    Atomically reserve one capacity slot.

    Uses DynamoDB atomic counter with a condition to enforce the cap:
      ADD current_count :1  WHERE current_count < :max (or item doesn't exist)

    Returns True if slot was reserved, False if at capacity.
    Thread-safe and idempotent per unique (destination_id, window_start) pair.
    """
    ttl = window_start + window_seconds + ttl_padding

    try:
        table.update_item(
            Key={
                "restaurant_id": destination_id,  # PK name kept for DDB compat
                "window_start": window_start,
            },
            UpdateExpression="SET current_count = if_not_exists(current_count, :zero) + :one, "
                             "ttl = :ttl",
            ConditionExpression=(
                Attr("current_count").not_exists() |
                Attr("current_count").lt(max_concurrent)
            ),
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":ttl": ttl,
            },
        )
        return True

    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False


def release_slot(
    table,
    destination_id: str,
    window_start: int,
) -> None:
    """
    Release one capacity slot (on cancel/complete).

    Decrements current_count with a floor at 0 to prevent negative counts.
    No-ops gracefully if the row doesn't exist (e.g., TTL already expired).
    """
    try:
        table.update_item(
            Key={
                "restaurant_id": destination_id,
                "window_start": window_start,
            },
            UpdateExpression="SET current_count = current_count - :one",
            ConditionExpression=Attr("current_count").gt(0),
            ExpressionAttributeValues={":one": 1},
        )
    except Exception as e:
        # Row expired or count already 0 — safe to ignore but log for debugging
        print(f"WARN release_slot({destination_id}, {window_start}): {e}")


# =============================================================================
# Config — Read Destination Capacity Settings
# =============================================================================

def get_capacity_config(
    config_table,
    destination_id: str,
) -> Dict[str, Any]:
    """
    Read capacity configuration for a destination.

    Returns dict with:
      - max_concurrent_orders: int
      - capacity_window_seconds: int

    Falls back to sensible defaults if no config exists.
    """
    if not config_table:
        return {
            "max_concurrent_orders": DEFAULT_MAX_CONCURRENT,
            "capacity_window_seconds": DEFAULT_WINDOW_SECONDS,
        }

    try:
        resp = config_table.get_item(Key={"restaurant_id": destination_id})
        item = resp.get("Item", {})
        return {
            "max_concurrent_orders": int(
                item.get("max_concurrent_orders", DEFAULT_MAX_CONCURRENT)
            ),
            "capacity_window_seconds": int(
                item.get("capacity_window_seconds", DEFAULT_WINDOW_SECONDS)
            ),
        }
    except Exception:
        return {
            "max_concurrent_orders": DEFAULT_MAX_CONCURRENT,
            "capacity_window_seconds": DEFAULT_WINDOW_SECONDS,
        }


# =============================================================================
# Dining Extension — Restaurant-Specific Helpers
# =============================================================================

def check_and_reserve_for_arrival(
    capacity_table,
    config_table,
    destination_id: str,
    now: int,
) -> Dict[str, Any]:
    """
    High-level dining flow: check capacity and reserve a slot on arrival.

    Used by the vicinity handler when a 5_MIN_OUT event fires.

    Returns:
        {
            "reserved": bool,
            "window_start": int,
            "window_seconds": int,
            "max_concurrent": int,
        }
    """
    config = get_capacity_config(config_table, destination_id)
    max_concurrent = config["max_concurrent_orders"]
    window_seconds = config["capacity_window_seconds"]
    window_start = get_window_start(now, window_seconds)

    reserved = try_reserve_slot(
        table=capacity_table,
        destination_id=destination_id,
        window_start=window_start,
        max_concurrent=max_concurrent,
        window_seconds=window_seconds,
    )

    return {
        "reserved": reserved,
        "window_start": window_start,
        "window_seconds": window_seconds,
        "max_concurrent": max_concurrent,
    }
