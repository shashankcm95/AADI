import {
    addFavorite,
    clearAuthHeaderCache,
    createOrder,
    getFavorites,
    getRestaurantMenu,
    getRestaurants,
    OrderItem,
    removeFavorite,
} from '../api';

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
        clearAuthHeaderCache();
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

    it('createOrder sanitizes items before sending', async () => {
        const mockOrder = { order_id: '123', status: 'created' };
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => mockOrder,
        });

        const items: OrderItem[] = [{
            id: '',
            name: 'Burger',
            price_cents: -50,
            qty: 0,
            description: '   ',
        }];

        await createOrder('rest_1', items, 'John');

        const [, request] = (global.fetch as jest.Mock).mock.calls[0];
        const payload = JSON.parse(request.body);

        expect(payload.items).toEqual([
            {
                id: 'local-item-0',
                name: 'Burger',
                price_cents: 0,
                qty: 1,
            },
        ]);
    });

    it('getFavorites fetches and returns data', async () => {
        const mockFavorites = [{ customer_id: 'cust_1', restaurant_id: 'rest_1' }];
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ favorites: mockFavorites }),
        });

        const result = await getFavorites();
        expect(result).toEqual(mockFavorites);
        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('/v1/favorites'),
            expect.objectContaining({
                headers: expect.objectContaining({ Authorization: 'Bearer mock-token' }),
            })
        );
    });

    it('addFavorite sends PUT to favorites endpoint', async () => {
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({}),
        });

        await addFavorite('rest_1');

        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('/v1/favorites/rest_1'),
            expect.objectContaining({
                method: 'PUT',
            })
        );
    });

    it('removeFavorite sends DELETE to favorites endpoint', async () => {
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({}),
        });

        await removeFavorite('rest_1');

        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('/v1/favorites/rest_1'),
            expect.objectContaining({
                method: 'DELETE',
            })
        );
    });

    it('getRestaurantMenu generates fallback IDs when backend IDs are missing', async () => {
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                items: [
                    { name: 'Burger', price_cents: 1200 },
                    { name: '', price_cents: 500 },
                ],
            }),
        });

        const items = await getRestaurantMenu('rest_1');

        expect(items[0].id).toBe('local-rest_1-burger-0');
        expect(items[1].id).toBe('local-rest_1-item-1');
    });
});
