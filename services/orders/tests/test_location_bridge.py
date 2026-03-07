"""
Unit tests for location_bridge.py — Amazon Location bridge helpers.

Tests:
  - coerce_finite_float: valid, None, non-numeric, inf, NaN
  - coerce_epoch_seconds: seconds, milliseconds, None, negative, non-numeric, infinity
  - publish_device_position: no tracker, no client, empty device_id, success, API error, API rejected
  - tracker_enabled: various combinations
"""

import os
import sys
import math
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

import location_bridge


# =============================================================================
# coerce_finite_float
# =============================================================================

class TestCoerceFiniteFloat:
    def test_valid_float_string(self):
        assert location_bridge.coerce_finite_float("3.14") == pytest.approx(3.14)

    def test_integer(self):
        assert location_bridge.coerce_finite_float(42) == 42.0

    def test_none_returns_none(self):
        assert location_bridge.coerce_finite_float(None) is None

    def test_non_numeric_string_returns_none(self):
        assert location_bridge.coerce_finite_float("abc") is None

    def test_inf_returns_none(self):
        assert location_bridge.coerce_finite_float(float('inf')) is None

    def test_negative_inf_returns_none(self):
        assert location_bridge.coerce_finite_float(float('-inf')) is None

    def test_nan_returns_none(self):
        assert location_bridge.coerce_finite_float(float('nan')) is None

    def test_zero(self):
        assert location_bridge.coerce_finite_float(0) == 0.0

    def test_negative_float(self):
        assert location_bridge.coerce_finite_float(-97.7431) == pytest.approx(-97.7431)


# =============================================================================
# coerce_epoch_seconds
# =============================================================================

class TestCoerceEpochSeconds:
    def test_normal_epoch_seconds(self):
        assert location_bridge.coerce_epoch_seconds(1700000000, 0) == 1700000000

    def test_milliseconds_divided_by_1000(self):
        """Values > 10B are assumed to be milliseconds."""
        assert location_bridge.coerce_epoch_seconds(17000000000000, 0) == 17000000000

    def test_none_returns_fallback(self):
        assert location_bridge.coerce_epoch_seconds(None, 999) == 999

    def test_negative_returns_fallback(self):
        assert location_bridge.coerce_epoch_seconds(-100, 999) == 999

    def test_non_numeric_returns_fallback(self):
        assert location_bridge.coerce_epoch_seconds("abc", 999) == 999

    def test_infinity_returns_fallback(self):
        assert location_bridge.coerce_epoch_seconds(float('inf'), 999) == 999

    def test_nan_returns_fallback(self):
        assert location_bridge.coerce_epoch_seconds(float('nan'), 999) == 999

    def test_zero_returns_fallback(self):
        """Zero is not positive, so falls back."""
        assert location_bridge.coerce_epoch_seconds(0, 999) == 999

    def test_string_number(self):
        assert location_bridge.coerce_epoch_seconds("1700000000", 0) == 1700000000


# =============================================================================
# publish_device_position
# =============================================================================

class TestPublishDevicePosition:
    def test_no_tracker_name(self):
        """TRACKER_NAME empty → tracker_not_configured."""
        with patch.object(location_bridge, 'TRACKER_NAME', ''):
            result = location_bridge.publish_device_position(
                device_id='dev1', latitude=30.0, longitude=-97.0, sample_time_seconds=1700000000
            )
        assert result['published'] is False
        assert result['reason'] == 'tracker_not_configured'

    def test_no_location_client(self):
        """Client unavailable → location_client_unavailable."""
        with patch.object(location_bridge, 'TRACKER_NAME', 'my-tracker'), \
             patch.object(location_bridge, '_get_location_client', return_value=None):
            result = location_bridge.publish_device_position(
                device_id='dev1', latitude=30.0, longitude=-97.0, sample_time_seconds=1700000000
            )
        assert result['published'] is False
        assert result['reason'] == 'location_client_unavailable'

    def test_empty_device_id(self):
        """Empty device_id → missing_device_id."""
        mock_client = MagicMock()
        with patch.object(location_bridge, 'TRACKER_NAME', 'my-tracker'), \
             patch.object(location_bridge, '_get_location_client', return_value=mock_client):
            result = location_bridge.publish_device_position(
                device_id='', latitude=30.0, longitude=-97.0, sample_time_seconds=1700000000
            )
        assert result['published'] is False
        assert result['reason'] == 'missing_device_id'

    def test_successful_publish(self):
        """Successful batch_update_device_position → published True."""
        mock_client = MagicMock()
        mock_client.batch_update_device_position.return_value = {'Errors': []}
        with patch.object(location_bridge, 'TRACKER_NAME', 'my-tracker'), \
             patch.object(location_bridge, '_get_location_client', return_value=mock_client):
            result = location_bridge.publish_device_position(
                device_id='dev1', latitude=30.0, longitude=-97.0, sample_time_seconds=1700000000
            )
        assert result['published'] is True
        mock_client.batch_update_device_position.assert_called_once()

    def test_api_exception(self):
        """API exception → batch_update_failed."""
        mock_client = MagicMock()
        mock_client.batch_update_device_position.side_effect = Exception("Connection refused")
        with patch.object(location_bridge, 'TRACKER_NAME', 'my-tracker'), \
             patch.object(location_bridge, '_get_location_client', return_value=mock_client):
            result = location_bridge.publish_device_position(
                device_id='dev1', latitude=30.0, longitude=-97.0, sample_time_seconds=1700000000
            )
        assert result['published'] is False
        assert result['reason'] == 'batch_update_failed'

    def test_api_returns_errors(self):
        """API returns Errors array → batch_update_rejected."""
        mock_client = MagicMock()
        mock_client.batch_update_device_position.return_value = {
            'Errors': [{'Error': {'Message': 'Invalid position'}}]
        }
        with patch.object(location_bridge, 'TRACKER_NAME', 'my-tracker'), \
             patch.object(location_bridge, '_get_location_client', return_value=mock_client):
            result = location_bridge.publish_device_position(
                device_id='dev1', latitude=30.0, longitude=-97.0, sample_time_seconds=1700000000
            )
        assert result['published'] is False
        assert result['reason'] == 'batch_update_rejected'

    def test_position_properties_passed(self):
        """Position properties are correctly formatted and passed."""
        mock_client = MagicMock()
        mock_client.batch_update_device_position.return_value = {'Errors': []}
        with patch.object(location_bridge, 'TRACKER_NAME', 'my-tracker'), \
             patch.object(location_bridge, '_get_location_client', return_value=mock_client):
            result = location_bridge.publish_device_position(
                device_id='dev1', latitude=30.0, longitude=-97.0,
                sample_time_seconds=1700000000,
                position_properties={'order_id': 'ord_123', 'none_val': None}
            )
        assert result['published'] is True
        call_kwargs = mock_client.batch_update_device_position.call_args[1]
        update = call_kwargs['Updates'][0]
        # None values should be filtered out
        assert 'none_val' not in update['PositionProperties']
        assert update['PositionProperties']['order_id'] == 'ord_123'


# =============================================================================
# tracker_enabled
# =============================================================================

class TestTrackerEnabled:
    def test_tracker_name_set_and_client_available(self):
        mock_client = MagicMock()
        with patch.object(location_bridge, 'TRACKER_NAME', 'my-tracker'), \
             patch.object(location_bridge, '_get_location_client', return_value=mock_client):
            assert location_bridge.tracker_enabled() is True

    def test_tracker_name_empty(self):
        with patch.object(location_bridge, 'TRACKER_NAME', ''):
            assert location_bridge.tracker_enabled() is False

    def test_client_unavailable(self):
        with patch.object(location_bridge, 'TRACKER_NAME', 'my-tracker'), \
             patch.object(location_bridge, '_get_location_client', return_value=None):
            assert location_bridge.tracker_enabled() is False
