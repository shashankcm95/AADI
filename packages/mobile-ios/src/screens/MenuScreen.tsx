/**
 * Menu Screen
 * Agent Kappa: Order placement flow
 */
import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    FlatList,
    TouchableOpacity,
    StyleSheet,
    Alert,
    ActivityIndicator,
} from 'react-native';
import { createOrder, getRestaurantMenu, Restaurant } from '../services/api';
import { startLocationTracking, requestPermissions } from '../services/location';
import { theme } from '../theme';

interface Props {
    navigation: any;
    route: any;
}

export default function MenuScreen({ navigation, route }: Props) {
    const [cart, setCart] = useState<any[]>([]);
    const [menuItems, setMenuItems] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    const restaurant: Restaurant | undefined = route.params?.restaurant;
    const customerName = route.params?.customerName || 'Guest';

    useEffect(() => {
        if (!restaurant?.restaurant_id) {
            Alert.alert('Restaurant Missing', 'Please select a restaurant to continue.');
            navigation.goBack();
            return;
        }
        loadMenu();
    }, [restaurant?.restaurant_id]);

    const loadMenu = async () => {
        if (!restaurant?.restaurant_id) {
            return;
        }
        try {
            const items = await getRestaurantMenu(restaurant.restaurant_id);
            setMenuItems(items);
        } catch (error) {
            console.error('Failed to load menu:', error);
            Alert.alert('Error', 'Could not load menu');
        } finally {
            setLoading(false);
        }
    };

    const addToCart = (item: any) => {
        const existing = cart.find(c => c.id === item.id);
        if (existing) {
            setCart(cart.map(c => c.id === item.id ? { ...c, qty: c.qty + 1 } : c));
        } else {
            setCart([...cart, { ...item, qty: 1 }]);
        }
    };

    const getCartTotal = () => {
        return cart.reduce((sum, item) => sum + item.price_cents * item.qty, 0);
    };

    const handlePlaceOrder = async () => {
        if (cart.length === 0) {
            Alert.alert('Cart Empty', 'Add some items first!');
            return;
        }

        try {
            if (!restaurant?.restaurant_id) {
                Alert.alert('Restaurant Missing', 'Please select a restaurant to continue.');
                return;
            }

            const order = await createOrder(restaurant.restaurant_id, cart, customerName);

            // Navigate to order screen
            navigation.navigate('Order', { orderId: order.order_id });
            setCart([]);

            // Try location tracking in background (non-blocking)
            try {
                const hasPermission = await requestPermissions();
                if (hasPermission) {
                    const hasCoordinates = Number.isFinite(restaurant.latitude) && Number.isFinite(restaurant.longitude);
                    if (hasCoordinates) {
                        startLocationTracking(
                            {
                                latitude: Number(restaurant.latitude),
                                longitude: Number(restaurant.longitude),
                                restaurantId: restaurant.restaurant_id,
                            },
                            order.order_id,
                            () => { }
                        );
                    } else {
                        console.warn('[MenuScreen] Restaurant coordinates unavailable; background arrival tracking skipped.');
                    }
                }
            } catch (locErr) {
                console.warn('[MenuScreen] Location tracking skipped:', locErr);
            }
        } catch (error: any) {
            console.error('[MenuScreen] Order placement FAILED:', error?.message);
            Alert.alert('Error', `Failed to place order: ${error?.message || 'Network error'}`);
        }
    };

    const renderMenuItem = ({ item }: { item: any }) => (
        <View style={styles.menuItem}>
            <View style={styles.itemInfo}>
                <Text style={styles.itemName}>{item.name}</Text>
                <Text style={styles.itemDesc}>{item.description}</Text>
                <Text style={styles.itemPrice}>${(item.price_cents / 100).toFixed(2)}</Text>
            </View>
            <TouchableOpacity style={styles.addButton} onPress={() => addToCart(item)}>
                <Text style={styles.addButtonText}>+</Text>
            </TouchableOpacity>
        </View>
    );

    if (!restaurant?.restaurant_id) {
        return (
            <View style={styles.center}>
                <Text style={styles.emptyText}>Restaurant not selected</Text>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            {loading ? (
                <View style={styles.center}>
                    <ActivityIndicator size="large" color={theme.colors.primary} />
                </View>
            ) : (
                <FlatList
                    data={menuItems}
                    renderItem={renderMenuItem}
                    keyExtractor={item => item.id}
                    contentContainerStyle={styles.list}
                    ListEmptyComponent={<Text style={styles.emptyText}>No items available</Text>}
                />
            )}

            {cart.length > 0 && (
                <View style={styles.cartBar}>
                    <Text style={styles.cartText}>
                        {cart.reduce((sum, i) => sum + i.qty, 0)} items · ${(getCartTotal() / 100).toFixed(2)}
                    </Text>
                    <TouchableOpacity style={styles.orderButton} onPress={handlePlaceOrder}>
                        <Text style={styles.orderButtonText}>Place Order</Text>
                    </TouchableOpacity>
                </View>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: theme.colors.background },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
    emptyText: { textAlign: 'center', marginTop: 40, color: theme.colors.textMuted, fontSize: 16 },
    list: { padding: 16 },
    menuItem: {
        ...theme.layout.card,
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 20, /* Slightly taller */
        backgroundColor: '#fff',
    },
    itemInfo: { flex: 1 },
    itemName: { color: theme.colors.text, fontSize: 18, fontWeight: '600', fontFamily: theme.typography.header.fontFamily },
    itemDesc: { color: theme.colors.textMuted, fontSize: 14, marginTop: 4 },
    itemPrice: { color: theme.colors.accent, fontSize: 16, fontWeight: '700', marginTop: 8 },
    addButton: {
        width: 44,
        height: 44,
        borderRadius: 22,
        backgroundColor: theme.colors.primary,
        justifyContent: 'center',
        alignItems: 'center',
        shadowColor: theme.colors.primary,
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 5,
    },
    addButtonText: { color: '#fff', fontSize: 24, fontWeight: 'bold' },
    cartBar: {
        flexDirection: 'row',
        backgroundColor: '#fff',
        padding: 20,
        borderTopWidth: 1,
        borderTopColor: '#eee',
        alignItems: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: -4 },
        shadowOpacity: 0.05,
        shadowRadius: 10,
    },
    cartText: { flex: 1, color: theme.colors.text, fontSize: 16, fontWeight: '600' },
    orderButton: {
        backgroundColor: theme.colors.primary,
        paddingHorizontal: 24,
        paddingVertical: 12,
        borderRadius: 50,
    },
    orderButtonText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
