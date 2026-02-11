/**
 * Menu Screen
 * Agent Kappa: Order placement flow
 */
import React, { useState } from 'react';
import {
    View,
    Text,
    FlatList,
    TouchableOpacity,
    StyleSheet,
    Alert,
} from 'react-native';
import { createOrder } from '../services/api';
import { startLocationTracking, requestPermissions } from '../services/location';
import { theme } from '../theme';

// Demo menu items
const MENU_ITEMS = [
    { id: 'item_1', name: 'Signature Truffle Burger', price_cents: 1499, description: 'Wagyu beef, truffle aioli' },
    { id: 'item_2', name: 'Spicy Rigatoni', price_cents: 1850, description: 'Vodka sauce, calabrian chili' },
    { id: 'item_3', name: 'Crispy Brussels Sprouts', price_cents: 900, description: 'Honey balsamic glaze' },
    { id: 'item_4', name: 'Tiramisu', price_cents: 800, description: 'Espresso, mascarpone' },
    { id: 'item_5', name: 'Pinot Noir (Glass)', price_cents: 1200, description: 'Sonoma Coast, 2021' },
];

// Default restaurant location (Austin, TX) for GPS tracking
const DEFAULT_COORDS = { latitude: 30.2672, longitude: -97.7431 };

interface Props {
    navigation: any;
    route: any;
    onOrderPlaced: (order: any) => void;
}

export default function MenuScreen({ navigation, route, onOrderPlaced }: Props) {
    const [cart, setCart] = useState<any[]>([]);

    // Get restaurant and customer from navigation params
    const restaurant = route.params?.restaurant || { restaurant_id: 'rst_demo_001', name: 'AADI Bistro', emoji: '🍔' };
    const customerName = route.params?.customerName || 'Guest';

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
            console.log('[MenuScreen] Starting order placement...');

            // Create order FIRST - this is the critical path
            console.log('[MenuScreen] Calling createOrder API...');
            const order = await createOrder(restaurant.restaurant_id, cart, customerName);
            console.log('[MenuScreen] Order created successfully:', order.order_id);
            onOrderPlaced(order);

            // Navigate to order screen
            navigation.navigate('Order', { orderId: order.order_id });
            setCart([]);

            // Try location tracking in background (non-blocking)
            try {
                const hasPermission = await requestPermissions();
                if (hasPermission) {
                    startLocationTracking(
                        { latitude: DEFAULT_COORDS.latitude, longitude: DEFAULT_COORDS.longitude, restaurantId: restaurant.restaurant_id },
                        order.order_id,
                        (event, orderId) => console.log(`Arrival event: ${event} for ${orderId}`)
                    );
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

    return (
        <View style={styles.container}>
            <FlatList
                data={MENU_ITEMS}
                renderItem={renderMenuItem}
                keyExtractor={item => item.id}
                contentContainerStyle={styles.list}
            />

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
