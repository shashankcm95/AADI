"""Asynchronous worker for global geofence resync jobs."""
import json
import os
import time

import boto3

from shared.logger import get_logger
from utils import GLOBAL_CONFIG_ID, config_table, restaurants_table, upsert_restaurant_geofences

log = get_logger("restaurants.geofence_resync_worker", service="restaurants")

GEOFENCE_RESYNC_QUEUE_URL = os.environ.get('GEOFENCE_RESYNC_QUEUE_URL', '').strip()
GEOFENCE_RESYNC_TASK_TYPE = 'geofence_resync'

_sqs_client = None


def _env_int(name, default_value):
    try:
        value = int(os.environ.get(name, default_value))
    except (TypeError, ValueError):
        value = int(default_value)
    return max(1, value)


GEOFENCE_RESYNC_BATCH_SIZE = _env_int('GEOFENCE_RESYNC_BATCH_SIZE', 25)
GEOFENCE_RESYNC_MAX_UPSERT_ATTEMPTS = _env_int('GEOFENCE_RESYNC_MAX_UPSERT_ATTEMPTS', 3)


def _get_sqs_client():
    global _sqs_client
    if _sqs_client is not None:
        return _sqs_client if _sqs_client else None
    try:
        _sqs_client = boto3.client('sqs')
    except Exception as e:
        print(f"Failed to create SQS client: {e}")
        _sqs_client = False
    return _sqs_client if _sqs_client else None


def _to_int(value, default_value=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default_value)


def _normalize_cursor(value):
    if isinstance(value, dict) and value:
        return value
    return None


def _load_sync_state(job_id, now):
    default_state = {
        'job_id': str(job_id),
        'status': 'IN_PROGRESS',
        'queued_at': int(now),
        'started_at': int(now),
        'attempted': 0,
        'updated': 0,
        'failed': 0,
        'batches_processed': 0,
    }

    if not config_table:
        return default_state

    try:
        existing = config_table.get_item(Key={'restaurant_id': GLOBAL_CONFIG_ID}).get('Item', {})
    except Exception as e:
        print(f"Failed to read global config for sync state: {e}")
        return default_state

    raw_state = existing.get('geofence_sync')
    if not isinstance(raw_state, dict) or raw_state.get('job_id') != str(job_id):
        return default_state

    state = dict(raw_state)
    state['job_id'] = str(job_id)
    state['status'] = 'IN_PROGRESS'
    state['queued_at'] = _to_int(state.get('queued_at'), now)
    state['started_at'] = _to_int(state.get('started_at'), now)
    state['attempted'] = _to_int(state.get('attempted'), 0)
    state['updated'] = _to_int(state.get('updated'), 0)
    state['failed'] = _to_int(state.get('failed'), 0)
    state['batches_processed'] = _to_int(state.get('batches_processed'), 0)
    return state


def _persist_sync_state(state):
    if not config_table:
        return
    config_table.update_item(
        Key={'restaurant_id': GLOBAL_CONFIG_ID},
        UpdateExpression='SET geofence_sync = :gs, updated_at = :u',
        ExpressionAttributeValues={
            ':gs': state,
            ':u': int(time.time()),
        },
    )


def _enqueue_follow_up(job_id, cursor, queued_at):
    if not GEOFENCE_RESYNC_QUEUE_URL:
        raise RuntimeError('GEOFENCE_RESYNC_QUEUE_URL is not configured')

    sqs = _get_sqs_client()
    if sqs is None:
        raise RuntimeError('SQS client unavailable')

    sqs.send_message(
        QueueUrl=GEOFENCE_RESYNC_QUEUE_URL,
        MessageBody=json.dumps({
            'task_type': GEOFENCE_RESYNC_TASK_TYPE,
            'job_id': str(job_id),
            'queued_at': int(queued_at),
            'cursor': cursor,
        }),
    )


def _upsert_with_retry(restaurant_id, location):
    for attempt in range(1, GEOFENCE_RESYNC_MAX_UPSERT_ATTEMPTS + 1):
        if upsert_restaurant_geofences(restaurant_id, location):
            return True
        if attempt < GEOFENCE_RESYNC_MAX_UPSERT_ATTEMPTS:
            time.sleep(min(0.1 * attempt, 0.3))
    return False


def _process_batch(cursor):
    if not restaurants_table:
        return {
            'attempted': 0,
            'updated': 0,
            'failed': 0,
            'last_evaluated_key': None,
        }

    scan_kwargs = {'Limit': GEOFENCE_RESYNC_BATCH_SIZE}
    if cursor:
        scan_kwargs['ExclusiveStartKey'] = cursor

    response = restaurants_table.scan(**scan_kwargs)

    attempted = 0
    updated = 0
    failed = 0

    for item in response.get('Items', []):
        restaurant_id = item.get('restaurant_id')
        if not restaurant_id:
            continue

        attempted += 1
        if _upsert_with_retry(restaurant_id, item.get('location')):
            updated += 1
        else:
            failed += 1

    return {
        'attempted': attempted,
        'updated': updated,
        'failed': failed,
        'last_evaluated_key': response.get('LastEvaluatedKey'),
    }


def _handle_job_message(message, req_log):
    job_id = str(message.get('job_id') or '').strip()
    if not job_id:
        raise ValueError('Missing job_id in geofence resync message')

    now = int(time.time())
    cursor = _normalize_cursor(message.get('cursor'))
    state = _load_sync_state(job_id, now)

    batch_result = _process_batch(cursor)
    next_cursor = _normalize_cursor(batch_result.get('last_evaluated_key'))

    state['attempted'] = _to_int(state.get('attempted'), 0) + batch_result['attempted']
    state['updated'] = _to_int(state.get('updated'), 0) + batch_result['updated']
    state['failed'] = _to_int(state.get('failed'), 0) + batch_result['failed']
    state['batches_processed'] = _to_int(state.get('batches_processed'), 0) + 1
    state['last_batch_attempted'] = batch_result['attempted']
    state['last_batch_updated'] = batch_result['updated']
    state['last_batch_failed'] = batch_result['failed']
    state['last_batch_at'] = now

    if next_cursor:
        _enqueue_follow_up(job_id=job_id, cursor=next_cursor, queued_at=state.get('queued_at', now))
        state['status'] = 'IN_PROGRESS'
    else:
        state['status'] = 'COMPLETED'
        state['completed_at'] = now

    _persist_sync_state(state)

    req_log.info('geofence_resync_batch_processed', extra={
        'job_id': job_id,
        'status': state.get('status'),
        'batch_attempted': batch_result['attempted'],
        'batch_updated': batch_result['updated'],
        'batch_failed': batch_result['failed'],
        'total_attempted': state.get('attempted'),
        'total_updated': state.get('updated'),
        'total_failed': state.get('failed'),
        'batches_processed': state.get('batches_processed'),
        'has_next_batch': bool(next_cursor),
    })


def lambda_handler(event, context):
    req_log = log.bind(request_id=getattr(context, 'aws_request_id', 'no-request-id'))

    for record in event.get('Records', []):
        payload = json.loads(record.get('body') or '{}')
        if payload.get('task_type') != GEOFENCE_RESYNC_TASK_TYPE:
            req_log.info('ignored_queue_message', extra={'task_type': payload.get('task_type')})
            continue
        _handle_job_message(payload, req_log)

    return {'statusCode': 200, 'processed': len(event.get('Records', []))}
