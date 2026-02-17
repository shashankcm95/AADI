import React from 'react';
import { render, fireEvent } from '@testing-library/react-native';
import { PeacockHeader } from '../PeacockHeader';

jest.mock('expo-linear-gradient', () => ({
    LinearGradient: ({ children }: any) => <>{children}</>,
}));

jest.mock('react-native-safe-area-context', () => ({
    useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
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

    it('calls onProfilePress when right action is tapped', () => {
        const onProfilePress = jest.fn();
        const { getByTestId } = render(<PeacockHeader onProfilePress={onProfilePress} />);

        fireEvent.press(getByTestId('peacock-header-right-button'));

        expect(onProfilePress).toHaveBeenCalled();
    });
});
