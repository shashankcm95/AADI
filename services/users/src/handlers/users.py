import logging
import time
import json
from datetime import datetime
from utils import get_user_claims, json_response, users_table

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_profile(event):
    """
    GET /v1/users/me
    Retrieve the authenticated user's profile.
    """
    claims = get_user_claims(event)
    user_id = claims.get('user_id')
    
    if not user_id:
        return json_response(401, {'error': 'Unauthorized'})

    try:
        if not users_table:
            return json_response(500, {'error': 'Database configuration error'})

        response = users_table.get_item(Key={'user_id': user_id})
        item = response.get('Item')
        
        if not item:
            return json_response(404, {'error': 'Profile not found'})
            
        return json_response(200, item)
        
    except Exception as e:
        logger.error(f"Error fetching profile for {user_id}: {e}")
        return json_response(500, {'error': 'Failed to fetch profile'})


def update_profile(event):
    """
    PUT /v1/users/me
    Update allowed fields in the authenticated user's profile.
    Allowed: name, phone_number
    ignored: role, email, user_id (immutable or managed by Auth)
    """
    claims = get_user_claims(event)
    user_id = claims.get('user_id')
    
    if not user_id:
        return json_response(401, {'error': 'Unauthorized'})
        
    try:
        if not event.get('body'):
            return json_response(400, {'error': 'Missing request body'})
            
        body = json.loads(event['body'])
        
    except Exception:
         return json_response(400, {'error': 'Invalid JSON'})

    # Allowed updates
    update_expression_parts = []
    expression_attribute_values = {}
    expression_attribute_names = {}
    
    allowed_fields = {
        'name': 'name',
        'phone_number': 'phone_number'
    }
    
    timestamp = int(time.time())
    update_expression_parts.append('#updated_at = :updated_at')
    expression_attribute_names['#updated_at'] = 'updated_at'
    expression_attribute_values[':updated_at'] = timestamp

    for field, db_attr in allowed_fields.items():
        if field in body:
            attr_placeholder = f"#{field}"
            val_placeholder = f":{field}"
            
            update_expression_parts.append(f"{attr_placeholder} = {val_placeholder}")
            expression_attribute_names[attr_placeholder] = db_attr
            expression_attribute_values[val_placeholder] = body[field]
            
    if len(update_expression_parts) == 1: # Only updated_at
        return json_response(400, {'error': 'No valid fields to update'})

    update_expression = "SET " + ", ".join(update_expression_parts)
    
    try:
        response = users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="ALL_NEW"
        )
        
        return json_response(200, response.get('Attributes'))
        
    except Exception as e:
        logger.error(f"Error updating profile for {user_id}: {e}")
        return json_response(500, {'error': 'Failed to update profile'})
