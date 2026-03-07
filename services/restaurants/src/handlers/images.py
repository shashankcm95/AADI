"""Image upload URL handler."""
import json
import os
import uuid

from shared.logger import get_logger
from utils import (
    get_user_claims, _is_admin_or_owner, make_response,
    restaurants_table, s3_client, RESTAURANT_IMAGES_BUCKET,
    _build_image_url,
)

logger = get_logger("restaurants.images")


def create_image_upload_url(event, restaurant_id):
    """Generate a short-lived pre-signed S3 URL for restaurant image uploads."""
    if not restaurant_id:
        return make_response(400, {'error': 'restaurant_id is required'}, event)

    claims = get_user_claims(event)
    if not _is_admin_or_owner(claims, restaurant_id):
        return make_response(403, {'error': 'Access denied'}, event)

    if not RESTAURANT_IMAGES_BUCKET:
        return make_response(500, {'error': 'Image bucket not configured'}, event)

    restaurant_record = None
    if restaurants_table:
        resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
        restaurant_record = resp.get('Item')
        if not restaurant_record:
            return make_response(404, {'error': 'Restaurant not found'}, event)

    try:
        body = json.loads(event.get('body', '{}'))
    except Exception:
        body = {}

    file_name = str(body.get('file_name') or 'upload.jpg').strip()
    content_type = str(body.get('content_type') or '').strip().lower()
    if not content_type.startswith('image/'):
        return make_response(400, {'error': 'content_type must be an image/* MIME type'}, event)

    if content_type == 'image/svg+xml':
        return make_response(400, {'error': 'SVG uploads are not allowed'}, event)

    existing_image_keys = []
    if isinstance(restaurant_record, dict):
        existing_image_keys = restaurant_record.get('restaurant_image_keys') or []
    if isinstance(existing_image_keys, list) and len(existing_image_keys) >= 5:
        return make_response(400, {'error': 'A maximum of 5 restaurant images is allowed'}, event)

    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.heic', '.heif'):
        ext_by_type = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/webp': '.webp',
            'image/gif': '.gif',
            'image/heic': '.heic',
            'image/heif': '.heif',
        }
        ext = ext_by_type.get(content_type, '.jpg')

    object_key = f"restaurants/{restaurant_id}/{uuid.uuid4().hex}{ext}"
    upload_ttl_seconds = 900

    try:
        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': RESTAURANT_IMAGES_BUCKET,
                'Key': object_key,
                'ContentType': content_type,
            },
            ExpiresIn=upload_ttl_seconds,
        )
    except Exception as e:
        logger.error("presigned_url_failed", extra={"restaurant_id": restaurant_id, "error": str(e)})
        return make_response(500, {'error': 'Failed to generate upload URL'}, event)

    return make_response(200, {
        'upload_url': upload_url,
        'object_key': object_key,
        'preview_url': _build_image_url(object_key),
        'expires_in_seconds': upload_ttl_seconds,
    }, event)
