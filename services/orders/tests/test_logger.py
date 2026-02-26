import json
import logging
import time
import pytest
from io import StringIO

# conftest.py adds src/ to path
import shared.logger as logger

def test_json_formatter_structure():
    formatter = logger.JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Hello World",
        args=(),
        exc_info=None
    )
    # Inject context manually like the logger would
    record.correlation_id = "req-123"
    record.service = "test-service"
    record.custom_observability_field = "kept"
    
    formatted = formatter.format(record)
    data = json.loads(formatted)
    
    assert data["level"] == "INFO"
    assert data["logger"] == "test.logger"
    assert data["message"] == "Hello World"
    assert data["service"] == "test-service"
    assert data["correlation_id"] == "req-123"
    assert data["custom_observability_field"] == "kept"
    assert "timestamp" in data

def test_json_formatter_exception():
    formatter = logger.JSONFormatter()
    try:
        raise ValueError("Oops")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="t.py", lineno=1,
            msg="Error occurred", args=(), exc_info=sys.exc_info()
        )
        
    data = json.loads(formatter.format(record))
    assert "exception" in data
    assert "ValueError: Oops" in data["exception"]

def test_structured_logger_binding():
    # Setup capture
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logger.JSONFormatter())
    
    base_logger = logging.getLogger("test_bind")
    base_logger.addHandler(handler)
    base_logger.setLevel(logging.INFO)
    
    # 1. Base context
    log = logger.StructuredLogger(base_logger, {"service": "base"})
    log.info("msg 1")
    
    # 2. Bound context
    child_log = log.bind(order_id="123")
    child_log.info("msg 2")
    
    # 3. Request-specific
    child_log.info("msg 3", extra={"status_code": 200})
    
    lines = stream.getvalue().strip().split('\n')
    assert len(lines) == 3
    
    l1 = json.loads(lines[0])
    assert l1["message"] == "msg 1"
    assert l1["service"] == "base"
    assert "order_id" not in l1
    
    l2 = json.loads(lines[1])
    assert l2["message"] == "msg 2"
    assert l2["order_id"] == "123"
    
    l3 = json.loads(lines[2])
    assert l3["message"] == "msg 3"
    assert l3["order_id"] == "123"
    assert l3["status_code"] == 200

def test_timer_context():
    with logger.Timer() as t:
        time.sleep(0.01)
    
    assert t.elapsed_ms > 0
    assert isinstance(t.elapsed_ms, float)

def test_extract_correlation_id():
    # From params
    e1 = {"requestContext": {"requestId": "req-1"}}
    assert logger.extract_correlation_id(e1) == "req-1"
    
    # From headers
    e2 = {"headers": {"x-amzn-requestid": "req-2"}}
    assert logger.extract_correlation_id(e2) == "req-2"
    
    # Fallback
    assert logger.extract_correlation_id({}) == "no-correlation-id"
