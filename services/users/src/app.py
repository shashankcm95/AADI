"""
Users Service – Lambda entry-point.

All business logic lives in ``handlers/users.py``.
This file is responsible only for:
  1. Extracting the route key
  2. Dispatching to the correct handler
"""
from handlers import users
from shared.serialization import make_response
from shared.logger import get_logger, extract_correlation_id

logger = get_logger("users.router")


def lambda_handler(event, context):
    route_key = event.get('routeKey')
    req_log = logger.bind(
        correlation_id=extract_correlation_id(event),
        route_key=route_key,
    )
    req_log.info("request_received")

    try:
        if route_key == 'GET /v1/users/health':
            return make_response(200, {'status': 'healthy', 'service': 'users'}, event)

        if route_key == 'GET /v1/users/me':
            return users.get_profile(event)

        if route_key == 'PUT /v1/users/me':
            return users.update_profile(event)

        if route_key == 'POST /v1/users/me/avatar/upload-url':
            return users.create_avatar_upload_url(event)

        return make_response(404, {'error': 'Not Found'}, event)

    except Exception as e:
        req_log.error("unhandled_exception", extra={"error_type": type(e).__name__, "detail": str(e)}, exc_info=True)
        return make_response(500, {'error': 'Internal server error'}, event)
