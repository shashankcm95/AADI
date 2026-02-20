"""
Unit tests for capacity.py — Domain-Agnostic Capacity Gating

Tests:
  - get_window_start: boundary math
  - try_reserve_slot: success + at-capacity (mocked DDB)
  - release_slot: success + already-zero (mocked DDB)
  - get_capacity_config: with config, without config, with defaults
  - check_and_reserve_for_arrival: end-to-end dining flow
"""

import pytest
from unittest.mock import MagicMock, patch

import capacity


# =============================================================================
# get_window_start
# =============================================================================

class TestGetWindowStart:
    def test_exact_boundary(self):
        assert capacity.get_window_start(900, 300) == 900

    def test_mid_window(self):
        assert capacity.get_window_start(1007, 300) == 900

    def test_just_before_next_boundary(self):
        assert capacity.get_window_start(1199, 300) == 900

    def test_next_boundary(self):
        assert capacity.get_window_start(1200, 300) == 1200

    def test_zero(self):
        assert capacity.get_window_start(0, 300) == 0

    def test_one_second_windows(self):
        assert capacity.get_window_start(42, 1) == 42

    def test_large_window(self):
        assert capacity.get_window_start(7200, 3600) == 7200
        assert capacity.get_window_start(7201, 3600) == 7200


# =============================================================================
# try_reserve_slot
# =============================================================================

class TestTryReserveSlot:
    def _mock_table(self, should_succeed=True):
        """Create a mock DynamoDB table with a real exception class."""
        table = MagicMock()

        # Create a real exception class so the except clause can match it
        class ConditionalCheckFailedException(Exception):
            pass

        table.meta.client.exceptions.ConditionalCheckFailedException = (
            ConditionalCheckFailedException
        )

        if should_succeed:
            table.update_item.return_value = {}
        else:
            table.update_item.side_effect = ConditionalCheckFailedException(
                "Conditional check failed"
            )
        return table

    def test_reserve_success(self):
        table = self._mock_table(should_succeed=True)
        result = capacity.try_reserve_slot(
            table=table,
            destination_id="rest_abc",
            window_start=900,
            max_concurrent=5,
        )
        assert result is True
        table.update_item.assert_called_once()

        # Verify the key structure
        call_kwargs = table.update_item.call_args[1]
        assert call_kwargs['Key']['restaurant_id'] == 'rest_abc'
        assert call_kwargs['Key']['window_start'] == 900

    def test_reserve_at_capacity(self):
        table = self._mock_table(should_succeed=False)
        result = capacity.try_reserve_slot(
            table=table,
            destination_id="rest_abc",
            window_start=900,
            max_concurrent=5,
        )
        assert result is False

    def test_ttl_is_set(self):
        table = self._mock_table(should_succeed=True)
        capacity.try_reserve_slot(
            table=table,
            destination_id="rest_abc",
            window_start=900,
            max_concurrent=5,
            window_seconds=300,
            ttl_padding=3600,
        )
        call_kwargs = table.update_item.call_args[1]
        # TTL = window_start + window_seconds + ttl_padding = 900 + 300 + 3600 = 4800
        assert call_kwargs['ExpressionAttributeValues'][':ttl'] == 4800
        assert call_kwargs['ExpressionAttributeNames']['#ttl'] == 'ttl'


# =============================================================================
# release_slot
# =============================================================================

class TestReleaseSlot:
    def test_release_success(self):
        table = MagicMock()
        table.update_item.return_value = {}
        capacity.release_slot(table, "rest_abc", 900)
        table.update_item.assert_called_once()

    def test_release_graceful_on_error(self):
        """Should not raise even if the row doesn't exist or count is 0."""
        table = MagicMock()
        table.update_item.side_effect = Exception("ConditionalCheckFailed")
        # Should NOT raise
        capacity.release_slot(table, "rest_abc", 900)


# =============================================================================
# get_capacity_config
# =============================================================================

class TestGetCapacityConfig:
    def test_returns_defaults_when_no_table(self):
        config = capacity.get_capacity_config(None, "rest_abc")
        assert config['max_concurrent_orders'] == capacity.DEFAULT_MAX_CONCURRENT
        assert config['capacity_window_seconds'] == capacity.DEFAULT_WINDOW_SECONDS

    def test_returns_config_from_table(self):
        table = MagicMock()
        table.get_item.return_value = {
            'Item': {
                'restaurant_id': 'rest_abc',
                'max_concurrent_orders': 3,
                'capacity_window_seconds': 600,
            }
        }
        config = capacity.get_capacity_config(table, "rest_abc")
        assert config['max_concurrent_orders'] == 3
        assert config['capacity_window_seconds'] == 600

    def test_returns_defaults_when_config_missing(self):
        table = MagicMock()
        table.get_item.return_value = {'Item': {'restaurant_id': 'rest_abc'}}
        config = capacity.get_capacity_config(table, "rest_abc")
        assert config['max_concurrent_orders'] == capacity.DEFAULT_MAX_CONCURRENT
        assert config['capacity_window_seconds'] == capacity.DEFAULT_WINDOW_SECONDS

    def test_returns_defaults_on_error(self):
        table = MagicMock()
        table.get_item.side_effect = Exception("Connection refused")
        config = capacity.get_capacity_config(table, "rest_abc")
        assert config['max_concurrent_orders'] == capacity.DEFAULT_MAX_CONCURRENT


# =============================================================================
# check_and_reserve_for_arrival (Dining Extension)
# =============================================================================

class TestCheckAndReserveForArrival:
    def test_full_flow_reserved(self):
        cap_table = MagicMock()
        cap_table.update_item.return_value = {}

        config_table = MagicMock()
        config_table.get_item.return_value = {
            'Item': {
                'restaurant_id': 'rest_abc',
                'max_concurrent_orders': 5,
                'capacity_window_seconds': 300,
            }
        }

        result = capacity.check_and_reserve_for_arrival(
            capacity_table=cap_table,
            config_table=config_table,
            destination_id="rest_abc",
            now=1007,
        )

        assert result['reserved'] is True
        assert result['window_start'] == 900
        assert result['window_seconds'] == 300
        assert result['max_concurrent'] == 5

    def test_full_flow_at_capacity(self):
        cap_table = MagicMock()

        # Create a real exception class for the mock
        class ConditionalCheckFailedException(Exception):
            pass

        cap_table.meta.client.exceptions.ConditionalCheckFailedException = (
            ConditionalCheckFailedException
        )
        cap_table.update_item.side_effect = ConditionalCheckFailedException(
            "At capacity"
        )

        config_table = MagicMock()
        config_table.get_item.return_value = {
            'Item': {
                'restaurant_id': 'rest_abc',
                'max_concurrent_orders': 2,
                'capacity_window_seconds': 300,
            }
        }

        result = capacity.check_and_reserve_for_arrival(
            capacity_table=cap_table,
            config_table=config_table,
            destination_id="rest_abc",
            now=1007,
        )

        assert result['reserved'] is False

    def test_defaults_when_no_config(self):
        cap_table = MagicMock()
        cap_table.update_item.return_value = {}

        result = capacity.check_and_reserve_for_arrival(
            capacity_table=cap_table,
            config_table=None,
            destination_id="rest_abc",
            now=1007,
        )

        assert result['reserved'] is True
        assert result['max_concurrent'] == capacity.DEFAULT_MAX_CONCURRENT
        assert result['window_seconds'] == capacity.DEFAULT_WINDOW_SECONDS


# =============================================================================
# leave advisory (non-reserving)
# =============================================================================

class TestLeaveAdvisory:
    def test_window_usage_defaults_to_zero(self):
        usage = capacity.get_window_usage(None, "rest_abc", 900)
        assert usage == 0

    def test_window_usage_reads_current_count(self):
        cap_table = MagicMock()
        cap_table.get_item.return_value = {'Item': {'current_count': 3}}
        usage = capacity.get_window_usage(cap_table, "rest_abc", 900)
        assert usage == 3

    def test_estimate_leave_now_when_capacity_available(self):
        cap_table = MagicMock()
        cap_table.get_item.return_value = {'Item': {'current_count': 1}}

        config_table = MagicMock()
        config_table.get_item.return_value = {
            'Item': {
                'restaurant_id': 'rest_abc',
                'max_concurrent_orders': 3,
                'capacity_window_seconds': 300,
            }
        }

        advisory = capacity.estimate_leave_advisory(
            capacity_table=cap_table,
            config_table=config_table,
            destination_id="rest_abc",
            now=1007,
        )

        assert advisory['recommended_action'] == 'LEAVE_NOW'
        assert advisory['estimated_wait_seconds'] == 0
        assert advisory['available_slots'] == 2
        assert advisory['is_estimate'] is True

    def test_estimate_wait_when_capacity_full(self):
        cap_table = MagicMock()
        cap_table.get_item.return_value = {'Item': {'current_count': 3}}

        config_table = MagicMock()
        config_table.get_item.return_value = {
            'Item': {
                'restaurant_id': 'rest_abc',
                'max_concurrent_orders': 3,
                'capacity_window_seconds': 300,
            }
        }

        advisory = capacity.estimate_leave_advisory(
            capacity_table=cap_table,
            config_table=config_table,
            destination_id="rest_abc",
            now=1007,
        )

        assert advisory['recommended_action'] == 'WAIT'
        assert advisory['estimated_wait_seconds'] > 0
        assert advisory['available_slots'] == 0
