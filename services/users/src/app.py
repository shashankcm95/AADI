import json
import os
from handlers import users
from shared.cors import cors_headers
from shared.logger import get_logger

logger = get_logger("users.router")


def lambda_handler(event, context):
    """
    Main entry point for Users Service.
    Routing logic.
    """
    http_method = event.get('requestContext', {}).get('http', {}).get('method')
    path = event.get('requestContext', {}).get('http', {}).get('path')
    request_id = event.get('requestContext', {}).get('requestId')
    logger.info("Users request received", extra={"method": http_method, "path": path, "request_id": request_id})

    headers = cors_headers(event)

    # Enable CORS for OPTIONS — use configured allow-list, not wildcard
    if http_method == 'OPTIONS':
        headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return {
            'statusCode': 200,
            'headers': headers,
            'body': '',
        }

    try:
        if path == '/v1/users/health' and http_method == 'GET':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({'status': 'healthy', 'service': 'users'}),
            }

        if path == '/v1/users/me':
            if http_method == 'GET':
                return users.get_profile(event)
            elif http_method == 'PUT':
                return users.update_profile(event)

        if path == '/v1/users/me/avatar/upload-url' and http_method == 'POST':
            return users.create_avatar_upload_url(event)

        return {
            'statusCode': 404,
            'headers': headers,
            'body': json.dumps({'error': 'Not Found'}),
        }

    except Exception as e:
        logger.error("Unhandled exception", extra={"error": str(e)}, exc_info=True)
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'Internal Server Error'}),
        }
