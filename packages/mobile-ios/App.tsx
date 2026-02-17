import { StatusBar } from 'expo-status-bar';
import { StyleSheet, View, TouchableOpacity, Text } from 'react-native';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { theme } from './src/theme';
import { CartProvider } from './src/state/CartContext';

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

export default function App() {
    return (
        <CartProvider>
            <NavigationContainer theme={navTheme}>
                <View style={styles.container}>
                    <StatusBar style="dark" />
                    <Stack.Navigator
                        screenOptions={({ navigation, route }: any) => ({
                            headerStyle: { backgroundColor: theme.colors.background },
                            headerTintColor: theme.colors.primary,
                            headerTitleStyle: { fontWeight: 'bold', fontFamily: 'System', fontSize: 20 },
                            headerShadowVisible: false,
                            contentStyle: { backgroundColor: theme.colors.background },
                            headerBackTitleVisible: false,
                            headerRight: route.name !== 'Home' && route.name !== 'Login'
                                ? () => (
                                    <TouchableOpacity
                                        onPress={() => navigation.navigate('Home')}
                                        style={styles.homeButton}
                                    >
                                        <Text style={styles.homeButtonText}>Home</Text>
                                    </TouchableOpacity>
                                )
                                : undefined,
                        })}
                    >
                        <Stack.Screen
                            name="Login"
                            component={LoginScreen}
                            options={{ title: 'AADI', headerShown: false }}
                        />
                        <Stack.Screen
                            name="Home"
                            component={HomeScreen}
                            options={{ headerShown: false }}
                        />
                        <Stack.Screen
                            name="Menu"
                            component={MenuScreen}
                            options={({ route }: any) => ({
                                title: route.params?.restaurant?.name || 'Menu',
                            })}
                        />
                        <Stack.Screen
                            name="Cart"
                            component={CartScreen}
                            options={{ title: 'Your Cart' }}
                        />
                        <Stack.Screen
                            name="Order"
                            component={OrderScreen}
                            options={{ title: 'Your Order' }}
                        />
                        <Stack.Screen
                            name="Orders"
                            component={OrdersScreen}
                            options={{ title: 'Past Orders' }}
                        />
                        <Stack.Screen
                            name="Profile"
                            component={ProfileScreen}
                            options={{ title: 'Profile' }}
                        />
                        <Stack.Screen
                            name="Favorites"
                            component={FavoritesScreen}
                            options={{ title: 'Favorites' }}
                        />
                        <Stack.Screen
                            name="Restaurants"
                            component={RestaurantsScreen}
                            options={{ title: 'Browse' }}
                        />
                    </Stack.Navigator>
                </View>
            </NavigationContainer>
        </CartProvider>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
    },
    homeButton: {
        borderWidth: 1,
        borderColor: theme.colors.border,
        borderRadius: theme.radii.chip,
        backgroundColor: theme.colors.surface,
        paddingHorizontal: theme.spacing.sm,
        paddingVertical: theme.spacing.xs,
    },
    homeButtonText: {
        ...theme.typography.caption,
        color: theme.colors.text,
        fontWeight: '700',
    },
});
