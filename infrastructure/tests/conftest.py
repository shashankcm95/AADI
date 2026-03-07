import sys
import os
import pytest

# Add src to path
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src'))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


class InMemoryTable:
    """Minimal DynamoDB Table mock following the pattern in services/restaurants/tests/conftest.py."""

    def __init__(self, key_name='user_id'):
        self.items = {}
        self.key_name = key_name

    def put_item(self, Item, ConditionExpression=None, **kwargs):
        key = Item[self.key_name]
        if ConditionExpression and key in self.items:
            from botocore.exceptions import ClientError
            raise ClientError(
                {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'Condition not met'}},
                'PutItem'
            )
        self.items[key] = dict(Item)

    def get_item(self, Key):
        key = Key[self.key_name]
        item = self.items.get(key)
        if item:
            return {'Item': dict(item)}
        return {}

    @property
    def meta(self):
        return self

    @property
    def client(self):
        return self

    @property
    def exceptions(self):
        return self

    @property
    def ConditionalCheckFailedException(self):
        from botocore.exceptions import ClientError
        return ClientError


class MockDynamoDBResource:
    def __init__(self):
        self._tables = {}

    def Table(self, name):
        if name not in self._tables:
            self._tables[name] = InMemoryTable()
        return self._tables[name]

    @property
    def meta(self):
        return self

    @property
    def client(self):
        return self

    @property
    def exceptions(self):
        return self

    @property
    def ConditionalCheckFailedException(self):
        from botocore.exceptions import ClientError
        return ClientError


class MockCognitoClient:
    def __init__(self):
        self.calls = []

    def admin_update_user_attributes(self, **kwargs):
        self.calls.append(kwargs)


@pytest.fixture(autouse=True)
def mock_boto3(monkeypatch):
    """Mock both boto3.client and boto3.resource to prevent real AWS calls."""
    mock_cognito = MockCognitoClient()
    mock_dynamodb = MockDynamoDBResource()

    def mock_client(service_name, *args, **kwargs):
        if service_name == 'cognito-idp':
            return mock_cognito
        raise ValueError(f"Unexpected service: {service_name}")

    def mock_resource(service_name, *args, **kwargs):
        if service_name == 'dynamodb':
            return mock_dynamodb
        raise ValueError(f"Unexpected resource: {service_name}")

    monkeypatch.setattr("boto3.client", mock_client)
    monkeypatch.setattr("boto3.resource", mock_resource)
