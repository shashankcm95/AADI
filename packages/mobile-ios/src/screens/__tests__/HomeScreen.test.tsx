import React from 'react';
import { render, waitFor, fireEvent } from '@testing-library/react-native';
import { HomeScreen } from '../HomeScreen';
import * as favorites from '../../services/favorites';
import * as restaurantsCatalog from '../../services/restaurantsCatalog';

jest.mock('../../services/restaurantsCatalog', () => ({
    getRestaurantsWithCache: jest.fn(),
}));
jest.mock('../../services/favorites', () => ({
    favoriteIdsToMap: (ids: string[]) => ids.reduce<Record<string, boolean>>((acc, id) => {
        acc[id] = true;
        return acc;
    }, {}),
    getFavoritesWithCache: jest.fn(),
    setFavoriteForCurrentUser: jest.fn(),
}));
jest.mock('expo-linear-gradient', () => ({
    LinearGradient: ({ children }: any) => <>{children}</>,
}));
jest.mock('react-native-safe-area-context', () => ({
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

describe('HomeScreen', () => {
    const mockNavigation = {
        navigate: jest.fn(),
        reset: jest.fn(),
    };

    const mockRoute = { params: {} };

    const mockRestaurants = [
        {
            restaurant_id: '1',
            name: 'AADI Burger',
            cuisine: 'Burgers',
            rating: 4.8,
            emoji: '🍔',
            address: '123 Main St',
            tags: ['fast'],
        },
        {
            restaurant_id: '2',
            name: 'Zed Cafe',
            cuisine: 'Cafe',
            rating: 4.2,
            emoji: '☕',
            address: '456 Oak St',
            tags: ['coffee'],
        },
    ];

    beforeEach(() => {
        jest.clearAllMocks();
        (restaurantsCatalog.getRestaurantsWithCache as jest.Mock).mockResolvedValue({
            userId: 'cust_1',
            restaurants: mockRestaurants,
            fromCache: false,
        });
        (favorites.getFavoritesWithCache as jest.Mock).mockResolvedValue({
            userId: 'cust_1',
            favoriteRestaurantIds: [],
            fromCache: false,
        });
        (favorites.setFavoriteForCurrentUser as jest.Mock).mockResolvedValue(undefined);
    });

    it('renders restaurants after loading', async () => {
        const { getByText } = render(<HomeScreen navigation={mockNavigation} route={mockRoute} />);

        await waitFor(() => {
            expect(getByText('AADI Burger')).toBeTruthy();
            expect(getByText('Zed Cafe')).toBeTruthy();
        });
    });

    it('filters restaurants by search text', async () => {
        const { getByPlaceholderText, getByText, queryByText } = render(
            <HomeScreen navigation={mockNavigation} route={mockRoute} />
        );

        await waitFor(() => {
            expect(getByText('AADI Burger')).toBeTruthy();
            expect(getByText('Zed Cafe')).toBeTruthy();
        });

        fireEvent.changeText(getByPlaceholderText('Deliver to Your Location'), 'burger');

        expect(getByText('AADI Burger')).toBeTruthy();
        expect(queryByText('Zed Cafe')).toBeNull();
    });

    it('navigates to Menu on restaurant press', async () => {
        const { getByText } = render(<HomeScreen navigation={mockNavigation} route={mockRoute} />);

        await waitFor(() => expect(getByText('AADI Burger')).toBeTruthy());

        fireEvent.press(getByText('AADI Burger'));

        expect(mockNavigation.navigate).toHaveBeenCalledWith('Menu', {
            restaurant: mockRestaurants[0],
            customerName: 'Guest',
        });
    });

    it('shows connection error state and recovers on retry', async () => {
        const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);

        (restaurantsCatalog.getRestaurantsWithCache as jest.Mock)
            .mockRejectedValueOnce(new Error('offline'))
            .mockResolvedValueOnce({
                userId: 'cust_1',
                restaurants: mockRestaurants,
                fromCache: false,
            });

        const { getByText } = render(<HomeScreen navigation={mockNavigation} route={mockRoute} />);

        await waitFor(() => {
            expect(getByText('Unable to load restaurants')).toBeTruthy();
            expect(getByText('Retry')).toBeTruthy();
        });

        fireEvent.press(getByText('Retry'));

        await waitFor(() => {
            expect(getByText('AADI Burger')).toBeTruthy();
        });

        errorSpy.mockRestore();
    });
});
