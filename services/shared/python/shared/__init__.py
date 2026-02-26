"""
Arrive Shared Lambda Layer

Canonical implementations of cross-cutting concerns shared by all services.
Deployed as an AWS Lambda Layer; available at `from shared import ...`.
"""

from shared.cors import get_cors_origin, cors_headers, CORS_HEADERS
from shared.auth import get_user_claims
from shared.serialization import decimal_default, make_response
from shared.logger import (
    get_logger,
    extract_correlation_id,
    StructuredLogger,
    JSONFormatter,
    Timer,
)

__all__ = [
    # CORS
    "get_cors_origin",
    "cors_headers",
    "CORS_HEADERS",
    # Auth
    "get_user_claims",
    # Serialization
    "decimal_default",
    "make_response",
    # Logger
    "get_logger",
    "extract_correlation_id",
    "StructuredLogger",
    "JSONFormatter",
    "Timer",
]
