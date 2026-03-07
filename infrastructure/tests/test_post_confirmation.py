import sys
import pytest
import post_confirmation
from conftest import InMemoryTable

def test_post_confirmation_success(monkeypatch):
    """Should set role to 'customer' if not present."""
    # Setup
    event = {
        'userPoolId': 'pool-1',
        'userName': 'new-user',
        'request': {
            'userAttributes': {}
        }
    }
    
    # Capture calls
    calls = []
    
    class MockClient:
        def admin_update_user_attributes(self, **kwargs):
            calls.append(kwargs)
            
    monkeypatch.setattr(post_confirmation, 'cognito', MockClient())
    
    # Execute
    result = post_confirmation.lambda_handler(event, {})
    
    # Verify
    assert result == event
    assert len(calls) == 1
    assert calls[0]['Username'] == 'new-user'
    assert calls[0]['UserAttributes'][0]['Name'] == 'custom:role'
    assert calls[0]['UserAttributes'][0]['Value'] == 'customer'

def test_post_confirmation_idempotent(monkeypatch):
    """Should do nothing if role is already set."""
    event = {
        'userPoolId': 'pool-1',
        'userName': 'admin-user',
        'request': {
            'userAttributes': {
                'custom:role': 'admin'
            }
        }
    }
    
    calls = []
    class MockClient:
        def admin_update_user_attributes(self, **kwargs):
            calls.append(kwargs)
            
    monkeypatch.setattr(post_confirmation, 'cognito', MockClient())
    
    result = post_confirmation.lambda_handler(event, {})
    
    assert result == event
    assert len(calls) == 0  # No API call made

def test_post_confirmation_error_handling(monkeypatch):
    """Should swallow errors (log them) and return event to avoid blocking signup."""
    event = {
        'userPoolId': 'pool-1',
        'userName': 'error-user',
        'request': {'userAttributes': {}}
    }
    
    class MockClient:
        def admin_update_user_attributes(self, **kwargs):
            raise Exception("Cognito is down")
            
    monkeypatch.setattr(post_confirmation, 'cognito', MockClient())
    
    # Should not raise exception
    result = post_confirmation.lambda_handler(event, {})
    assert result == event


# --- DynamoDB profile creation tests ---


def _reload_post_confirmation(monkeypatch, users_table_value):
    """Force reimport of post_confirmation with USERS_TABLE env var set."""
    if users_table_value:
        monkeypatch.setenv('USERS_TABLE', users_table_value)
    else:
        monkeypatch.delenv('USERS_TABLE', raising=False)
    if 'post_confirmation' in sys.modules:
        del sys.modules['post_confirmation']
    import post_confirmation as mod
    return mod


def test_dynamodb_profile_created(monkeypatch):
    """DynamoDB profile should be created for new user when USERS_TABLE is set."""
    mod = _reload_post_confirmation(monkeypatch, 'test-users-table')

    mock_table = InMemoryTable()

    class MockCognito:
        def admin_update_user_attributes(self, **kwargs):
            pass

    monkeypatch.setattr(mod, 'cognito', MockCognito())
    monkeypatch.setattr(mod, '_users_table', mock_table)

    event = {
        'userPoolId': 'pool-1',
        'userName': 'new-user',
        'request': {
            'userAttributes': {
                'sub': 'user-abc-123',
                'email': 'test@example.com',
                'name': 'Test User',
                'phone_number': '+1234567890',
            }
        }
    }

    result = mod.lambda_handler(event, {})
    assert result == event
    assert 'user-abc-123' in mock_table.items
    item = mock_table.items['user-abc-123']
    assert item['email'] == 'test@example.com'
    assert item['role'] == 'customer'
    assert 'created_at' in item
    assert 'created_at_iso' in item


def test_dynamodb_idempotent_no_overwrite(monkeypatch):
    """Should not overwrite existing profile (ConditionalCheckFailedException)."""
    mod = _reload_post_confirmation(monkeypatch, 'test-users-table')

    mock_table = InMemoryTable()
    mock_table.items['user-abc-123'] = {
        'user_id': 'user-abc-123',
        'email': 'original@example.com',
        'role': 'admin',
    }

    class MockCognito:
        def admin_update_user_attributes(self, **kwargs):
            pass

    monkeypatch.setattr(mod, 'cognito', MockCognito())
    monkeypatch.setattr(mod, '_users_table', mock_table)

    event = {
        'userPoolId': 'pool-1',
        'userName': 'admin-user',
        'request': {
            'userAttributes': {
                'sub': 'user-abc-123',
                'email': 'new@example.com',
                'custom:role': 'admin',
            }
        }
    }

    result = mod.lambda_handler(event, {})
    assert result == event
    # Original should be preserved
    assert mock_table.items['user-abc-123']['email'] == 'original@example.com'


def test_dynamodb_skipped_when_no_table(monkeypatch):
    """Should skip DynamoDB write gracefully when _users_table is None."""
    mod = _reload_post_confirmation(monkeypatch, None)

    class MockCognito:
        def admin_update_user_attributes(self, **kwargs):
            pass

    monkeypatch.setattr(mod, 'cognito', MockCognito())
    monkeypatch.setattr(mod, '_users_table', None)

    event = {
        'userPoolId': 'pool-1',
        'userName': 'user',
        'request': {
            'userAttributes': {'sub': 'user-1'}
        }
    }

    result = mod.lambda_handler(event, {})
    assert result == event


def test_datetime_uses_utc_timezone(monkeypatch):
    """Verify the ISO timestamp uses timezone-aware UTC."""
    mod = _reload_post_confirmation(monkeypatch, 'test-users-table')

    mock_table = InMemoryTable()

    class MockCognito:
        def admin_update_user_attributes(self, **kwargs):
            pass

    monkeypatch.setattr(mod, 'cognito', MockCognito())
    monkeypatch.setattr(mod, '_users_table', mock_table)

    event = {
        'userPoolId': 'pool-1',
        'userName': 'tz-user',
        'request': {
            'userAttributes': {
                'sub': 'user-tz-1',
                'email': 'tz@test.com',
            }
        }
    }

    mod.lambda_handler(event, {})
    iso = mock_table.items['user-tz-1']['created_at_iso']
    # datetime.now(timezone.utc).isoformat() produces '+00:00'
    assert '+00:00' in iso
