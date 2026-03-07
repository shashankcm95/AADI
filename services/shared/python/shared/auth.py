"""
Authentication utilities — single source of truth.

Extracts Cognito JWT claims into a normalized dict.
Not used by POS integration (which uses API key auth).

Supports both HTTP API v2 (``requestContext.authorizer.jwt.claims``)
and REST API v1 (``requestContext.authorizer.claims``) event formats.
"""

from typing import Any, Dict, Optional


def get_raw_claims(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract raw JWT claims from an API Gateway event (HTTP API v2 or REST v1).

    Returns the raw claims dict for accessing arbitrary claim fields
    (``given_name``, ``family_name``, ``email``, etc.).
    For normalized role/restaurant_id access, prefer ``get_user_claims()``.
    """
    try:
        return event['requestContext']['authorizer']['jwt']['claims']
    except (KeyError, TypeError):
        try:
            return event['requestContext']['authorizer']['claims']
        except (KeyError, TypeError):
            return {}


def get_user_claims(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract user claims from an API Gateway event with Cognito JWT authorizer.

    Returns a dict with:
        role            – custom:role or 'customer' fallback for legacy users
        restaurant_id   – custom:restaurant_id (restaurant_admin users)
        customer_id     – sub claim (all authenticated users)
        user_id         – alias for customer_id (backward compat)
        username        – cognito:username
        email           – email claim
    """
    claims = get_raw_claims(event)
    if not claims:
        return {}

    role = claims.get('custom:role') or claims.get('role')
    restaurant_id = claims.get('custom:restaurant_id') or claims.get('restaurant_id')
    customer_id = claims.get('sub')

    # Legacy/federated users may not carry custom role attributes.
    if not role and customer_id and not restaurant_id:
        role = 'customer'

    return {
        'role': role,
        'restaurant_id': restaurant_id,
        'customer_id': customer_id,
        'user_id': customer_id,
        'username': claims.get('cognito:username') or claims.get('username'),
        'email': claims.get('email'),
    }


# ---------------------------------------------------------------------------
# Convenience helpers — thin wrappers over get_raw_claims()
# ---------------------------------------------------------------------------


def get_user_role(event: Dict[str, Any], default: str = "") -> str:
    """Return normalized role from claims.

    Defaults to empty string for fail-closed authorization handling.
    """
    claims = get_raw_claims(event)
    return claims.get('custom:role') or claims.get('role') or default


def get_customer_id(event: Dict[str, Any]) -> Optional[str]:
    """Extract customer ID (``sub`` claim) from the event."""
    claims = get_raw_claims(event)
    return claims.get('sub')


def get_restaurant_id(event: Dict[str, Any]) -> Optional[str]:
    """Return the restaurant_id bound to a restaurant_admin account, if present."""
    claims = get_raw_claims(event)
    return claims.get('custom:restaurant_id') or claims.get('restaurant_id')
