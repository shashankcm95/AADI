import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { PeacockHeader } from '../PeacockHeader';

// Mock Linear Gradient since it's a native module
jest.mock('expo-linear-gradient', () => ({
    LinearGradient: ({ children, style }: any) => <>{children}</>,
}));

// Mock SafeAreaView
jest.mock('react-native-safe-area-context', () => ({
    SafeAreaView: ({ children }: any) => <>{children}</>,
}));

describe('PeacockHeader', () => {
    it('renders default title', () => {
        const { getByText } = render(<PeacockHeader />);
        expect(getByText('AADI')).toBeTruthy();
    });

    it('renders custom title', () => {
        const { getByText } = render(<PeacockHeader title="Custom Title" />);
        expect(getByText('Custom Title')).toBeTruthy();
    });

    it('calls onProfilePress when profile icon is tapped', () => {
        const onProfilePress = jest.fn();
        const { getByText } = render(<PeacockHeader onProfilePress={onProfilePress} />);

        const profileIcon = getByText('👤');
        fireEvent.press(profileIcon);

        expect(onProfilePress).toHaveBeenCalled();
    });
});
