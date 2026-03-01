"""
Tests for POS Integration auth.py module.
Uses mocking to avoid real DynamoDB calls.
"""
import sys
import os
import time
import pytest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

# Mock boto3 before importing auth to prevent real DynamoDB connection
with patch.dict(os.environ, {'POS_API_KEYS_TABLE': 'test-keys'}):
    with patch('boto3.resource') as mock_boto:
        mock_table = MagicMock()
        mock_boto.return_value.Table.return_value = mock_table
        import auth


# Replace the module-level keys_table with our mock
auth.keys_table = mock_table


class TestValidateKey:
    def setup_method(self):
        mock_table.reset_mock()
        mock_table.get_item.side_effect = None

    def test_valid_key(self):
        mock_table.get_item.return_value = {
            'Item': {
                'api_key': 'test-key-123',
                'restaurant_id': 'r1',
                'pos_system': 'toast',
                'permissions': ['orders:read', 'orders:write'],
                'created_at': 1000,
            }
        }
        result = auth.validate_key('test-key-123')

        assert result is not None
        assert result['api_key'] == 'test-key-123'
        assert result['restaurant_id'] == 'r1'
        assert result['pos_system'] == 'toast'
        assert 'orders:read' in result['permissions']

    def test_empty_key_returns_none(self):
        assert auth.validate_key('') is None
        assert auth.validate_key(None) is None

    def test_key_not_found(self):
        mock_table.get_item.return_value = {}
        assert auth.validate_key('nonexistent') is None

    def test_expired_key_returns_none(self):
        mock_table.get_item.return_value = {
            'Item': {
                'api_key': 'expired-key',
                'restaurant_id': 'r1',
                'ttl': int(time.time()) - 3600,  # expired 1 hour ago
            }
        }
        assert auth.validate_key('expired-key') is None

    def test_valid_ttl_returns_record(self):
        future_ttl = int(time.time()) + 3600
        mock_table.get_item.return_value = {
            'Item': {
                'api_key': 'valid-key',
                'restaurant_id': 'r1',
                'ttl': future_ttl,
            }
        }
        result = auth.validate_key('valid-key')
        assert result is not None
        assert result['restaurant_id'] == 'r1'

    def test_no_ttl_field_returns_record(self):
        """Keys without TTL should be valid forever."""
        mock_table.get_item.return_value = {
            'Item': {
                'api_key': 'no-ttl',
                'restaurant_id': 'r1',
            }
        }
        result = auth.validate_key('no-ttl')
        assert result is not None

    def test_default_permissions(self):
        """Missing 'permissions' field should default to [] (fail-closed — no access)."""
        mock_table.get_item.return_value = {
            'Item': {
                'api_key': 'k1',
                'restaurant_id': 'r1',
            }
        }
        result = auth.validate_key('k1')
        assert result['permissions'] == []

    def test_default_pos_system(self):
        """Missing 'pos_system' should default to 'generic'."""
        mock_table.get_item.return_value = {
            'Item': {
                'api_key': 'k1',
                'restaurant_id': 'r1',
            }
        }
        result = auth.validate_key('k1')
        assert result['pos_system'] == 'generic'

    def test_dynamo_exception_returns_none(self):
        mock_table.get_item.side_effect = Exception("Connection timeout")
        assert auth.validate_key('any-key') is None


class TestRequirePermission:
    def test_has_permission(self):
        record = {'permissions': ['orders:read', 'orders:write']}
        assert auth.require_permission(record, 'orders:read') is True

    def test_missing_permission(self):
        record = {'permissions': ['orders:read']}
        assert auth.require_permission(record, 'orders:write') is False

    def test_wildcard_permission(self):
        record = {'permissions': ['*']}
        assert auth.require_permission(record, 'anything:here') is True

    def test_empty_permissions(self):
        record = {'permissions': []}
        assert auth.require_permission(record, 'orders:read') is False

    def test_no_permissions_key(self):
        record = {}
        assert auth.require_permission(record, 'orders:read') is False


class TestAuthenticateRequest:
    def setup_method(self):
        mock_table.reset_mock()
        mock_table.get_item.side_effect = None

    def test_extracts_lowercase_header(self):
        mock_table.get_item.return_value = {
            'Item': {
                'api_key': 'my-key',
                'restaurant_id': 'r1',
            }
        }
        result = auth.authenticate_request({
            'headers': {'x-pos-api-key': 'my-key'}
        })
        assert result is not None
        assert result['restaurant_id'] == 'r1'

    def test_extracts_pascal_case_header(self):
        mock_table.get_item.return_value = {
            'Item': {
                'api_key': 'my-key',
                'restaurant_id': 'r1',
            }
        }
        result = auth.authenticate_request({
            'headers': {'X-POS-API-Key': 'my-key'}
        })
        assert result is not None

    def test_no_header_returns_none(self):
        assert auth.authenticate_request({'headers': {}}) is None

    def test_no_headers_key_returns_none(self):
        assert auth.authenticate_request({}) is None
