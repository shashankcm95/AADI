import React, { useEffect, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    FlatList,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';
import { theme } from '../theme';
import { createOrder, sendArrivalEvent, sendLocationSample } from '../services/api';
import { upsertOrderInCache } from '../services/orderHistory';
import { getCurrentUserProfile } from '../services/session';
import { requestPermissions, startLocationTracking, stopLocationTracking } from '../services/location';
import { useCart } from '../state/CartContext';

interface Props {
    navigation: any;
}

function money(cents: number): string {
    return `$${(cents / 100).toFixed(2)}`;
}

export default function CartScreen({ navigation }: Props) {
    const {
        cartItems,
        cartRestaurant,
        cartCount,
        cartTotalCents,
        setItemQty,
        removeItem,
        clearCart,
    } = useCart();

    const [placingOrder, setPlacingOrder] = useState(false);
    const [customerName, setCustomerName] = useState('Customer');

    useEffect(() => {
        getCurrentUserProfile()
            .then((profile) => setCustomerName(profile.displayName || 'Customer'))
            .catch(() => setCustomerName('Customer'));
    }, []);

    const onCheckout = async () => {
        if (!cartRestaurant || cartItems.length === 0) {
            Alert.alert('Cart Empty', 'Please add items before checkout.');
            return;
        }

        setPlacingOrder(true);
        try {
            const order = await createOrder(cartRestaurant.restaurant_id, cartItems, customerName);
            await upsertOrderInCache(order);

            // Keep existing background location behavior for arrival events.
            try {
                const hasPermission = await requestPermissions({ requestBackground: true });
                if (hasPermission && Number.isFinite(cartRestaurant.latitude) && Number.isFinite(cartRestaurant.longitude)) {
                    await startLocationTracking(
                        {
                            latitude: Number(cartRestaurant.latitude),
                            longitude: Number(cartRestaurant.longitude),
                            restaurantId: cartRestaurant.restaurant_id,
                        },
                        order.order_id,
                        async (event, eventOrderId) => {
                            if (!['5_MIN_OUT', 'PARKING', 'AT_DOOR'].includes(event)) {
                                return;
                            }

                            if (event === 'AT_DOOR') {
                                await stopLocationTracking();
                            }

                            try {
                                await sendArrivalEvent(eventOrderId, event);
                            } catch (arrivalError) {
                                console.warn('[CartScreen] Failed to send arrival event:', arrivalError);
                            }
                        },
                        async (sampleOrderId, sample) => {
                            try {
                                await sendLocationSample(sampleOrderId, sample);
                            } catch (sampleError) {
                                console.warn('[CartScreen] Failed to send location sample:', sampleError);
                            }
                        },
                    );
                }
            } catch (locErr) {
                console.warn('[CartScreen] Location tracking skipped:', locErr);
            }

            clearCart();
            navigation.navigate('Order', { orderId: order.order_id });
        } catch (error: any) {
            console.error('[CartScreen] Checkout failed:', error);
            Alert.alert('Checkout Failed', error?.message || 'Please try again.');
        } finally {
            setPlacingOrder(false);
        }
    };

    if (cartItems.length === 0) {
        return (
            <View style={styles.emptyWrap}>
                <Text style={styles.emptyTitle}>Your cart is empty</Text>
                <Text style={styles.emptyBody}>Add items from a menu to continue checkout.</Text>
                <TouchableOpacity style={styles.browseButton} onPress={() => navigation.navigate('Home')}>
                    <Text style={styles.browseText}>Browse restaurants</Text>
                </TouchableOpacity>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            <View style={styles.headerCard}>
                <Text style={styles.restaurantName}>{cartRestaurant?.name || 'Your Cart'}</Text>
                <Text style={styles.meta}>{cartCount} items</Text>
            </View>

            <FlatList
                data={cartItems}
                keyExtractor={(item) => item.cart_item_key}
                contentContainerStyle={styles.list}
                renderItem={({ item }) => (
                    <View style={styles.itemCard}>
                        <View style={styles.itemBody}>
                            <Text style={styles.itemName}>{item.name}</Text>
                            {item.description ? <Text style={styles.itemDesc}>{item.description}</Text> : null}
                            <Text style={styles.itemPrice}>{money((item.price_cents || 0) * (item.qty || 0))}</Text>
                        </View>

                        <View style={styles.qtyWrap}>
                            <TouchableOpacity style={styles.qtyButton} onPress={() => setItemQty(item.cart_item_key, item.qty - 1)}>
                                <Text style={styles.qtyText}>-</Text>
                            </TouchableOpacity>
                            <Text style={styles.qtyValue}>{item.qty}</Text>
                            <TouchableOpacity style={styles.qtyButton} onPress={() => setItemQty(item.cart_item_key, item.qty + 1)}>
                                <Text style={styles.qtyText}>+</Text>
                            </TouchableOpacity>
                            <TouchableOpacity style={styles.removeButton} onPress={() => removeItem(item.cart_item_key)}>
                                <Text style={styles.removeText}>Remove</Text>
                            </TouchableOpacity>
                        </View>
                    </View>
                )}
            />

            <View style={styles.checkoutBar}>
                <View>
                    <Text style={styles.totalLabel}>Total</Text>
                    <Text style={styles.totalValue}>{money(cartTotalCents)}</Text>
                </View>

                <TouchableOpacity
                    style={[styles.checkoutButton, placingOrder && styles.checkoutButtonDisabled]}
                    onPress={onCheckout}
                    disabled={placingOrder}
                >
                    {placingOrder ? (
                        <ActivityIndicator color={theme.colors.white} />
                    ) : (
                        <Text style={styles.checkoutText}>Place Order</Text>
                    )}
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
    },
    headerCard: {
        ...theme.layout.card,
        marginHorizontal: theme.spacing.lg,
        marginTop: theme.spacing.md,
        marginBottom: theme.spacing.sm,
    },
    restaurantName: {
        ...theme.typography.h3,
        color: theme.colors.text,
    },
    meta: {
        ...theme.typography.bodySm,
        color: theme.colors.textSecondary,
        marginTop: theme.spacing.xs,
    },
    list: {
        paddingHorizontal: theme.spacing.lg,
        paddingBottom: theme.spacing.xl,
    },
    itemCard: {
        ...theme.layout.card,
        marginBottom: theme.spacing.md,
        padding: theme.spacing.lg,
    },
    itemBody: {
        marginBottom: theme.spacing.md,
    },
    itemName: {
        ...theme.typography.body,
        color: theme.colors.text,
        fontWeight: '700',
    },
    itemDesc: {
        ...theme.typography.bodySm,
        color: theme.colors.textSecondary,
        marginTop: theme.spacing.xs,
    },
    itemPrice: {
        ...theme.typography.body,
        color: theme.colors.primary,
        marginTop: theme.spacing.xs,
        fontWeight: '700',
    },
    qtyWrap: {
        flexDirection: 'row',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: theme.spacing.sm,
    },
    qtyButton: {
        width: 32,
        height: 32,
        borderRadius: 16,
        borderWidth: 1,
        borderColor: theme.colors.border,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: theme.colors.surface,
    },
    qtyText: {
        ...theme.typography.h3,
        color: theme.colors.text,
        lineHeight: 18,
    },
    qtyValue: {
        ...theme.typography.body,
        color: theme.colors.text,
        minWidth: 20,
        textAlign: 'center',
        fontWeight: '700',
    },
    removeButton: {
        marginLeft: 'auto',
    },
    removeText: {
        ...theme.typography.bodySm,
        color: theme.colors.error,
        fontWeight: '600',
    },
    checkoutBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingHorizontal: theme.spacing.lg,
        paddingVertical: theme.spacing.md,
        borderTopWidth: 1,
        borderTopColor: theme.colors.border,
        backgroundColor: theme.colors.surface,
    },
    totalLabel: {
        ...theme.typography.bodySm,
        color: theme.colors.textSecondary,
    },
    totalValue: {
        ...theme.typography.h2,
        color: theme.colors.text,
    },
    checkoutButton: {
        minWidth: 160,
        paddingHorizontal: theme.spacing.lg,
        paddingVertical: theme.spacing.md,
        borderRadius: theme.radii.button,
        backgroundColor: theme.colors.primary,
        alignItems: 'center',
        justifyContent: 'center',
    },
    checkoutButtonDisabled: {
        opacity: 0.6,
    },
    checkoutText: {
        ...theme.typography.body,
        color: theme.colors.white,
        fontWeight: '700',
    },
    emptyWrap: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        padding: theme.spacing.xl,
        backgroundColor: theme.colors.background,
    },
    emptyTitle: {
        ...theme.typography.h2,
        color: theme.colors.text,
        textAlign: 'center',
    },
    emptyBody: {
        ...theme.typography.body,
        color: theme.colors.textSecondary,
        marginTop: theme.spacing.sm,
        textAlign: 'center',
    },
    browseButton: {
        marginTop: theme.spacing.lg,
        borderRadius: theme.radii.button,
        borderWidth: 1,
        borderColor: theme.colors.border,
        paddingHorizontal: theme.spacing.lg,
        paddingVertical: theme.spacing.md,
        backgroundColor: theme.colors.surface,
    },
    browseText: {
        ...theme.typography.body,
        color: theme.colors.text,
        fontWeight: '700',
    },
});
