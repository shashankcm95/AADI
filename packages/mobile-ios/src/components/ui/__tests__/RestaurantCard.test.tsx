import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { RestaurantCard } from '../RestaurantCard';

describe('RestaurantCard', () => {
    const mockProps = {
        name: 'Test Restaurant',
        cuisine: 'Italian',
        rating: 4.5,
        priceTier: 2,
        deliveryTime: '20-30 min',
        onPress: jest.fn(),
        emoji: '🍕',
    };

    it('renders correctly', () => {
        const { getByText } = render(<RestaurantCard {...mockProps} />);

        expect(getByText('Test Restaurant')).toBeTruthy();
        expect(getByText(/Italian/)).toBeTruthy();
        expect(getByText('4.5')).toBeTruthy();
        expect(getByText('🍕')).toBeTruthy();
    });

    it('calls onPress when tapped', () => {
        const { getByText } = render(<RestaurantCard {...mockProps} />);
        const card = getByText('Test Restaurant');

        fireEvent.press(card);
        expect(mockProps.onPress).toHaveBeenCalled();
    });
});
