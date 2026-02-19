import json
import logging
from handlers import users

# Setup logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Main entry point for Users Service.
    Routing logic.
    """
    http_method = event.get('requestContext', {}).get('http', {}).get('method')
    path = event.get('requestContext', {}).get('http', {}).get('path')
    request_id = event.get('requestContext', {}).get('requestId')
    logger.info("Users request received", extra={"method": http_method, "path": path, "request_id": request_id})
    
    # Enable CORS for OPTIONS
    if http_method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Authorization,Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS'
            },
            'body': ''
        }
        
    try:
        if path == '/v1/users/health' and http_method == 'GET':
            return {
                'statusCode': 200,
                'body': json.dumps({'status': 'healthy', 'service': 'users'})
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
            'body': json.dumps({'error': 'Not Found'})
        }

    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal Server Error'})
        }
