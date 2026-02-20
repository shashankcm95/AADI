import React from 'react';
import { render } from '@testing-library/react-native';
import App from './App';

let capturedScreenOptions: any;

jest.mock('@react-navigation/native', () => {
    return {
        NavigationContainer: ({ children }: any) => <>{children}</>,
        DefaultTheme: { colors: {} },
    };
});

jest.mock('@react-navigation/native-stack', () => {
    return {
        createNativeStackNavigator: () => ({
            Navigator: ({ screenOptions, children }: any) => {
                capturedScreenOptions = screenOptions;
                return <>{children}</>;
            },
            Screen: () => null,
        }),
    };
});

jest.mock('./src/screens/LoginScreen', () => () => null);
jest.mock('./src/screens/HomeScreen', () => ({ HomeScreen: () => null }));
jest.mock('./src/screens/MenuScreen', () => () => null);
jest.mock('./src/screens/OrderScreen', () => () => null);
jest.mock('./src/screens/RestaurantsScreen', () => () => null);
jest.mock('./src/screens/OrdersScreen', () => () => null);
jest.mock('./src/screens/ProfileScreen', () => () => null);
jest.mock('./src/screens/CartScreen', () => () => null);
jest.mock('./src/screens/FavoritesScreen', () => () => null);

describe('App navigator config', () => {
    beforeEach(() => {
        capturedScreenOptions = undefined;
    });

    it('does not inject a global Home header button', () => {
        render(<App />);
        expect(capturedScreenOptions?.headerRight).toBeUndefined();
    });
});
