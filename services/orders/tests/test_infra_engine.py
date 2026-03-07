import sys
import os
import pytest
from unittest.mock import MagicMock

# Orders engine tests (relocated from infrastructure/tests/)
sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), '../src')
    )
)

import engine
from models import (
    STATUS_PENDING, STATUS_SENT, STATUS_WAITING, STATUS_IN_PROGRESS, 
    STATUS_READY
)



# --- decide_vicinity_update Tests ---

def test_vicinity_update_ignores_false():
    # If client says vicinity=False, do nothing
    session = {"status": STATUS_PENDING, "session_id": "123"}
    plan = engine.decide_vicinity_update(
        session, vicinity=False, now=100, window_seconds=60, window_start=1000, reserved_capacity=True
    )
    assert plan.response["status"] == STATUS_PENDING
    assert plan.set_fields is None

def test_vicinity_update_success_with_capacity():
    # If capacity is reserved, should move to SENT
    session = {"status": STATUS_PENDING, "session_id": "123"}
    now = 1000
    plan = engine.decide_vicinity_update(
        session, vicinity=True, now=now, window_seconds=60, window_start=2000, reserved_capacity=True
    )
    
    assert plan.set_fields["status"] == STATUS_SENT
    assert plan.set_fields["vicinity"] is True
    assert plan.set_fields["sent_at"] == now

def test_vicinity_update_blocked_no_capacity():
    # If no capacity, should move to WAITING
    session = {"status": STATUS_PENDING, "session_id": "123"}
    now = 1000
    plan = engine.decide_vicinity_update(
        session, vicinity=True, now=now, window_seconds=60, window_start=2000, reserved_capacity=False
    )
    
    assert plan.set_fields["status"] == STATUS_WAITING
    assert plan.set_fields["vicinity"] is True
    assert plan.set_fields["waiting_since"] == now
