import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { RestaurantCard } from '../RestaurantCard';

jest.mock('expo-linear-gradient', () => ({
    LinearGradient: ({ children }: any) => <>{children}</>,
}));

describe('RestaurantCard', () => {
    const mockProps = {
        name: 'Test Restaurant',
        cuisine: 'Italian',
        rating: 4.5,
        ratingCount: 120,
        deliveryTime: '20-30 min',
        deliveryFee: '$1.99 delivery',
        priceTier: 2,
        onPress: jest.fn(),
        emoji: '🍕',
    };

    it('renders key data', () => {
        const { getByText, getAllByText } = render(<RestaurantCard {...mockProps} />);

        expect(getByText('Test Restaurant')).toBeTruthy();
        expect(getByText('4.5')).toBeTruthy();
        expect(getByText('$1.99 delivery')).toBeTruthy();
        expect(getAllByText(/Italian/).length).toBeGreaterThan(0);
    });

    it('calls onPress when card is tapped', () => {
        const { getByTestId } = render(<RestaurantCard {...mockProps} />);
        fireEvent.press(getByTestId('restaurant-card'));
        expect(mockProps.onPress).toHaveBeenCalled();
    });
});
