"""
CORS utilities — single source of truth.

All services read CORS_ALLOW_ORIGIN / CORS_ALLOW_ORIGIN_ADMIN from env vars
and localhost fallbacks. `cors_headers(event)` dynamically matches the
requesting origin; `CORS_HEADERS` is a static fallback for code that
doesn't have access to the event.
"""

import os

_CORS_ALLOW_ORIGINS = [
    o.strip() for o in [
        os.environ.get('CORS_ALLOW_ORIGIN', ''),
        os.environ.get('CORS_ALLOW_ORIGIN_ADMIN', ''),
        'http://localhost:5173',
        'http://localhost:5174',
    ] if o.strip()
]

_DEFAULT_CORS_HEADERS = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Headers': 'Authorization,Content-Type,Idempotency-Key',
}


def get_cors_origin(event=None):
    """Return the matching allowed origin for the request, or the first configured origin."""
    origin = ''
    try:
        origin = (event or {}).get('headers', {}).get('origin', '') or ''
    except (AttributeError, TypeError):
        pass
    if origin and origin in _CORS_ALLOW_ORIGINS:
        return origin
    return _CORS_ALLOW_ORIGINS[0] if _CORS_ALLOW_ORIGINS else '*'


def cors_headers(event=None):
    """Build CORS headers with the correct Access-Control-Allow-Origin for this request."""
    headers = dict(_DEFAULT_CORS_HEADERS)
    headers['Access-Control-Allow-Origin'] = get_cors_origin(event)
    return headers


# Backward-compatible static reference (used by code that doesn't have the event)
CORS_HEADERS = dict(_DEFAULT_CORS_HEADERS)
CORS_HEADERS['Access-Control-Allow-Origin'] = _CORS_ALLOW_ORIGINS[0] if _CORS_ALLOW_ORIGINS else '*'
