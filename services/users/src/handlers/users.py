import re
import time
import json
import os
from botocore.exceptions import ClientError
from utils import get_user_claims, json_response, users_table, s3_client
from shared.logger import get_logger

logger = get_logger("users")

# Allowed avatar content types and their extensions
_CONTENT_TYPE_TO_EXT = {
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/gif': 'gif',
}

# Pattern: avatars/{user_id}-{unix_timestamp}.{ext}
_AVATAR_KEY_RE = re.compile(r'^avatars/[^/]+-\d+\.(jpg|png|webp|gif)$')


def get_profile(event):
    """
    GET /v1/users/me
    Retrieve the authenticated user's profile.
    """
    claims = get_user_claims(event)
    user_id = claims.get('user_id')

    if not user_id:
        return json_response(401, {'error': 'Unauthorized'}, event)

    try:
        if not users_table:
            return json_response(500, {'error': 'Database configuration error'}, event)

        response = users_table.get_item(Key={'user_id': user_id})
        item = response.get('Item')

        if not item:
            return json_response(404, {'error': 'Profile not found'}, event)

        return json_response(200, item, event)

    except Exception as e:
        logger.error("Error fetching profile", extra={"user_id": user_id, "error": str(e)})
        return json_response(500, {'error': 'Failed to fetch profile'}, event)


def update_profile(event):
    """
    PUT /v1/users/me
    Update allowed fields in the authenticated user's profile.
    Allowed: name, phone_number, picture
    Immutable: role, email, user_id
    """
    claims = get_user_claims(event)
    user_id = claims.get('user_id')

    if not user_id:
        return json_response(401, {'error': 'Unauthorized'}, event)

    try:
        if not event.get('body'):
            return json_response(400, {'error': 'Missing request body'}, event)

        body = json.loads(event['body'])

    except Exception:
        return json_response(400, {'error': 'Invalid JSON'}, event)

    # Allowed updates
    update_expression_parts = []
    expression_attribute_values = {}
    expression_attribute_names = {}

    allowed_fields = {
        'name': 'name',
        'phone_number': 'phone_number',
        'picture': 'picture',
    }

    timestamp = int(time.time())
    update_expression_parts.append('#updated_at = :updated_at')
    expression_attribute_names['#updated_at'] = 'updated_at'
    expression_attribute_values[':updated_at'] = timestamp

    for field, db_attr in allowed_fields.items():
        if field not in body:
            continue

        if field == 'picture':
            # Validate that the key belongs to this user and matches expected format
            picture_val = body[field]
            if not isinstance(picture_val, str) or not _AVATAR_KEY_RE.match(picture_val):
                return json_response(400, {'error': 'Invalid picture key format'}, event)
            # Ensure the key is scoped to the authenticated user
            if not picture_val.startswith(f'avatars/{user_id}-'):
                return json_response(400, {'error': 'picture key does not belong to this user'}, event)

        attr_placeholder = f"#{field}"
        val_placeholder = f":{field}"
        update_expression_parts.append(f"{attr_placeholder} = {val_placeholder}")
        expression_attribute_names[attr_placeholder] = db_attr
        expression_attribute_values[val_placeholder] = body[field]

    if len(update_expression_parts) == 1:  # Only updated_at
        return json_response(400, {'error': 'No valid fields to update'}, event)

    update_expression = "SET " + ", ".join(update_expression_parts)

    try:
        response = users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ConditionExpression='attribute_exists(user_id)',
            ReturnValues="ALL_NEW",
        )

        return json_response(200, response.get('Attributes'), event)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return json_response(404, {'error': 'Profile not found'}, event)
        logger.error("Error updating profile", extra={"user_id": user_id, "error": str(e)})
        return json_response(500, {'error': 'Failed to update profile'}, event)

    except Exception as e:
        logger.error("Error updating profile", extra={"user_id": user_id, "error": str(e)})
        return json_response(500, {'error': 'Failed to update profile'}, event)


def create_avatar_upload_url(event):
    """
    POST /v1/users/me/avatar/upload-url
    Generate a presigned S3 URL for uploading an avatar.
    Returns: { "upload_url": "...", "s3_key": "...", "public_url": "..." }
    """
    claims = get_user_claims(event)
    user_id = claims.get('user_id')

    if not user_id:
        return json_response(401, {'error': 'Unauthorized'}, event)

    bucket_name = os.environ.get('AVATARS_BUCKET_NAME')
    if not bucket_name:
        return json_response(500, {'error': 'Storage configuration error'}, event)

    try:
        content_type = 'image/jpeg'
        ext = 'jpg'

        if event.get('body'):
            try:
                body = json.loads(event['body'])
                requested_ct = body.get('content_type')
                if requested_ct and requested_ct in _CONTENT_TYPE_TO_EXT:
                    content_type = requested_ct
                    ext = _CONTENT_TYPE_TO_EXT[content_type]
            except Exception:
                pass

        timestamp = int(time.time())
        s3_key = f"avatars/{user_id}-{timestamp}.{ext}"
        region = os.environ.get('AWS_REGION', 'us-east-1')
        public_base_url = os.environ.get(
            'AVATARS_PUBLIC_BASE_URL',
            f"https://{bucket_name}.s3.{region}.amazonaws.com"
        ).rstrip('/')
        public_url = f"{public_base_url}/{s3_key}"

        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key,
                'ContentType': content_type,
            },
            ExpiresIn=300,  # 5 minutes
        )

        return json_response(200, {
            'upload_url': upload_url,
            's3_key': s3_key,
            'bucket': bucket_name,
            'region': region,
            'public_url': public_url,
        }, event)

    except Exception as e:
        logger.error("Error generating upload URL", extra={"user_id": user_id, "error": str(e)})
        return json_response(500, {'error': 'Failed to generate upload URL'}, event)
