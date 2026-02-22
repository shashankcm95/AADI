"""Amazon Location bridge helpers for the orders service."""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import os
import math

import boto3


TRACKER_NAME = os.environ.get('LOCATION_TRACKER_NAME', '').strip()
_location_client = None


def _get_location_client():
    global _location_client
    if _location_client is not None:
        return _location_client
    try:
        _location_client = boto3.client('location')
    except Exception:
        _location_client = False
    return _location_client if _location_client else None


def tracker_enabled() -> bool:
    return bool(TRACKER_NAME) and _get_location_client() is not None


def coerce_finite_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def coerce_epoch_seconds(value: Any, fallback_now_seconds: int) -> int:
    if value is None:
        return int(fallback_now_seconds)

    try:
        raw = float(value)
    except (TypeError, ValueError):
        return int(fallback_now_seconds)

    if not math.isfinite(raw) or raw <= 0:
        return int(fallback_now_seconds)

    # Accept either seconds or milliseconds.
    if raw > 10_000_000_000:
        raw = raw / 1000.0
    return int(raw)


def publish_device_position(
    *,
    device_id: str,
    latitude: float,
    longitude: float,
    sample_time_seconds: int,
    position_properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not TRACKER_NAME:
        return {"published": False, "tracker_enabled": False, "reason": "tracker_not_configured"}

    client = _get_location_client()
    if client is None:
        return {"published": False, "tracker_enabled": False, "reason": "location_client_unavailable"}

    if not device_id:
        return {"published": False, "tracker_enabled": True, "reason": "missing_device_id"}

    update: Dict[str, Any] = {
        'DeviceId': str(device_id),
        'SampleTime': datetime.fromtimestamp(int(sample_time_seconds), tz=timezone.utc),
        'Position': [float(longitude), float(latitude)],
    }
    if position_properties:
        update['PositionProperties'] = {
            str(k): str(v)
            for k, v in position_properties.items()
            if v is not None
        }

    try:
        response = client.batch_update_device_position(
            TrackerName=TRACKER_NAME,
            Updates=[update],
        )
    except Exception as exc:
        return {
            "published": False,
            "tracker_enabled": True,
            "reason": "batch_update_failed",
            "error": str(exc),
        }

    errors = response.get('Errors') or []
    if errors:
        detail = errors[0]
        return {
            "published": False,
            "tracker_enabled": True,
            "reason": "batch_update_rejected",
            "error": str(detail.get('Error', {}).get('Message') or detail),
        }

    return {"published": True, "tracker_enabled": True}
