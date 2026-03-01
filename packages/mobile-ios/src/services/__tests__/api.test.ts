import {
    addFavorite,
    clearAuthHeaderCache,
    createOrder,
    getFavorites,
    getRestaurant,
    getRestaurantMenu,
    getRestaurants,
    OrderItem,
    removeFavorite,
    sendLocationSample,
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

    it('getRestaurants maps location.lat/lon to top-level latitude/longitude', async () => {
        const mockRestaurants = [{
            restaurant_id: '1',
            name: 'Geo Rest',
            location: { lat: 30.2672, lon: -97.7431 },
        }];
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ restaurants: mockRestaurants }),
        });

        const result = await getRestaurants();
        expect(result[0].latitude).toBeCloseTo(30.2672, 4);
        expect(result[0].longitude).toBeCloseTo(-97.7431, 4);
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

    it('getRestaurant fetches a single restaurant by ID', async () => {
        const mockRestaurant = { restaurant_id: 'rest_1', name: 'Test Rest', cuisine: 'Italian' };
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => mockRestaurant,
        });

        const result = await getRestaurant('rest_1');
        expect(result.restaurant_id).toBe('rest_1');
        expect(result.name).toBe('Test Rest');
        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('/v1/restaurants/rest_1'),
            expect.objectContaining({
                headers: expect.objectContaining({ Authorization: 'Bearer mock-token' }),
            })
        );
    });

    it('getRestaurant throws "Restaurant not found" on 404', async () => {
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: false,
            status: 404,
        });

        await expect(getRestaurant('missing')).rejects.toThrow('Restaurant not found');
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

    it('passes category through from API response', async () => {
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                items: [
                    { id: 'item_1', name: 'Pad Thai', price_cents: 1400, category: 'Mains' },
                    { id: 'item_2', name: 'Spring Rolls', price_cents: 800, category: 'Appetizers' },
                    { id: 'item_3', name: 'Iced Tea', price_cents: 350 },
                ],
            }),
        });

        const items = await getRestaurantMenu('rest_cat');

        expect(items[0].category).toBe('Mains');
        expect(items[1].category).toBe('Appetizers');
        // Item with no category returns category === ''
        expect(items[2].category).toBe('');
    });

    it('sendLocationSample posts to location telemetry endpoint', async () => {
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ received: true }),
        });

        await sendLocationSample('ord_1', {
            latitude: 30.26,
            longitude: -97.74,
            sample_time: 1700000000,
        });

        expect(global.fetch).toHaveBeenCalledWith(
            expect.stringContaining('/v1/orders/ord_1/location'),
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({
                    latitude: 30.26,
                    longitude: -97.74,
                    sample_time: 1700000000,
                }),
            })
        );
    });

    it('sendLocationSample disables repeated posts when location route is missing', async () => {
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: false,
            status: 404,
            text: async () => '{"message":"Not Found"}',
        });

        const first = await sendLocationSample('ord_1', {
            latitude: 30.26,
            longitude: -97.74,
        });
        expect(first).toEqual({ received: false });
        expect(global.fetch).toHaveBeenCalledTimes(1);

        (global.fetch as jest.Mock).mockClear();

        const second = await sendLocationSample('ord_1', {
            latitude: 30.27,
            longitude: -97.73,
        });
        expect(second).toEqual({ received: false });
        expect(global.fetch).not.toHaveBeenCalled();
    });

    it('sendLocationSample suppresses fetch after cooldown is set by a 404', async () => {
        // First call triggers 404 and sets the cooldown timestamp.
        (global.fetch as jest.Mock).mockResolvedValueOnce({
            ok: false,
            status: 404,
            text: async () => '{"message":"Not Found"}',
        });

        const first = await sendLocationSample('ord_1', { latitude: 30.26, longitude: -97.74 });
        expect(first).toEqual({ received: false });
        expect(global.fetch).toHaveBeenCalledTimes(1);

        // Second call should be suppressed (no fetch) because cooldown is active.
        (global.fetch as jest.Mock).mockClear();
        const second = await sendLocationSample('ord_2', { latitude: 30.27, longitude: -97.73 });
        expect(second).toEqual({ received: false });
        expect(global.fetch).not.toHaveBeenCalled();
    });
});
