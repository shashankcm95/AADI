import sys
import os
import pytest

# Add src to path
_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src'))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

@pytest.fixture(autouse=True)
def mock_boto3(monkeypatch):
    """
    Mock boto3 at module level to prevent import side effects.
    This fixture runs automatically for all tests in this directory.
    """
    # Create a mock client
    class MockCognitoClient:
        def admin_update_user_attributes(self, **kwargs):
            pass

    # Mock boto3.client factory
    def mock_client(service_name, *args, **kwargs):
        if service_name == 'cognito-idp':
            return MockCognitoClient()
        raise ValueError(f"Unexpected service: {service_name}")

    monkeypatch.setattr("boto3.client", mock_client)
