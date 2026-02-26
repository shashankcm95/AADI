"""
Authentication utilities — single source of truth.

Extracts Cognito JWT claims into a normalized dict.
Not used by POS integration (which uses API key auth).
"""


def get_user_claims(event):
    """Extract user claims from an API Gateway event with Cognito JWT authorizer.

    Returns a dict with:
        role            – custom:role or 'customer' fallback for legacy users
        restaurant_id   – custom:restaurant_id (restaurant_admin users)
        customer_id     – sub claim (all authenticated users)
        user_id         – alias for customer_id (backward compat)
        username        – cognito:username
        email           – email claim
    """
    try:
        claims = event['requestContext']['authorizer']['jwt']['claims']
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
    except (KeyError, TypeError):
        return {}
