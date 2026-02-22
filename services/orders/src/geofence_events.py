"""EventBridge consumer for Amazon Location geofence ENTER events."""
import json
import os
import time
from typing import Any, Dict, Optional, Tuple

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

import db
from handlers.customer import update_vicinity
from logger import get_logger
from models import STATUS_PENDING, STATUS_WAITING

log = get_logger("orders.geofence_events", service="orders")

_ACTIVE_STATUSES = {
    str(STATUS_PENDING),
    str(STATUS_WAITING),
    "SENT_TO_DESTINATION",
    "IN_PROGRESS",
    "READY",
}
_VALID_EVENTS = {"5_MIN_OUT", "PARKING", "AT_DOOR"}


def _to_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _claim_event(event_id: str) -> bool:
    table = db.geofence_events_table
    if not table:
        return True

    now = int(time.time())
    try:
        table.put_item(
            Item={
                'event_id': event_id,
                'created_at': now,
                'ttl': now + (7 * 24 * 60 * 60),
            },
            ConditionExpression='attribute_not_exists(event_id)',
        )
        return True
    except ClientError as exc:
        code = exc.response.get('Error', {}).get('Code')
        if code == 'ConditionalCheckFailedException':
            return False
        raise


def _read_detail(detail: Dict[str, Any], canonical: str) -> Optional[Any]:
    if canonical in detail:
        return detail.get(canonical)
    lower = canonical[0].lower() + canonical[1:]
    if lower in detail:
        return detail.get(lower)
    snake = canonical.replace("-", "_").lower()
    return detail.get(snake)


def _parse_geofence_id(raw_geofence_id: str) -> Tuple[Optional[str], Optional[str]]:
    token = str(raw_geofence_id or "").strip()
    if not token:
        return None, None

    if "|" in token:
        restaurant_id, event_name = token.split("|", 1)
    elif ":" in token:
        restaurant_id, event_name = token.rsplit(":", 1)
    else:
        return None, None

    normalized = event_name.strip().upper().replace("-", "_")
    if normalized == "FIVE_MIN_OUT":
        normalized = "5_MIN_OUT"
    if normalized not in _VALID_EVENTS:
        return restaurant_id.strip(), None

    return restaurant_id.strip(), normalized


def _find_candidate_order(customer_id: str, restaurant_id: str) -> Optional[Dict[str, Any]]:
    if not db.orders_table:
        return None

    response = db.orders_table.query(
        IndexName='GSI_CustomerOrders',
        KeyConditionExpression=Key('customer_id').eq(customer_id),
        ScanIndexForward=False,
        Limit=25,
    )
    for item in response.get('Items', []):
        destination_id = str(item.get('destination_id', item.get('restaurant_id', '')))
        if destination_id != restaurant_id:
            continue
        status = str(item.get('status', '')).upper()
        if status in _ACTIVE_STATUSES:
            return item
    return None


def _record_shadow_event(order_id: str, event_name: str, event_id: str) -> None:
    if not db.orders_table:
        return

    now = int(time.time())
    db.orders_table.update_item(
        Key={'order_id': order_id},
        UpdateExpression=(
            "SET geofence_shadow_last_event = :event, "
            "geofence_shadow_last_event_id = :event_id, "
            "geofence_shadow_last_received_at = :received_at"
        ),
        ExpressionAttributeValues={
            ':event': event_name,
            ':event_id': event_id,
            ':received_at': now,
        },
    )


def lambda_handler(event, context):
    req_log = log.bind(handler="geofence_events")

    event_id = str(event.get('id') or '')
    if not event_id:
        req_log.warning("missing_event_id")
        return {'statusCode': 200, 'body': json.dumps({'accepted': False, 'reason': 'missing_event_id'})}

    if not _claim_event(event_id):
        req_log.info("duplicate_event_suppressed", extra={'event': event_id})
        return {'statusCode': 200, 'body': json.dumps({'accepted': False, 'reason': 'duplicate_event'})}

    detail = event.get('detail') or {}
    event_type = str(_read_detail(detail, 'EventType') or '').upper()
    if event_type != 'ENTER':
        return {'statusCode': 200, 'body': json.dumps({'accepted': False, 'reason': 'non_enter_event'})}

    configured_collection = os.environ.get('LOCATION_GEOFENCE_COLLECTION_NAME', '').strip()
    event_collection = str(_read_detail(detail, 'GeofenceCollection') or '').strip()
    if configured_collection and event_collection and configured_collection != event_collection:
        req_log.info("collection_mismatch", extra={'detail': event_collection})
        return {'statusCode': 200, 'body': json.dumps({'accepted': False, 'reason': 'collection_mismatch'})}

    device_id = str(_read_detail(detail, 'DeviceId') or '').strip()
    geofence_id = str(_read_detail(detail, 'GeofenceId') or '').strip()
    if not device_id or not geofence_id:
        return {'statusCode': 200, 'body': json.dumps({'accepted': False, 'reason': 'missing_device_or_geofence'})}

    restaurant_id, arrival_event = _parse_geofence_id(geofence_id)
    if not restaurant_id or not arrival_event:
        return {'statusCode': 200, 'body': json.dumps({'accepted': False, 'reason': 'unsupported_geofence_id'})}

    session = _find_candidate_order(device_id, restaurant_id)
    if not session:
        req_log.info("no_candidate_order", extra={'customer_id': device_id, 'restaurant_id': restaurant_id})
        return {'statusCode': 200, 'body': json.dumps({'accepted': False, 'reason': 'no_candidate_order'})}

    order_id = str(session.get('order_id'))
    cutover_enabled = _to_bool(os.environ.get('LOCATION_GEOFENCE_CUTOVER_ENABLED'))
    force_shadow = _to_bool(os.environ.get('LOCATION_GEOFENCE_FORCE_SHADOW'))

    # Always keep a shadow trail so cutover can be validated and rolled back safely.
    _record_shadow_event(order_id, arrival_event, event_id)

    if force_shadow or not cutover_enabled:
        mode = 'forced_shadow' if force_shadow else 'shadow'
        req_log.info("shadow_event_recorded", extra={
            'order_id': order_id,
            'event': arrival_event,
            'customer_id': device_id,
            'mode': mode,
        })
        return {
            'statusCode': 200,
            'body': json.dumps({
                'accepted': True,
                'mode': mode,
                'order_id': order_id,
                'event': arrival_event,
            }),
        }

    synthetic = {'body': json.dumps({'event': arrival_event})}
    response = update_vicinity(order_id, synthetic, device_id)
    req_log.info("cutover_event_applied", extra={
        'order_id': order_id,
        'event': arrival_event,
        'status_code': response.get('statusCode'),
    })
    return response
