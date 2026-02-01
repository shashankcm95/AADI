from dataclasses import dataclass
from typing import Dict

from core.errors import ExpiredError, InvalidStateError, NotFoundError


@dataclass(frozen=True)
class HttpErrorSpec:
    status_code: int
    body: Dict


def map_core_error(e: Exception) -> HttpErrorSpec:
    # Keep response shapes stable with your existing patterns
    if isinstance(e, NotFoundError):
        return HttpErrorSpec(404, {"error": {"code": "NOT_FOUND"}})

    if isinstance(e, InvalidStateError):
        return HttpErrorSpec(409, {"error": {"code": "INVALID_STATE"}})

    if isinstance(e, ExpiredError):
        return HttpErrorSpec(409, {"error": {"code": "EXPIRED"}})

    # fallback
    return HttpErrorSpec(500, {"error": {"code": "INTERNAL"}})

