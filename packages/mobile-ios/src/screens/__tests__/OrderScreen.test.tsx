import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import OrderScreen from '../OrderScreen';
import {
    getLeaveAdvisory,
    getOrder,
    getRestaurant,
    sendArrivalEvent,
} from '../../services/api';
import {
    getPermissionLevel,
    requestPermissions,
    startLocationTracking,
    stopLocationTracking,
    triggerImmediateVicinityCheck,
} from '../../services/location';

jest.mock('../../services/api', () => ({
    getLeaveAdvisory: jest.fn(),
    getOrder: jest.fn(),
    getRestaurant: jest.fn(),
    sendLocationSample: jest.fn(),
    sendArrivalEvent: jest.fn(),
}));

jest.mock('../../services/location', () => ({
    getPermissionLevel: jest.fn(),
    requestPermissions: jest.fn(),
    startLocationTracking: jest.fn(),
    stopLocationTracking: jest.fn(),
    triggerImmediateVicinityCheck: jest.fn(),
}));

describe('OrderScreen', () => {
    beforeEach(() => {
        jest.clearAllMocks();
        (requestPermissions as jest.Mock).mockResolvedValue(true);
        (getPermissionLevel as jest.Mock).mockResolvedValue('foreground');
        (triggerImmediateVicinityCheck as jest.Mock).mockResolvedValue('exact');
    });

    it('renders fallback when orderId is missing', () => {
        const { getByText } = render(
            <OrderScreen navigation={{ navigate: jest.fn() } as any} route={{ params: {} } as any} />
        );

        expect(getByText('Order not found')).toBeTruthy();
    });

    it('does not spin forever when fetching the order fails', async () => {
        jest.spyOn(console, 'error').mockImplementation(() => undefined);
        (getOrder as jest.Mock).mockRejectedValue(new Error('network down'));

        const { getByText } = render(
            <OrderScreen
                navigation={{ navigate: jest.fn() } as any}
                route={{ params: { orderId: 'order-123456' } } as any}
            />
        );

        await waitFor(() => {
            expect(getByText('Order #123456')).toBeTruthy();
        });

        (console.error as jest.Mock).mockRestore();
    });

    it('stops tracking when order already reached the restaurant', async () => {
        (getOrder as jest.Mock).mockResolvedValue({
            order_id: 'order-123456',
            restaurant_id: 'rest-1',
            status: 'READY',
            arrival_status: 'AT_DOOR',
            items: [],
            total_cents: 0,
        });

        render(
            <OrderScreen
                navigation={{ navigate: jest.fn() } as any}
                route={{ params: { orderId: 'order-123456' } } as any}
            />
        );

        await waitFor(() => {
            expect(stopLocationTracking).toHaveBeenCalled();
        });
        expect(startLocationTracking).not.toHaveBeenCalled();
    });

    it('manual "I\'m Here" sends AT_DOOR and stops tracking', async () => {
        (getOrder as jest.Mock).mockResolvedValue({
            order_id: 'order-123456',
            restaurant_id: 'rest-1',
            status: 'PENDING_NOT_SENT',
            arrival_status: 'UNKNOWN',
            items: [],
            total_cents: 0,
        });
        (getLeaveAdvisory as jest.Mock).mockResolvedValue({
            recommended_action: 'LEAVE_NOW',
            estimated_wait_seconds: 0,
        });
        (getRestaurant as jest.Mock).mockResolvedValue({
            latitude: 30.26,
            longitude: -97.74,
            restaurant_id: 'rest-1',
        });
        (sendArrivalEvent as jest.Mock).mockResolvedValue({ status: 'ok' });
        (startLocationTracking as jest.Mock).mockResolvedValue(undefined);

        const { getByText } = render(
            <OrderScreen
                navigation={{ navigate: jest.fn() } as any}
                route={{ params: { orderId: 'order-123456' } } as any}
            />
        );

        await waitFor(() => {
            expect(getByText("I'm Here")).toBeTruthy();
        });

        fireEvent.press(getByText("I'm Here"));

        await waitFor(() => {
            expect(sendArrivalEvent).toHaveBeenCalledWith('order-123456', 'AT_DOOR');
        });
        expect(stopLocationTracking).toHaveBeenCalled();
    });
});
