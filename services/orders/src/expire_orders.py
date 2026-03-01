"""Scheduled Lambda: marks abandoned PENDING/WAITING orders as EXPIRED."""
import os
import time
import boto3
from botocore.exceptions import ClientError
from shared.logger import get_logger

logger = get_logger(__name__)
_dynamodb = boto3.resource('dynamodb')
ORDERS_TABLE = os.environ.get('ORDERS_TABLE', '')
STATUS_PENDING = 'PENDING_NOT_SENT'
STATUS_WAITING = 'WAITING_FOR_CAPACITY'
STATUS_EXPIRED = 'EXPIRED'


def lambda_handler(event, context):
    if not ORDERS_TABLE:
        logger.error('ORDERS_TABLE not set')
        return
    table = _dynamodb.Table(ORDERS_TABLE)
    now = int(time.time())
    expired = errors = 0
    last_key = None
    while True:
        kwargs = {
            'FilterExpression': '#s IN (:p, :w) AND expires_at < :now',
            'ExpressionAttributeNames': {'#s': 'status'},
            'ExpressionAttributeValues': {':p': STATUS_PENDING, ':w': STATUS_WAITING, ':now': now},
        }
        if last_key:
            kwargs['ExclusiveStartKey'] = last_key
        resp = table.scan(**kwargs)
        for item in resp.get('Items', []):
            try:
                table.update_item(
                    Key={'order_id': item['order_id']},
                    UpdateExpression='SET #s = :exp, updated_at = :now',
                    ConditionExpression='#s = :cur',
                    ExpressionAttributeNames={'#s': 'status'},
                    ExpressionAttributeValues={
                        ':exp': STATUS_EXPIRED,
                        ':cur': item['status'],
                        ':now': now,
                    },
                )
                expired += 1
                logger.info('order_expired', extra={'order_id': item['order_id'], 'was': item['status']})
            except ClientError as e:
                if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                    errors += 1
                    logger.error('expire_error', extra={'order_id': item['order_id'], 'error': str(e)})
        last_key = resp.get('LastEvaluatedKey')
        if not last_key:
            break
    logger.info('expire_orders_done', extra={'expired': expired, 'errors': errors})
