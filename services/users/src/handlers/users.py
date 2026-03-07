import re
import time
import json
import os
from urllib.parse import urlparse
from botocore.exceptions import ClientError
from utils import get_user_claims, make_response, users_table, s3_client
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
_AVATAR_KEY_RE = re.compile(r'^avatars/[a-zA-Z0-9_-]+-\d+\.(jpg|png|webp|gif)$')
_DEFAULT_AVATAR_GET_URL_TTL_SECONDS = 900


def _avatar_get_url_ttl_seconds():
    try:
        return max(60, int(os.environ.get('AVATAR_GET_URL_TTL_SECONDS', _DEFAULT_AVATAR_GET_URL_TTL_SECONDS)))
    except (TypeError, ValueError):
        return _DEFAULT_AVATAR_GET_URL_TTL_SECONDS


def _extract_avatar_key(value, bucket_name):
    candidate = str(value or '').strip()
    if not candidate:
        return None

    if _AVATAR_KEY_RE.match(candidate):
        return candidate

    if not bucket_name:
        return None

    parsed = urlparse(candidate)
    if parsed.scheme not in ('http', 'https'):
        return None

    host = (parsed.netloc or '').lower()
    bucket = str(bucket_name).lower()
    if not host.endswith('amazonaws.com'):
        return None

    path = parsed.path.lstrip('/')
    if not path:
        return None

    # Virtual-hosted style: <bucket>.s3.<region>.amazonaws.com/<key>
    if host.startswith(f'{bucket}.s3.'):
        pass
    # Path-style URL: s3.<region>.amazonaws.com/<bucket>/<key>
    elif host.startswith('s3.') and path.startswith(f'{bucket_name}/'):
        path = path[len(bucket_name) + 1:]
    else:
        return None

    if _AVATAR_KEY_RE.match(path):
        return path
    return None


def _build_avatar_read_url(bucket_name, avatar_key):
    if not bucket_name or not avatar_key:
        return None
    try:
        return s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': avatar_key,
            },
            ExpiresIn=_avatar_get_url_ttl_seconds(),
        )
    except Exception as e:
        logger.warning("Failed to presign avatar URL", extra={"avatar_key": avatar_key, "error": str(e)})
        return None


def _with_picture_url(item):
    if not isinstance(item, dict):
        return item

    payload = dict(item)
    bucket_name = os.environ.get('AVATARS_BUCKET_NAME')
    avatar_key = _extract_avatar_key(payload.get('picture'), bucket_name)
    if avatar_key:
        payload['picture'] = avatar_key
        avatar_url = _build_avatar_read_url(bucket_name, avatar_key)
        if avatar_url:
            payload['picture_url'] = avatar_url
    return payload


def get_profile(event):
    """
    GET /v1/users/me
    Retrieve the authenticated user's profile.
    """
    claims = get_user_claims(event)
    user_id = claims.get('user_id')

    if not user_id:
        return make_response(401, {'error': 'Unauthorized'}, event)

    try:
        if not users_table:
            return make_response(500, {'error': 'Database configuration error'}, event)

        response = users_table.get_item(Key={'user_id': user_id})
        item = response.get('Item')

        if not item:
            return make_response(404, {'error': 'Profile not found'}, event)

        return make_response(200, _with_picture_url(item), event)

    except Exception as e:
        logger.error("Error fetching profile", extra={"user_id": user_id, "error": str(e)})
        return make_response(500, {'error': 'Failed to fetch profile'}, event)


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
        return make_response(401, {'error': 'Unauthorized'}, event)

    try:
        if not event.get('body'):
            return make_response(400, {'error': 'Missing request body'}, event)

        body = json.loads(event['body'])

    except Exception:
        return make_response(400, {'error': 'Invalid JSON'}, event)

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

        if field == 'name':
            val = body[field]
            if not isinstance(val, str) or not val.strip() or len(val) > 255:
                return make_response(400, {'error': 'name must be a non-empty string (max 255 chars)'}, event)

        if field == 'phone_number':
            val = body[field]
            if not isinstance(val, str) or len(val) > 30:
                return make_response(400, {'error': 'phone_number must be a string (max 30 chars)'}, event)

        if field == 'picture':
            # Validate that the key belongs to this user and matches expected format
            picture_val = body[field]
            if not isinstance(picture_val, str) or not _AVATAR_KEY_RE.match(picture_val):
                return make_response(400, {'error': 'Invalid picture key format'}, event)
            # Ensure the key is scoped to the authenticated user
            if not picture_val.startswith(f'avatars/{user_id}-'):
                return make_response(400, {'error': 'picture key does not belong to this user'}, event)

        attr_placeholder = f"#{field}"
        val_placeholder = f":{field}"
        update_expression_parts.append(f"{attr_placeholder} = {val_placeholder}")
        expression_attribute_names[attr_placeholder] = db_attr
        expression_attribute_values[val_placeholder] = body[field]

    if len(update_expression_parts) == 1:  # Only updated_at
        return make_response(400, {'error': 'No valid fields to update'}, event)

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

        return make_response(200, _with_picture_url(response.get('Attributes')), event)

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return make_response(404, {'error': 'Profile not found'}, event)
        logger.error("Error updating profile", extra={"user_id": user_id, "error": str(e)})
        return make_response(500, {'error': 'Failed to update profile'}, event)

    except Exception as e:
        logger.error("Error updating profile", extra={"user_id": user_id, "error": str(e)})
        return make_response(500, {'error': 'Failed to update profile'}, event)


def create_avatar_upload_url(event):
    """
    POST /v1/users/me/avatar/upload-url
    Generate a presigned S3 URL for uploading an avatar.
    Returns: { "upload_url": "...", "s3_key": "...", "expires_in": 300 }
    """
    claims = get_user_claims(event)
    user_id = claims.get('user_id')

    if not user_id:
        return make_response(401, {'error': 'Unauthorized'}, event)

    bucket_name = os.environ.get('AVATARS_BUCKET_NAME')
    if not bucket_name:
        return make_response(500, {'error': 'Storage configuration error'}, event)

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
            except Exception as e:
                logger.warning("avatar_upload_body_parse_failed", extra={"user_id": user_id, "error": str(e)})

        timestamp = int(time.time())
        s3_key = f"avatars/{user_id}-{timestamp}.{ext}"
        upload_expires_in = 300

        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key,
                'ContentType': content_type,
            },
            ExpiresIn=upload_expires_in,
        )

        return make_response(200, {
            'upload_url': upload_url,
            's3_key': s3_key,
            'expires_in': upload_expires_in,
        }, event)

    except Exception as e:
        logger.error("Error generating upload URL", extra={"user_id": user_id, "error": str(e)})
        return make_response(500, {'error': 'Failed to generate upload URL'}, event)
