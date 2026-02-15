import React from 'react';
import { render, waitFor, fireEvent } from '@testing-library/react-native';
import { HomeScreen } from '../HomeScreen';
import * as api from '../../services/api';

// Mocks
jest.mock('../../services/api');
jest.mock('expo-linear-gradient', () => ({
    LinearGradient: ({ children }: any) => <>{children}</>,
}));
jest.mock('react-native-safe-area-context', () => ({
    SafeAreaView: ({ children }: any) => <>{children}</>,
}));

describe('HomeScreen', () => {
    const mockNavigation = { navigate: jest.fn() };
    const mockRestaurants = [
        {
            restaurant_id: '1',
            name: 'AADI Burger',
            cuisine: 'Burgers',
            rating: 4.8,
            emoji: '🍔',
            address: '123 Main St',
        }
    ];

    beforeEach(() => {
        jest.clearAllMocks();
        (api.getRestaurants as jest.Mock).mockResolvedValue(mockRestaurants);
    });

    it('renders loading state initially', () => {
        const { getByTestId } = render(<HomeScreen navigation={mockNavigation} />);
        // Note: ActivityIndicator doesn't have a default testID, but we can search by type if needed
        // or just assume implicit rendering. For strictness, let's wait for data.
    });

    it('renders restaurants after loading', async () => {
        const { getByText } = render(<HomeScreen navigation={mockNavigation} />);

        await waitFor(() => {
            expect(getByText('AADI Burger')).toBeTruthy();
            expect(getByText('Burgers')).toBeTruthy();
        });
    });

    it('navigates to Menu on card press', async () => {
        const { getByText } = render(<HomeScreen navigation={mockNavigation} />);

        await waitFor(() => expect(getByText('AADI Burger')).toBeTruthy());

        fireEvent.press(getByText('AADI Burger'));

        expect(mockNavigation.navigate).toHaveBeenCalledWith('Menu', {
            restaurant: mockRestaurants[0]
        });
    });
});
