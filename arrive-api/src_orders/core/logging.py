import json
from typing import Any, Dict

from decimal import Decimal


def json_default(o):
    if isinstance(o, Decimal):
        return int(o) if o % 1 == 0 else float(o)
    return str(o)


def log(event: str, ts: int, **fields):
    payload: Dict[str, Any] = {"event": event, "ts": ts}
    payload.update(fields)
    print(json.dumps(payload, default=json_default))

