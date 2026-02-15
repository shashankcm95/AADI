import { getRestaurants, createOrder, OrderItem } from '../api';

// Mock fetch
global.fetch = jest.fn();

// Mock Auth
jest.mock('aws-amplify/auth', () => ({
    fetchAuthSession: jest.fn().mockResolvedValue({
        tokens: { idToken: { toString: () => 'mock-token' } }
    }),
}));

describe('API Service', () => {
    beforeEach(() => {
        (global.fetch as jest.Mock).mockClear();
    });

    it('getRestaurants fetches and returns data', async () => {
        const mockRestaurants = [{ restaurant_id: '1', name: 'Test Rest' }];
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ restaurants: mockRestaurants }),
        });

        const result = await getRestaurants();
        expect(result).toEqual(mockRestaurants);
        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('/v1/restaurants'),
            expect.objectContaining({
                headers: expect.objectContaining({ Authorization: 'Bearer mock-token' }),
            })
        );
    });

    it('createOrder sends correct payload', async () => {
        const mockOrder = { order_id: '123', status: 'created' };
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => mockOrder,
        });

        const items: OrderItem[] = [{ id: '1', name: 'Burger', price_cents: 1000, qty: 1 }];
        const result = await createOrder('rest_1', items, 'John');

        expect(result).toEqual(mockOrder);
        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('/v1/orders'),
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({
                    restaurant_id: 'rest_1',
                    items,
                    customer_name: 'John',
                }),
            })
        );
    });
});
