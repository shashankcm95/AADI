import { StatusBar } from 'expo-status-bar';
import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { theme } from './src/theme';
import { CartProvider } from './src/state/CartContext';
import { ToastProvider } from './src/components/ui/Toast';
import { configureNudgeNotifications } from './src/services/notifications';

// Screens
import LoginScreen from './src/screens/LoginScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import MenuScreen from './src/screens/MenuScreen';
import OrderScreen from './src/screens/OrderScreen';
import RestaurantsScreen from './src/screens/RestaurantsScreen';
import OrdersScreen from './src/screens/OrdersScreen';
import ProfileScreen from './src/screens/ProfileScreen';
import CartScreen from './src/screens/CartScreen';
import FavoritesScreen from './src/screens/FavoritesScreen';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

const navTheme = {
    ...DefaultTheme,
    colors: {
        ...DefaultTheme.colors,
        background: theme.colors.background,
        primary: theme.colors.primary,
        card: theme.colors.background,
        text: theme.colors.primary,
    },
};

const commonStackOptions = {
    headerStyle: { backgroundColor: theme.colors.background },
    headerTintColor: theme.colors.primary,
    headerTitleStyle: { fontWeight: 'bold' as const, fontFamily: 'System', fontSize: 20 },
    headerShadowVisible: false,
    contentStyle: { backgroundColor: theme.colors.background },
};

// Each tab has its own nested stack so drill-downs keep the tab bar visible
function HomeStack() {
    return (
        <Stack.Navigator screenOptions={commonStackOptions}>
            <Stack.Screen name="HomeMain" component={HomeScreen} options={{ headerShown: false }} />
            <Stack.Screen
                name="Menu"
                component={MenuScreen}
                options={({ route }: any) => ({ title: route.params?.restaurant?.name || 'Menu' })}
            />
            <Stack.Screen name="Cart" component={CartScreen} options={{ title: 'Your Cart' }} />
            <Stack.Screen name="Order" component={OrderScreen} options={{ title: 'Your Order' }} />
        </Stack.Navigator>
    );
}

function BrowseStack() {
    return (
        <Stack.Navigator screenOptions={commonStackOptions}>
            <Stack.Screen name="BrowseMain" component={RestaurantsScreen} options={{ title: 'Browse' }} />
            <Stack.Screen
                name="Menu"
                component={MenuScreen}
                options={({ route }: any) => ({ title: route.params?.restaurant?.name || 'Menu' })}
            />
            <Stack.Screen name="Cart" component={CartScreen} options={{ title: 'Your Cart' }} />
            <Stack.Screen name="Order" component={OrderScreen} options={{ title: 'Your Order' }} />
        </Stack.Navigator>
    );
}

function OrdersStack() {
    return (
        <Stack.Navigator screenOptions={commonStackOptions}>
            <Stack.Screen name="OrdersMain" component={OrdersScreen} options={{ title: 'Past Orders' }} />
            <Stack.Screen name="Order" component={OrderScreen} options={{ title: 'Your Order' }} />
        </Stack.Navigator>
    );
}

function FavoritesStack() {
    return (
        <Stack.Navigator screenOptions={commonStackOptions}>
            <Stack.Screen name="FavoritesMain" component={FavoritesScreen} options={{ title: 'Favorites' }} />
            <Stack.Screen
                name="Menu"
                component={MenuScreen}
                options={({ route }: any) => ({ title: route.params?.restaurant?.name || 'Menu' })}
            />
            <Stack.Screen name="Cart" component={CartScreen} options={{ title: 'Your Cart' }} />
            <Stack.Screen name="Order" component={OrderScreen} options={{ title: 'Your Order' }} />
        </Stack.Navigator>
    );
}

function ProfileStack() {
    return (
        <Stack.Navigator screenOptions={commonStackOptions}>
            <Stack.Screen name="ProfileMain" component={ProfileScreen} options={{ title: 'Profile' }} />
        </Stack.Navigator>
    );
}

function MainTabs() {
    return (
        <Tab.Navigator
            screenOptions={{
                headerShown: false,
                tabBarActiveTintColor: theme.colors.blue4,
                tabBarInactiveTintColor: theme.colors.textSecondary,
                tabBarStyle: {
                    backgroundColor: theme.colors.surface,
                    borderTopWidth: 1,
                    borderTopColor: theme.colors.border,
                },
                tabBarLabelStyle: {
                    fontSize: 11,
                    fontWeight: '600',
                },
            }}
        >
            <Tab.Screen
                name="Home"
                component={HomeStack}
                options={{
                    tabBarIcon: ({ color }) => <Text style={{ fontSize: 18, color }}>⌂</Text>,
                }}
            />
            <Tab.Screen
                name="Browse"
                component={BrowseStack}
                options={{
                    tabBarIcon: ({ color }) => <Text style={{ fontSize: 18, color }}>⌕</Text>,
                }}
            />
            <Tab.Screen
                name="Orders"
                component={OrdersStack}
                options={{
                    tabBarIcon: ({ color }) => <Text style={{ fontSize: 18, color }}>🛒</Text>,
                }}
            />
            <Tab.Screen
                name="Favorites"
                component={FavoritesStack}
                options={{
                    tabBarIcon: ({ color }) => <Text style={{ fontSize: 18, color }}>♥</Text>,
                }}
            />
            <Tab.Screen
                name="Profile"
                component={ProfileStack}
                options={{
                    tabBarIcon: ({ color }) => <Text style={{ fontSize: 18, color }}>◉</Text>,
                }}
            />
        </Tab.Navigator>
    );
}

const RootStack = createNativeStackNavigator();

export default function App() {
    useEffect(() => {
        configureNudgeNotifications();
    }, []);

    return (
        <SafeAreaProvider>
            <CartProvider>
                <ToastProvider>
                    <NavigationContainer theme={navTheme}>
                        <View style={styles.container}>
                            <StatusBar style="dark" />
                            <RootStack.Navigator screenOptions={{ headerShown: false }}>
                                <RootStack.Screen name="Login" component={LoginScreen} />
                                <RootStack.Screen name="MainTabs" component={MainTabs} />
                            </RootStack.Navigator>
                        </View>
                    </NavigationContainer>
                </ToastProvider>
            </CartProvider>
        </SafeAreaProvider>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
    },
});
