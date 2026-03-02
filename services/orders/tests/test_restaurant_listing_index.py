from unittest.mock import MagicMock

import db
from handlers.restaurant import list_restaurant_orders


def test_list_restaurant_orders_uses_recency_index_without_status():
    original_table = db.orders_table
    try:
        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        db.orders_table = mock_table

        event = {'queryStringParameters': {'limit': '10'}}
        response = list_restaurant_orders('rest_1', event)

        assert response['statusCode'] == 200
        query_kwargs = mock_table.query.call_args.kwargs
        assert query_kwargs['IndexName'] == 'GSI_RestaurantCreated'
        assert query_kwargs['ScanIndexForward'] is False
    finally:
        db.orders_table = original_table


def test_list_restaurant_orders_uses_status_index_when_filtered():
    original_table = db.orders_table
    try:
        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}
        db.orders_table = mock_table

        event = {'queryStringParameters': {'status': 'IN_PROGRESS', 'limit': '10'}}
        response = list_restaurant_orders('rest_1', event)

        assert response['statusCode'] == 200
        query_kwargs = mock_table.query.call_args.kwargs
        assert query_kwargs['IndexName'] == 'GSI_RestaurantStatus'
        assert 'ScanIndexForward' not in query_kwargs
    finally:
        db.orders_table = original_table
