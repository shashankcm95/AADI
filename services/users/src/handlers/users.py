import logging
import time
import json
import os
import boto3
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
        'phone_number': 'phone_number',
        'picture': 'picture'
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


def create_avatar_upload_url(event):
    """
    POST /v1/users/me/avatar/upload-url
    Generate a presigned S3 URL for uploading an avatar.
    Returns: { "upload_url": "...", "s3_key": "..." }
    """
    claims = get_user_claims(event)
    user_id = claims.get('user_id')
    
    if not user_id:
        return json_response(401, {'error': 'Unauthorized'})
        
    bucket_name = os.environ.get('AVATARS_BUCKET_NAME')
    if not bucket_name:
        return json_response(500, {'error': 'Storage configuration error'})
        
    try:
        # Presigned URLs are content-type specific; default to JPEG.
        content_type = 'image/jpeg'
        ext = 'jpg'
        content_type_to_ext = {
            'image/jpeg': 'jpg',
            'image/jpg': 'jpg',
            'image/png': 'png',
            'image/webp': 'webp',
            'image/gif': 'gif'
        }

        if event.get('body'):
            try:
                body = json.loads(event['body'])
                requested_content_type = body.get('content_type')
                if requested_content_type:
                    content_type = requested_content_type
                    ext = content_type_to_ext.get(content_type, 'jpg')
            except Exception:
                pass

        timestamp = int(time.time())
        s3_key = f"avatars/{user_id}-{timestamp}.{ext}"
        region = os.environ.get('AWS_REGION', 'us-east-1')
        public_base_url = os.environ.get('AVATARS_PUBLIC_BASE_URL', f"https://{bucket_name}.s3.{region}.amazonaws.com").rstrip('/')
        public_url = f"{public_base_url}/{s3_key}"
        
        s3_client = boto3.client('s3')
        
        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key,
                'ContentType': content_type
            },
            ExpiresIn=300 # 5 minutes
        )
        
        return json_response(200, {
            'upload_url': upload_url,
            's3_key': s3_key,
            'bucket': bucket_name,
            'region': region,
            'public_url': public_url
        })
        
    except Exception as e:
        logger.error(f"Error generating upload URL for {user_id}: {e}")
        return json_response(500, {'error': 'Failed to generate upload URL'})
