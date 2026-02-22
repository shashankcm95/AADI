import React from 'react';
import { render, waitFor } from '@testing-library/react-native';

import OrdersScreen from '../OrdersScreen';
import { getMyOrdersWithCache } from '../../services/orderHistory';
import { getRestaurantsWithCache } from '../../services/restaurantsCatalog';

jest.mock('../../services/orderHistory', () => ({
    getMyOrdersWithCache: jest.fn(),
}));

jest.mock('../../services/restaurantsCatalog', () => ({
    getRestaurantsWithCache: jest.fn(),
}));

describe('OrdersScreen', () => {
    beforeEach(() => {
        jest.clearAllMocks();
    });

    it('renders epoch-seconds timestamps correctly', async () => {
        (getMyOrdersWithCache as jest.Mock).mockResolvedValue({
            fromCache: false,
            orders: [
                {
                    order_id: 'ord-1',
                    restaurant_id: 'rest-1',
                    status: 'PENDING_NOT_SENT',
                    items: [{ id: 'burger', qty: 1 }],
                    total_cents: 1200,
                    created_at: 1700000000,
                },
            ],
        });
        (getRestaurantsWithCache as jest.Mock).mockResolvedValue({
            restaurants: [
                {
                    restaurant_id: 'rest-1',
                    name: 'Test Kitchen',
                    cuisine: 'American',
                    rating: 4.5,
                    emoji: '🍔',
                    address: '123 Main St',
                },
            ],
        });

        const expectedDate = new Date(1700000000 * 1000).toLocaleString();
        const { getByText } = render(
            <OrdersScreen navigation={{ navigate: jest.fn() } as any} />
        );

        await waitFor(() => {
            expect(getByText(expectedDate)).toBeTruthy();
        });
    });

    it('renders safely when legacy orders are missing restaurant_id', async () => {
        (getMyOrdersWithCache as jest.Mock).mockResolvedValue({
            fromCache: false,
            orders: [
                {
                    order_id: 'ord-legacy-1',
                    status: 'PENDING_NOT_SENT',
                    items: [],
                    total_cents: 0,
                    created_at: 1700000000,
                },
            ],
        });
        (getRestaurantsWithCache as jest.Mock).mockResolvedValue({
            restaurants: [],
        });

        const { getByText } = render(
            <OrdersScreen navigation={{ navigate: jest.fn() } as any} />
        );

        await waitFor(() => {
            expect(getByText('Restaurant N/A')).toBeTruthy();
        });
    });
});
