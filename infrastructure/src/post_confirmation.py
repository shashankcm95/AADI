import json
import boto3
import os
import time
from datetime import datetime

cognito = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')
USERS_TABLE = os.environ.get('USERS_TABLE')

def lambda_handler(event, context):
    """
    Post Confirmation Lambda Trigger.
    1. Sets default 'custom:role' to 'customer' in Cognito if not set.
    2. Creates a user profile in DynamoDB UsersTable.
    """
    print(f"Received event: {json.dumps(event)}")
    
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
            print(f"Setting default role 'customer' for user {username}")
            cognito.admin_update_user_attributes(
                UserPoolId=user_pool_id,
                Username=username,
                UserAttributes=[
                    {'Name': 'custom:role', 'Value': 'customer'}
                ]
            )
            current_role = 'customer'
        else:
            print(f"User {username} already has role: {current_role}")

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
                print(f"Created DynamoDB profile for user {user_id}")
            except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                print(f"Profile already exists for user {user_id}")
            except Exception as e:
                print(f"Failed to create DynamoDB profile: {e}")
        else:
            print("Skipping DynamoDB profile creation: USERS_TABLE or user_id missing")

        return event
        
    except Exception as e:
        print(f"Error in post_confirmation: {e}")
        # Return event anyway to not block sign-up, but log error
        return event
