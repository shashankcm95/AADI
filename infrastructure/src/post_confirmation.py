import json
import boto3
import os

cognito = boto3.client('cognito-idp')

def lambda_handler(event, context):
    """
    Post Confirmation Lambda Trigger.
    Sets default 'custom:role' to 'customer' if not already set.
    """
    print(f"Received event: {json.dumps(event)}")
    
    try:
        user_attributes = event.get('request', {}).get('userAttributes', {})
        user_pool_id = event.get('userPoolId')
        username = event.get('userName')
        
        # Check if role is already set (e.g. by admin creator)
        if 'custom:role' in user_attributes:
            print(f"User {username} already has role: {user_attributes['custom:role']}")
            return event
            
        print(f"Setting default role 'customer' for user {username}")
        
        cognito.admin_update_user_attributes(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[
                {
                    'Name': 'custom:role',
                    'Value': 'customer'
                }
            ]
        )
        
        print("Successfully updated user attributes.")
        return event
        
    except Exception as e:
        print(f"Error updating user attributes: {e}")
        # Return event anyway to not block sign-up, but log error
        return event
