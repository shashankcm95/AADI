import pytest
import post_confirmation

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
