import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react-native';
import LoginScreen from '../screens/LoginScreen';
import { HomeScreen } from '../screens/HomeScreen';
import OrderScreen from '../screens/OrderScreen';
import CartScreen from '../screens/CartScreen';
import { CartProvider, useCart } from '../state/CartContext';
import { fetchAuthSession, signIn } from 'aws-amplify/auth';
import { getFavoritesWithCache } from '../services/favorites';
import { getRestaurantsWithCache } from '../services/restaurantsCatalog';
import {
    createOrder,
    getLeaveAdvisory,
    getOrder,
    getRestaurant,
    sendArrivalEvent,
} from '../services/api';
import {
    requestPermissions,
    startLocationTracking,
    stopLocationTracking,
} from '../services/location';
import { getCurrentUserProfile } from '../services/session';

jest.mock('aws-amplify/auth', () => ({
    confirmResetPassword: jest.fn(),
    confirmSignUp: jest.fn(),
    fetchAuthSession: jest.fn(),
    resendSignUpCode: jest.fn(),
    resetPassword: jest.fn(),
    signIn: jest.fn(),
    signOut: jest.fn(),
    signUp: jest.fn(),
}));

jest.mock('../services/restaurantsCatalog', () => ({
    getRestaurantsWithCache: jest.fn(),
}));

jest.mock('../services/favorites', () => ({
    favoriteIdsToMap: (ids: string[]) => ids.reduce<Record<string, boolean>>((acc, id) => {
        acc[id] = true;
        return acc;
    }, {}),
    getFavoritesWithCache: jest.fn(),
    setFavoriteForCurrentUser: jest.fn(),
}));

jest.mock('../services/api', () => ({
    createOrder: jest.fn(),
    getLeaveAdvisory: jest.fn(),
    getOrder: jest.fn(),
    getRestaurant: jest.fn(),
    sendArrivalEvent: jest.fn(),
}));

jest.mock('../services/location', () => ({
    requestPermissions: jest.fn(),
    startLocationTracking: jest.fn(),
    stopLocationTracking: jest.fn(),
}));

jest.mock('../services/session', () => ({
    getCurrentUserProfile: jest.fn(),
}));

jest.mock('expo-linear-gradient', () => ({
    LinearGradient: ({ children }: any) => <>{children}</>,
}));

function SeededCart({ navigation }: { navigation: any }) {
    const { addItemToCart } = useCart();
    const seededRef = React.useRef(false);

    React.useEffect(() => {
        if (seededRef.current) {
            return;
        }
        seededRef.current = true;

        addItemToCart({
            id: 'menu-1',
            name: 'Burger',
            price_cents: 1200,
            qty: 1,
            description: 'Classic',
        } as any, {
            restaurant_id: 'rest-1',
            name: 'Demo',
            latitude: 30.26,
            longitude: -97.74,
        } as any);
    }, [addItemToCart]);

    return <CartScreen navigation={navigation} />;
}

describe('mobile-ios e2e integration', () => {
    beforeEach(() => {
        jest.resetAllMocks();

        (getFavoritesWithCache as jest.Mock).mockResolvedValue({
            userId: 'cust_1',
            favoriteRestaurantIds: [],
            fromCache: false,
        });
    });

    it('sign-in flow resets navigation to Home', async () => {
        const navigation = { navigate: jest.fn(), reset: jest.fn() };

        (fetchAuthSession as jest.Mock)
            .mockResolvedValueOnce({ tokens: {} })
            .mockResolvedValue({
                tokens: {
                    idToken: {
                        payload: { email: 'e2e@example.com' },
                    },
                },
            });
        (signIn as jest.Mock).mockResolvedValue({
            isSignedIn: true,
            nextStep: { signInStep: 'DONE' },
        });

        const { getByPlaceholderText, getByText } = render(
            <LoginScreen navigation={navigation as any} />
        );

        fireEvent.changeText(getByPlaceholderText('user@example.com'), 'e2e@example.com');
        fireEvent.changeText(getByPlaceholderText('••••••••'), 'secret');
        fireEvent.press(getByText('Sign In'));

        await waitFor(() => {
            expect(navigation.reset).toHaveBeenCalledWith({
                index: 0,
                routes: [
                    {
                        name: 'Home',
                        params: { customerName: 'e2e' },
                    },
                ],
            });
        }, { timeout: 3000 });
    });

    it('home screen shows retry on outage and recovers after retry', async () => {
        const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined);
        const navigation = { navigate: jest.fn(), reset: jest.fn() };
        const route = { params: {} };

        (getRestaurantsWithCache as jest.Mock)
            .mockRejectedValueOnce(new Error('offline'))
            .mockResolvedValueOnce({
                userId: 'cust_1',
                restaurants: [{
                    restaurant_id: '1',
                    name: 'AADI Burger',
                    cuisine: 'Burgers',
                    rating: 4.8,
                    emoji: '🍔',
                    address: '123 Main St',
                    tags: ['fast'],
                }],
                fromCache: false,
            });

        const { getByText } = render(
            <HomeScreen navigation={navigation as any} route={route as any} />
        );

        await waitFor(() => {
            expect(getByText('Unable to load restaurants')).toBeTruthy();
        }, { timeout: 3000 });

        fireEvent.press(getByText('Retry'));

        await waitFor(() => {
            expect(getByText('AADI Burger')).toBeTruthy();
        }, { timeout: 3000 });

        errorSpy.mockRestore();
    });

    it('checkout flow sends AT_DOOR and stops tracking after arrival callback', async () => {
        const navigation = { navigate: jest.fn(), reset: jest.fn() };

        (getCurrentUserProfile as jest.Mock).mockResolvedValue({
            userId: 'cust_1',
            displayName: 'Customer',
        });
        (createOrder as jest.Mock).mockResolvedValue({
            order_id: 'order-123456',
            restaurant_id: 'rest-1',
            status: 'PENDING_NOT_SENT',
            items: [],
            total_cents: 1200,
        });
        (requestPermissions as jest.Mock).mockResolvedValue(true);
        (sendArrivalEvent as jest.Mock).mockResolvedValue({ status: 'ok' });
        (startLocationTracking as jest.Mock).mockImplementation(async (_restaurant, orderId, onEvent) => {
            await onEvent('AT_DOOR', orderId, { ignored: true });
        });

        const { getByText } = render(
            <CartProvider>
                <SeededCart navigation={navigation} />
            </CartProvider>
        );

        await waitFor(() => {
            expect(getByText('Place Order')).toBeTruthy();
        }, { timeout: 3000 });

        fireEvent.press(getByText('Place Order'));

        await waitFor(() => {
            expect(sendArrivalEvent).toHaveBeenCalledWith('order-123456', 'AT_DOOR');
        }, { timeout: 3000 });
        expect(stopLocationTracking).toHaveBeenCalled();
        expect(navigation.navigate).toHaveBeenCalledWith('Order', { orderId: 'order-123456' });
    });

    it('order screen manual "I\'m Here" sends AT_DOOR and stops tracking', async () => {
        (getOrder as jest.Mock).mockResolvedValue({
            order_id: 'order-123456',
            restaurant_id: 'rest-1',
            status: 'PENDING_NOT_SENT',
            arrival_status: 'UNKNOWN',
            items: [],
            total_cents: 1200,
        });
        (getLeaveAdvisory as jest.Mock).mockResolvedValue({
            recommended_action: 'LEAVE_NOW',
            estimated_wait_seconds: 0,
        });
        (getRestaurant as jest.Mock).mockResolvedValue({
            restaurant_id: 'rest-1',
            latitude: 30.26,
            longitude: -97.74,
        });
        (startLocationTracking as jest.Mock).mockResolvedValue(undefined);
        (sendArrivalEvent as jest.Mock).mockResolvedValue({ status: 'ok' });

        const { getByText } = render(
            <OrderScreen
                navigation={{ navigate: jest.fn() } as any}
                route={{ params: { orderId: 'order-123456' } } as any}
            />
        );

        await waitFor(() => {
            expect(getByText("I'm Here")).toBeTruthy();
        }, { timeout: 3000 });

        fireEvent.press(getByText("I'm Here"));

        await waitFor(() => {
            expect(sendArrivalEvent).toHaveBeenCalledWith('order-123456', 'AT_DOOR');
        }, { timeout: 3000 });
        expect(stopLocationTracking).toHaveBeenCalled();
    });
});
