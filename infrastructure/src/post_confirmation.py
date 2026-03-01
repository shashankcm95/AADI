import json
import boto3
import os
import time
import logging
from datetime import datetime

cognito = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')
USERS_TABLE = os.environ.get('USERS_TABLE')

logger = logging.getLogger("post_confirmation")
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Post Confirmation Lambda Trigger.
    1. Sets default 'custom:role' to 'customer' in Cognito if not set.
    2. Creates a user profile in DynamoDB UsersTable.
    """
    logger.info("post_confirmation_triggered", extra={
        "trigger_source": event.get("triggerSource"),
        "user_pool_id": event.get("userPoolId"),
    })
    
    try:
        request = event.get('request', {})
        user_attributes = request.get('userAttributes', {})
        user_pool_id = event.get('userPoolId')
        username = event.get('userName')
        user_id = user_attributes.get('sub')
        email = user_attributes.get('email')
        
        # 1. Update Cognito Attributes (Role)
        current_role = user_attributes.get('custom:role')
        if not current_role:
            logger.info("setting_default_role", extra={"username": username, "role": "customer"})
            cognito.admin_update_user_attributes(
                UserPoolId=user_pool_id,
                Username=username,
                UserAttributes=[
                    {'Name': 'custom:role', 'Value': 'customer'}
                ]
            )
            current_role = 'customer'
        else:
            logger.info("role_already_set", extra={"username": username, "role": current_role})

        # 2. Create DynamoDB Profile
        if USERS_TABLE and user_id:
            table = dynamodb.Table(USERS_TABLE)
            timestamp = int(time.time())
            iso_timestamp = datetime.utcnow().isoformat()
            
            item = {
                'user_id': user_id,
                'email': email,
                'role': current_role,
                'name': user_attributes.get('name', ''),
                'phone_number': user_attributes.get('phone_number', ''),
                'created_at': timestamp,
                'updated_at': timestamp,
                'created_at_iso': iso_timestamp
            }
            
            # Use ConditionExpression to avoid overwriting existing profile if trigger fires multiple times
            try:
                table.put_item(
                    Item=item,
                    ConditionExpression='attribute_not_exists(user_id)'
                )
                logger.info("profile_created", extra={"user_id": user_id})
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                logger.info("profile_already_exists", extra={"user_id": user_id})
            except Exception as e:
                logger.error("profile_creation_failed", extra={"user_id": user_id, "error": str(e)})
        else:
            logger.warning("profile_creation_skipped", extra={"reason": "missing_users_table_or_user_id"})

        return event
        
    except Exception as e:
        logger.error("post_confirmation_failed", extra={"error": str(e)}, exc_info=True)
        # Return event anyway to not block sign-up, but log error
        return event
