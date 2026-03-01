"""Tests for expire_orders Lambda handler (BL-010)."""
import time
from unittest.mock import MagicMock, patch, call
from botocore.exceptions import ClientError

import expire_orders as sut


def _make_table(scan_pages, update_side_effects=None):
    """Return a mock DynamoDB Table with pre-configured scan pages."""
    table = MagicMock()
    table.scan.side_effect = scan_pages
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


def test_expires_pending_order(monkeypatch):
    """PENDING_NOT_SENT order with past expires_at is updated to EXPIRED."""
    now = int(time.time())
    item = {'order_id': 'o1', 'status': sut.STATUS_PENDING, 'expires_at': now - 60}
    table = _make_table([{'Items': [item]}])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    table.update_item.assert_called_once()
    call_kwargs = table.update_item.call_args.kwargs
    assert call_kwargs['ExpressionAttributeValues'][':exp'] == sut.STATUS_EXPIRED
    assert call_kwargs['ExpressionAttributeValues'][':cur'] == sut.STATUS_PENDING


def test_expires_waiting_order(monkeypatch):
    """WAITING_FOR_CAPACITY order with past expires_at is updated to EXPIRED."""
    now = int(time.time())
    item = {'order_id': 'o2', 'status': sut.STATUS_WAITING, 'expires_at': now - 10}
    table = _make_table([{'Items': [item]}])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    table.update_item.assert_called_once()
    call_kwargs = table.update_item.call_args.kwargs
    assert call_kwargs['ExpressionAttributeValues'][':exp'] == sut.STATUS_EXPIRED
    assert call_kwargs['ExpressionAttributeValues'][':cur'] == sut.STATUS_WAITING


def test_skips_non_expired_order(monkeypatch):
    """Orders with expires_at in the future should not trigger update_item."""
    # DynamoDB FilterExpression handles this server-side; simulate by returning no items.
    table = _make_table([{'Items': []}])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    table.update_item.assert_not_called()


def test_concurrent_update_skipped(monkeypatch):
    """ConditionalCheckFailedException on update_item is silently ignored (no error logged)."""
    now = int(time.time())
    item = {'order_id': 'o4', 'status': sut.STATUS_PENDING, 'expires_at': now - 5}
    table = _make_table([{'Items': [item]}], update_side_effects=[_conditional_check_error()])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb, \
         patch.object(sut.logger, 'error') as mock_error:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    # update_item was attempted
    table.update_item.assert_called_once()
    # error logger must NOT have been called for a conditional check failure
    mock_error.assert_not_called()


def test_paginated_scan(monkeypatch):
    """Scan spanning two pages processes all expired items on both pages."""
    now = int(time.time())
    item_a = {'order_id': 'oa', 'status': sut.STATUS_PENDING, 'expires_at': now - 10}
    item_b = {'order_id': 'ob', 'status': sut.STATUS_WAITING, 'expires_at': now - 20}

    page1 = {'Items': [item_a], 'LastEvaluatedKey': {'order_id': 'oa'}}
    page2 = {'Items': [item_b]}
    table = _make_table([page1, page2])

    monkeypatch.setattr(sut, 'ORDERS_TABLE', 'orders-table')
    with patch.object(sut, '_dynamodb') as mock_ddb:
        mock_ddb.Table.return_value = table
        sut.lambda_handler({}, None)

    assert table.scan.call_count == 2
    assert table.update_item.call_count == 2
    updated_ids = {c.kwargs['Key']['order_id'] for c in table.update_item.call_args_list}
    assert updated_ids == {'oa', 'ob'}
