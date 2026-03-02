"""Scheduled Lambda: marks abandoned PENDING/WAITING orders as EXPIRED."""
import os
import time
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from shared.logger import get_logger

logger = get_logger(__name__)
_dynamodb = boto3.resource('dynamodb')
ORDERS_TABLE = os.environ.get('ORDERS_TABLE', '')
STATUS_PENDING = 'PENDING_NOT_SENT'
STATUS_WAITING = 'WAITING_FOR_CAPACITY'
STATUS_EXPIRED = 'EXPIRED'
EXPIRY_GSI_NAME = os.environ.get('EXPIRY_GSI_NAME', 'GSI_StatusExpiry')
EXPIRY_SCAN_FALLBACK_ENABLED = (
    os.environ.get('EXPIRY_SCAN_FALLBACK_ENABLED', 'true').strip().lower()
    in ('1', 'true', 'yes', 'on')
)
QUERY_FALLBACK_ERROR_CODES = frozenset({'ResourceNotFoundException', 'ValidationException'})

# Safety limits to avoid Lambda timeout and excessive DynamoDB consumption.
SCAN_PAGE_LIMIT = 100          # Max items per scan page
MAX_ITEMS_PER_RUN = 500        # Stop after processing this many items
REMAINING_MS_BUFFER = 2000     # Abort when less than 2s remain


def _should_abort(context, expired, errors, scanned):
    """Return True when runtime or per-run limits are reached."""
    if context and hasattr(context, 'get_remaining_time_in_millis'):
        remaining = context.get_remaining_time_in_millis()
        if remaining < REMAINING_MS_BUFFER:
            logger.warning('expire_orders_time_limit', extra={
                'expired': expired,
                'errors': errors,
                'scanned': scanned,
                'remaining_ms': remaining,
            })
            return True

    if scanned >= MAX_ITEMS_PER_RUN:
        logger.warning('expire_orders_item_limit', extra={
            'expired': expired,
            'errors': errors,
            'scanned': scanned,
        })
        return True

    return False


def _expire_page_items(table, page_items, now):
    expired = errors = 0
    for item in page_items:
        current_status = item.get('status')
        if not current_status:
            continue
        try:
            table.update_item(
                Key={'order_id': item['order_id']},
                UpdateExpression='SET #s = :exp, updated_at = :now',
                ConditionExpression='#s = :cur',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':exp': STATUS_EXPIRED,
                    ':cur': current_status,
                    ':now': now,
                },
            )
            expired += 1
            logger.info('order_expired', extra={'order_id': item['order_id'], 'was': current_status})
        except ClientError as e:
            if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                errors += 1
                logger.error('expire_error', extra={'order_id': item['order_id'], 'error': str(e)})
    return expired, errors


def _expire_via_query(table, now, context):
    """Primary path: query status/expiry GSI."""
    expired = errors = scanned = 0
    for status in (STATUS_PENDING, STATUS_WAITING):
        last_key = None
        while True:
            if _should_abort(context, expired, errors, scanned):
                return expired, errors, scanned

            kwargs = {
                'IndexName': EXPIRY_GSI_NAME,
                'KeyConditionExpression': Key('status').eq(status) & Key('expires_at').lt(now),
                'Limit': SCAN_PAGE_LIMIT,
            }
            if last_key:
                kwargs['ExclusiveStartKey'] = last_key

            resp = table.query(**kwargs)
            page_items = resp.get('Items', [])
            scanned += len(page_items)

            page_expired, page_errors = _expire_page_items(table, page_items, now)
            expired += page_expired
            errors += page_errors

            last_key = resp.get('LastEvaluatedKey')
            if not last_key:
                break

    return expired, errors, scanned


def _expire_via_scan(table, now, context):
    """Fallback path used when GSI is unavailable during rollout."""
    expired = errors = scanned = 0
    last_key = None
    while True:
        if _should_abort(context, expired, errors, scanned):
            break

        kwargs = {
            'FilterExpression': '#s IN (:p, :w) AND expires_at < :now',
            'ExpressionAttributeNames': {'#s': 'status'},
            'ExpressionAttributeValues': {':p': STATUS_PENDING, ':w': STATUS_WAITING, ':now': now},
            'Limit': SCAN_PAGE_LIMIT,
        }
        if last_key:
            kwargs['ExclusiveStartKey'] = last_key

        resp = table.scan(**kwargs)
        page_items = resp.get('Items', [])
        scanned += len(page_items)

        page_expired, page_errors = _expire_page_items(table, page_items, now)
        expired += page_expired
        errors += page_errors

        last_key = resp.get('LastEvaluatedKey')
        if not last_key:
            break

    return expired, errors, scanned


def lambda_handler(event, context):
    if not ORDERS_TABLE:
        logger.error('ORDERS_TABLE not set')
        return

    table = _dynamodb.Table(ORDERS_TABLE)
    now = int(time.time())

    try:
        expired, errors, scanned = _expire_via_query(table, now, context)
        logger.info('expire_orders_done', extra={
            'mode': 'query',
            'expired': expired,
            'errors': errors,
            'scanned': scanned,
        })
        return
    except ClientError as e:
        error_code = e.response['Error'].get('Code')
        if not (EXPIRY_SCAN_FALLBACK_ENABLED and error_code in QUERY_FALLBACK_ERROR_CODES):
            logger.error('expire_query_failed', extra={'error_code': error_code, 'error': str(e)})
            raise

        logger.warning('expire_query_fallback_to_scan', extra={
            'index_name': EXPIRY_GSI_NAME,
            'error_code': error_code,
        })

    expired, errors, scanned = _expire_via_scan(table, now, context)
    logger.info('expire_orders_done', extra={
        'mode': 'scan_fallback',
        'expired': expired,
        'errors': errors,
        'scanned': scanned,
    })
