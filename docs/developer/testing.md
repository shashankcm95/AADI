# Testing Guide

The Arrive platform has 467 tests across its four backend services. Every test runs without AWS credentials, without network access, and without any external dependencies. This document explains how to run the tests, how the mock infrastructure works, how to write new tests, and what patterns to follow.

## Running the Tests

Each service's test suite is self-contained and runs independently. Use `pytest` from the service directory.

**Orders Service (229 tests):**

```bash
cd services/orders
python3 -m pytest tests/ -v
```

**Restaurants Service (121 tests):**

```bash
cd services/restaurants
python3 -m pytest tests/ -v
```

**Users Service (41 tests):**

```bash
cd services/users
python3 -m pytest tests/ -v
```

**POS Integration Service (76 tests):**

```bash
cd services/pos-integration
python3 -m pytest tests/ -v
```

To run all services in sequence:

```bash
for svc in orders restaurants users pos-integration; do
  (cd services/$svc && python3 -m pytest tests/ -v)
done
```

You can also run a specific test file or test function:

```bash
cd services/orders
python3 -m pytest tests/test_engine.py -v
python3 -m pytest tests/test_engine.py::test_decide_vicinity_update_reserves_capacity -v
```

## The conftest.py Convention

Every service has a `conftest.py` at `services/<name>/tests/conftest.py` that performs three critical setup steps.

### Path Setup

The conftest adds the shared Lambda Layer and the service's `src/` directory to `sys.path`, simulating the runtime environment where the Layer is mounted at `/opt/python/` and the handler code is at `/var/task/`:

```python
import sys, os

# Shared layer first (simulates Lambda Layer)
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../shared/python')
))
# Service source code
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../src')
))
```

The order matters: the shared layer is inserted first so that `from shared.auth import get_user_claims` resolves correctly, and the service's `src/` is inserted after so that `import app` resolves to the service's own `app.py`.

### Module Collision Prevention

When running tests for multiple services in the same Python process (which can happen with certain IDE configurations or when running pytest from the repository root), module names like `app`, `db`, `models`, and `handlers` would collide between services. Each conftest clears these common module names from `sys.modules`:

```python
for module_name in ("app", "db", "engine", "models", "handlers"):
    sys.modules.pop(module_name, None)
```

The POS service has its own set of module names to clear:

```python
for module_name in ("app", "handlers", "auth", "pos_mapper", "utils"):
    sys.modules.pop(module_name, None)
```

This ensures that when Python imports `app` in the POS tests, it gets the POS `app.py` rather than a cached version from the Orders service.

### Test Fixtures

Each conftest defines pytest fixtures that provide mock database tables and helper functions for constructing test events. The most important fixture is `mock_db`, which creates in-memory table mocks and patches them into the service's module-level variables.

## The InMemoryTable Mock Pattern

The backbone of the test infrastructure is the `InMemoryTable` class. This is a pure-Python mock that emulates the subset of the DynamoDB Table API that the application actually uses. It stores items in a plain dictionary and implements `get_item`, `put_item`, `update_item`, `query`, and `scan` with enough fidelity to test the handlers without a real database.

Here is a simplified version of the pattern:

```python
class InMemoryTable:
    def __init__(self, key_name='order_id'):
        self.items = {}
        self.key_name = key_name
        self.meta = MagicMock()
        self.meta.client.exceptions.ConditionalCheckFailedException = \
            ConditionalCheckFailedException

    def put_item(self, Item, ConditionExpression=None, **kwargs):
        key = Item[self.key_name]
        if ConditionExpression and key in self.items:
            raise ConditionalCheckFailedException("Condition failed")
        self.items[key] = dict(Item)

    def get_item(self, Key):
        key = Key[self.key_name]
        item = self.items.get(key)
        return {'Item': dict(item)} if item else {}

    def update_item(self, Key, UpdateExpression,
                    ConditionExpression=None,
                    ExpressionAttributeValues=None, **kwargs):
        key = Key[self.key_name]
        item = self.items.get(key, dict(Key))
        # Parse and apply SET expressions...
        self.items[key] = item
```

The mock implements enough of DynamoDB's conditional expression behavior to test idempotency guards, status transition conditions, and capacity atomic counters. It does not implement the full DynamoDB expression language; only the specific patterns used by the application code.

The `ConditionalCheckFailedException` is defined as a local exception class in the conftest and wired into the mock table's `meta.client.exceptions` attribute. This matches how `boto3` exposes the exception at runtime:

```python
class ConditionalCheckFailedException(Exception):
    pass

table.meta.client.exceptions.ConditionalCheckFailedException = \
    ConditionalCheckFailedException
```

### Fixture Wiring

The `mock_db` fixture creates table instances and patches them into the service's database module. Here is the pattern from the Orders service:

```python
@pytest.fixture
def mock_db():
    orders = InMemoryTable('order_id')
    capacity = InMemoryCapacityTable()
    config = InMemoryTable('restaurant_id')
    idempotency = InMemoryTable('idempotency_key')

    # Patch module-level table references
    original_orders = db.orders_table
    db.orders_table = orders
    db.capacity_table = capacity
    db.config_table = config
    db.idempotency_table = idempotency

    yield {
        'orders': orders,
        'capacity': capacity,
        'config': config,
        'idempotency': idempotency,
    }

    # Restore originals
    db.orders_table = original_orders
    # ... restore others
```

The fixture yields the mock tables so that tests can pre-populate data and inspect state after handler execution. The cleanup phase restores the original module-level references to avoid test pollution.

## Writing a New Test

To add a new test, follow this pattern:

### 1. Choose the Right Test File

Tests are organized by handler or feature. Engine logic tests go in `test_engine.py`, customer handler integration tests go in `test_customer.py`, and so on. If your test covers a new feature, create a new test file in the service's `tests/` directory.

### 2. Construct the API Gateway Event

Handler tests invoke the `lambda_handler` function directly with a synthetic API Gateway event. The event must include the route key, path parameters, headers, body, and (for authenticated routes) JWT claims:

```python
def make_event(route_key, body=None, path_params=None,
               role='customer', customer_id='cust_123',
               restaurant_id=None):
    claims = {
        'sub': customer_id,
        'custom:role': role,
        'email': 'test@example.com',
    }
    if restaurant_id:
        claims['custom:restaurant_id'] = restaurant_id

    return {
        'routeKey': route_key,
        'pathParameters': path_params or {},
        'headers': {'origin': 'http://localhost:5173'},
        'body': json.dumps(body) if body else None,
        'requestContext': {
            'requestId': 'test-correlation-id',
            'authorizer': {
                'jwt': {'claims': claims}
            }
        },
    }
```

The `requestContext.authorizer.jwt.claims` path is where API Gateway places the decoded JWT claims. The test constructs this manually to simulate different user roles and identities.

### 3. Set Up Test Data

Use the `mock_db` fixture to pre-populate tables with the state needed for your test:

```python
def test_get_order_returns_existing(mock_db):
    mock_db['orders'].items['ord_001'] = {
        'order_id': 'ord_001',
        'customer_id': 'cust_123',
        'restaurant_id': 'rest_abc',
        'status': 'SENT_TO_DESTINATION',
        'items': [],
        'total_cents': 0,
        'created_at': 1700000000,
        'expires_at': 1700003600,
    }

    event = make_event('GET /v1/orders/{order_id}',
                       path_params={'order_id': 'ord_001'})
    response = app.lambda_handler(event, None)

    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['order_id'] == 'ord_001'
    assert body['status'] == 'SENT_TO_DESTINATION'
```

### 4. Assert on Responses and Side Effects

Tests should assert on both the HTTP response and any side effects in the mock tables:

```python
def test_cancel_order_releases_capacity(mock_db):
    # Pre-populate an order with a capacity reservation
    mock_db['orders'].items['ord_001'] = {
        'order_id': 'ord_001',
        'customer_id': 'cust_123',
        'status': 'PENDING_NOT_SENT',
        'capacity_window_start': 1700000000,
        'restaurant_id': 'rest_abc',
        # ... other required fields
    }

    event = make_event('POST /v1/orders/{order_id}/cancel',
                       path_params={'order_id': 'ord_001'})
    response = app.lambda_handler(event, None)

    assert response['statusCode'] == 200
    # Verify the order is now canceled in the mock table
    assert mock_db['orders'].items['ord_001']['status'] == 'CANCELED'
```

### 5. Test Error Cases

Always test authorization failures, validation errors, and state conflicts:

```python
def test_cancel_sent_order_returns_409(mock_db):
    mock_db['orders'].items['ord_001'] = {
        'order_id': 'ord_001',
        'customer_id': 'cust_123',
        'status': 'SENT_TO_DESTINATION',
        # ...
    }

    event = make_event('POST /v1/orders/{order_id}/cancel',
                       path_params={'order_id': 'ord_001'})
    response = app.lambda_handler(event, None)

    assert response['statusCode'] == 409
```

## Testing the Engine

The dispatch engine (`engine.py`) is tested separately from the handlers because it has no I/O dependencies. Engine tests pass plain dictionaries and assert on the returned `UpdatePlan`:

```python
from engine import decide_vicinity_update
from models import STATUS_PENDING, STATUS_SENT

def test_vicinity_dispatches_when_capacity_available():
    session = {
        'order_id': 'ord_001',
        'status': STATUS_PENDING,
    }

    plan = decide_vicinity_update(
        session=session,
        vicinity=True,
        now=1700000000,
        window_seconds=300,
        window_start=1700000000,
        reserved_capacity=True,
    )

    assert plan.set_fields['status'] == STATUS_SENT
    assert plan.set_fields['vicinity'] is True
    assert plan.response['status'] == STATUS_SENT
```

Engine tests are fast (no mock setup), focused (one decision per test), and easy to reason about. They form the core of the test pyramid.

## The POS Module Collision Fix

The POS integration service has a specific challenge: its `auth.py` module name collides with the shared layer's `shared/auth.py`. When running POS tests after other services in the same Python process, the `auth` module reference could be stale.

The POS conftest addresses this by clearing `sys.modules` for the POS-specific module names before importing the service modules:

```python
for module_name in ("app", "handlers", "auth", "pos_mapper", "utils"):
    sys.modules.pop(module_name, None)

import app
import handlers
```

This ensures fresh imports of the POS service's own `auth.py` (which handles API key validation) rather than reusing a cached import of the shared `auth.py` (which handles JWT claims).

If you create a new service with module names that could collide with other services, follow this same pattern in your conftest.

## Integration Test Patterns

Most tests exercise the full handler chain: they call `app.lambda_handler(event, context)` and assert on the HTTP response. This tests routing, authorization, business logic, and serialization in a single pass. These are integration tests in the sense that they exercise multiple modules together, but they remain fast because all I/O is mocked.

The full-chain pattern is preferred over unit-testing individual handler functions in isolation, because it catches bugs in the router's authorization logic and route matching that unit tests would miss.

For the POS service, tests use a `mock_auth` fixture that creates events with the `X-POS-API-Key` header and patches the key validation to return a known key record:

```python
@pytest.fixture
def mock_auth():
    def _create_event(route_key, body=None, api_key='valid-key',
                      path_params=None, query_params=None):
        return {
            'routeKey': route_key,
            'headers': {'X-POS-API-Key': api_key},
            'body': json.dumps(body) if body else None,
            'pathParameters': path_params,
            'queryStringParameters': query_params,
        }
    return _create_event
```

## What CI Runs

The continuous integration pipeline runs the backend test suite for all four services. The CI configuration runs `python3 -m pytest tests/ -v` for each service directory, with environment variables stubbed to prevent boto3 from attempting real AWS connections during module-level initialization.

CI also runs `ruff` for Python linting and the frontend build/test/lint commands via Turborepo. A `detect-secrets` audit scans the codebase for accidentally committed credentials.

## Common Pitfalls

**Forgetting to mock the event's `requestContext`.** If you construct a test event without `requestContext.authorizer.jwt.claims`, the `get_user_claims` function returns an empty dict and the router rejects the request with a 401. Always include the claims in your test events.

**Testing against the wrong status string.** Order statuses are defined in `models.py` as `OrderStatus` enum members (e.g., `OrderStatus.PENDING_NOT_SENT` has the value `"PENDING_NOT_SENT"`). Use the module-level aliases (`STATUS_PENDING`, `STATUS_SENT`, etc.) to avoid typos.

**Not restoring mocked module variables.** If a test patches module-level variables (like `db.orders_table`) without restoring them, subsequent tests in the same session will use the patched values. Always use pytest fixtures with yield and cleanup, or use `unittest.mock.patch` as a context manager.

**Running all services from the repository root.** While the module collision prevention in conftest handles most cases, running `pytest` from the repo root can still cause import order issues. Prefer running each service's tests from its own directory.
