"""Image upload URL handler."""
import json
import os
import uuid

from utils import (
    CORS_HEADERS, get_user_claims, _is_admin_or_owner,
    restaurants_table, s3_client, RESTAURANT_IMAGES_BUCKET,
    _build_image_url,
)


def create_image_upload_url(event, restaurant_id):
    """Generate a short-lived pre-signed S3 URL for restaurant image uploads."""
    if not restaurant_id:
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'restaurant_id is required'})}

    claims = get_user_claims(event)
    if not _is_admin_or_owner(claims, restaurant_id):
        return {'statusCode': 403, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Access denied'})}

    if not RESTAURANT_IMAGES_BUCKET:
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Image bucket not configured'})}

    restaurant_record = None
    if restaurants_table:
        resp = restaurants_table.get_item(Key={'restaurant_id': restaurant_id})
        restaurant_record = resp.get('Item')
        if not restaurant_record:
            return {'statusCode': 404, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Restaurant not found'})}

    try:
        body = json.loads(event.get('body', '{}'))
    except Exception:
        body = {}

    file_name = str(body.get('file_name') or 'upload.jpg').strip()
    content_type = str(body.get('content_type') or '').strip().lower()
    if not content_type.startswith('image/'):
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'content_type must be an image/* MIME type'})}

    existing_image_keys = []
    if isinstance(restaurant_record, dict):
        existing_image_keys = restaurant_record.get('restaurant_image_keys') or []
    if isinstance(existing_image_keys, list) and len(existing_image_keys) >= 5:
        return {'statusCode': 400, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'A maximum of 5 restaurant images is allowed'})}

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
        print(f"Failed to generate upload URL: {e}")
        return {'statusCode': 500, 'headers': CORS_HEADERS, 'body': json.dumps({'error': 'Failed to generate upload URL'})}

    return {
        'statusCode': 200,
        'headers': CORS_HEADERS,
        'body': json.dumps({
            'upload_url': upload_url,
            'object_key': object_key,
            'preview_url': _build_image_url(object_key),
            'expires_in_seconds': upload_ttl_seconds,
        }),
    }
