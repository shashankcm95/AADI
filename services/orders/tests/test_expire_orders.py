"""Tests for expire_orders Lambda handler (BL-010)."""
import time
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError
import pytest

import expire_orders as sut


def _make_table(
    query_pages=None,
    scan_pages=None,
    query_side_effects=None,
    update_side_effects=None,
):
    """Return a mock DynamoDB Table with configurable query/scan behavior."""
    table = MagicMock()
    if query_side_effects is not None:
        table.query.side_effect = query_side_effects
    elif query_pages is not None:
        table.query.side_effect = query_pages
    else:
        table.query.return_value = {'Items': []}

    if scan_pages is not None:
        table.scan.side_effect = scan_pages
    else:
        table.scan.return_value = {'Items': []}

    if update_side_effects:
        table.update_item.side_effect = update_side_effects
    return table


def _conditional_check_error():
    err = ClientError(
        {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'cond fail'}},
        'UpdateItem',
    )
    return err


def _other_client_error():
    return ClientError(
        {'Error': {'Code': 'ProvisionedThroughputExceededException', 'Message': 'throttle'}},
        'UpdateItem',
    )


def _missing_index_error():
    return ClientError(
        {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'index missing'}},
        'Query',
    )


def test_expires_pending_order(monkeypatch):
    """PENDING_NOT_SENT order with past expires_at is updated to EXPIRED."""
    now = int(time.time())
    item = {'order_id': 'o1', 'status': sut.STATUS_PENDING, 'expires_at': now - 60}
    table = _make_table(query_pages=[{'Items': [item]}, {'Items': []}])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    table.update_item.assert_called_once()
    table.scan.assert_not_called()
    call_kwargs = table.update_item.call_args.kwargs
    assert call_kwargs['ExpressionAttributeValues'][':exp'] == sut.STATUS_EXPIRED
    assert call_kwargs['ExpressionAttributeValues'][':cur'] == sut.STATUS_PENDING


def test_expires_waiting_order(monkeypatch):
    """WAITING_FOR_CAPACITY order with past expires_at is updated to EXPIRED."""
    now = int(time.time())
    item = {'order_id': 'o2', 'status': sut.STATUS_WAITING, 'expires_at': now - 10}
    table = _make_table(query_pages=[{'Items': []}, {'Items': [item]}])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    table.update_item.assert_called_once()
    call_kwargs = table.update_item.call_args.kwargs
    assert call_kwargs['ExpressionAttributeValues'][':exp'] == sut.STATUS_EXPIRED
    assert call_kwargs['ExpressionAttributeValues'][':cur'] == sut.STATUS_WAITING


def test_skips_non_expired_order(monkeypatch):
    """No matched rows in query path should not trigger update_item."""
    table = _make_table(query_pages=[{'Items': []}, {'Items': []}])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    table.update_item.assert_not_called()


def test_concurrent_update_skipped(monkeypatch):
    """ConditionalCheckFailedException on update_item is silently ignored (no error logged)."""
    now = int(time.time())
    item = {'order_id': 'o4', 'status': sut.STATUS_PENDING, 'expires_at': now - 5}
    table = _make_table(
        query_pages=[{'Items': [item]}, {'Items': []}],
        update_side_effects=[_conditional_check_error()],
    )

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb, \
         patch.object(sut.logger, 'error') as mock_error:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    table.update_item.assert_called_once()
    mock_error.assert_not_called()


def test_paginated_query(monkeypatch):
    """Query path paginates and expires all matched rows."""
    now = int(time.time())
    item_a = {'order_id': 'oa', 'status': sut.STATUS_PENDING, 'expires_at': now - 10}
    item_b = {'order_id': 'ob', 'status': sut.STATUS_WAITING, 'expires_at': now - 20}

    # Pending page 1 + page 2, then waiting page 1.
    page1 = {'Items': [item_a], 'LastEvaluatedKey': {'order_id': 'oa', 'status': sut.STATUS_PENDING, 'expires_at': now - 10}}
    page2 = {'Items': [item_b]}
    table = _make_table(query_pages=[page1, page2, {'Items': []}])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    assert table.query.call_count == 3
    assert table.update_item.call_count == 2
    updated_ids = {c.kwargs['Key']['order_id'] for c in table.update_item.call_args_list}
    assert updated_ids == {'oa', 'ob'}


def test_query_fallback_to_scan_when_index_missing(monkeypatch):
    """If expiry GSI is not ready yet, handler falls back to bounded scan path."""
    now = int(time.time())
    item = {'order_id': 'o1', 'status': sut.STATUS_PENDING, 'expires_at': now - 60}
    table = _make_table(
        query_side_effects=[_missing_index_error()],
        scan_pages=[{'Items': [item]}],
    )

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    monkeypatch.setattr(sut, 'EXPIRY_SCAN_FALLBACK_ENABLED', True)
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    table.query.assert_called_once()
    table.scan.assert_called_once()
    table.update_item.assert_called_once()


def test_query_missing_index_raises_when_fallback_disabled(monkeypatch):
    """Fallback is controlled by flag; disabled mode should fail fast."""
    table = _make_table(query_side_effects=[_missing_index_error()])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    monkeypatch.setattr(sut, 'EXPIRY_SCAN_FALLBACK_ENABLED', False)
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        with patch.object(sut.logger, 'error') as _:
            with pytest.raises(ClientError):
                sut.lambda_handler({}, None)

    table.query.assert_called_once()
    table.scan.assert_not_called()


def test_time_remaining_guard_stops_early(monkeypatch):
    """Lambda aborts query loop when remaining time drops below buffer."""
    now = int(time.time())
    items = [{'order_id': f'o{i}', 'status': sut.STATUS_PENDING, 'expires_at': now - 60} for i in range(5)]
    page1 = {'Items': items[:3], 'LastEvaluatedKey': {'order_id': 'o2', 'status': sut.STATUS_PENDING, 'expires_at': now - 60}}
    page2 = {'Items': items[3:]}
    table = _make_table(query_pages=[page1, page2, {'Items': []}])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')

    class FakeContext:
        _calls = 0
        def get_remaining_time_in_millis(self):
            self._calls += 1
            # First call: plenty of time; second call: almost out
            return 10000 if self._calls == 1 else 500

    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, FakeContext())

    assert table.query.call_count == 1
    assert table.update_item.call_count == 3


def test_item_cap_stops_early(monkeypatch):
    """Lambda stops after reaching MAX_ITEMS_PER_RUN in query path."""
    monkeypatch.setattr(sut, 'MAX_ITEMS_PER_RUN', 3)

    now = int(time.time())
    items = [{'order_id': f'o{i}', 'status': sut.STATUS_PENDING, 'expires_at': now - 60} for i in range(5)]
    page1 = {'Items': items[:4], 'LastEvaluatedKey': {'order_id': 'o3', 'status': sut.STATUS_PENDING, 'expires_at': now - 60}}
    page2 = {'Items': items[4:]}
    table = _make_table(query_pages=[page1, page2, {'Items': []}])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    assert table.query.call_count == 1
    assert table.update_item.call_count == 4
