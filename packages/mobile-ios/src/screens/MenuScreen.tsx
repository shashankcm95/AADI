/**
 * Menu Screen
 * Agent Kappa: Order placement flow
 */
import React, { useEffect, useLayoutEffect, useMemo, useState } from 'react';
import {
    View,
    Text,
    SectionList,
    TouchableOpacity,
    StyleSheet,
    Alert,
    ActivityIndicator,
} from 'react-native';
import { createOrder, getRestaurantMenu, Restaurant, sendArrivalEvent, sendLocationSample } from '../services/api';
import {
    getFavoritesWithCache,
    setFavoriteForCurrentUser,
} from '../services/favorites';
import { requestPermissions, startLocationTracking, stopLocationTracking } from '../services/location';
import { theme } from '../theme';
import { useCart } from '../state/CartContext';
import { upsertOrderInCache } from '../services/orderHistory';

interface Props {
    navigation: any;
    route: any;
}

export default function MenuScreen({ navigation, route }: Props) {
    const [menuItems, setMenuItems] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [placingOrder, setPlacingOrder] = useState(false);
    const [isFavorite, setIsFavorite] = useState(false);
    const [favoriteUpdating, setFavoriteUpdating] = useState(false);

    const restaurant: Restaurant | undefined = route.params?.restaurant;
    const customerName = route.params?.customerName || 'Guest';

    const {
        cartItems,
        cartRestaurant,
        cartCount,
        cartTotalCents,
        addItemToCart,
        forceAddItemToCart,
        clearCart,
        isCartForRestaurant,
    } = useCart();

    const isCurrentRestaurantCart = useMemo(() => {
        return isCartForRestaurant(restaurant?.restaurant_id);
    }, [isCartForRestaurant, restaurant?.restaurant_id]);

    const visibleCartItems = isCurrentRestaurantCart ? cartItems : [];
    const menuSections = useMemo(() => {
        const groups = new Map<string, any[]>();
        for (const item of menuItems) {
            const categoryName = String(item.category || '').trim() || 'Other';
            if (!groups.has(categoryName)) {
                groups.set(categoryName, []);
            }
            groups.get(categoryName)?.push(item);
        }
        return Array.from(groups.entries()).map(([title, data]) => ({ title, data }));
    }, [menuItems]);

    useLayoutEffect(() => {
        navigation.setOptions({
            headerRight: () => (
                <View style={styles.headerActions}>
                    <TouchableOpacity
                        onPress={handleToggleFavorite}
                        style={styles.headerFavoriteButton}
                        disabled={favoriteUpdating}
                    >
                        <Text style={styles.headerFavoriteText}>{isFavorite ? '♥' : '♡'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                        onPress={() => navigation.navigate('Cart')}
                        style={styles.headerCartButton}
                    >
                        <Text style={styles.headerCartText}>Cart{cartCount > 0 ? ` (${cartCount})` : ''}</Text>
                    </TouchableOpacity>
                </View>
            ),
        });
    }, [navigation, cartCount, isFavorite, favoriteUpdating]);

    useEffect(() => {
        if (!restaurant?.restaurant_id) {
            Alert.alert('Restaurant Missing', 'Please select a restaurant to continue.');
            navigation.goBack();
            return;
        }
        loadMenu();
        loadFavoriteStatus(restaurant.restaurant_id);
    }, [restaurant?.restaurant_id]);

    async function loadFavoriteStatus(restaurantId: string) {
        try {
            const favorites = await getFavoritesWithCache();
            setIsFavorite(favorites.favoriteRestaurantIds.includes(restaurantId));
        } catch {
            setIsFavorite(false);
        }
    }

    async function handleToggleFavorite() {
        const restaurantId = restaurant?.restaurant_id;
        if (!restaurantId || favoriteUpdating) {
            return;
        }

        const nextValue = !isFavorite;
        setIsFavorite(nextValue);
        setFavoriteUpdating(true);

        try {
            await setFavoriteForCurrentUser(restaurantId, nextValue);
        } catch (error) {
            setIsFavorite(!nextValue);
            Alert.alert('Favorites', 'Could not update favorites. Please try again.');
        } finally {
            setFavoriteUpdating(false);
        }
    }

    async function loadMenu() {
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
    }

    const addToCart = (item: any) => {
        if (!restaurant) {
            return;
        }

        const result = addItemToCart({ ...item, qty: 1 }, restaurant);
        if (result === 'added') {
            return;
        }

        Alert.alert(
            'Replace Existing Cart?',
            `Your cart has items from ${cartRestaurant?.name || 'another restaurant'}. Replace them with this item?`,
            [
                { text: 'Keep Current Cart', style: 'cancel' },
                {
                    text: 'Replace',
                    style: 'destructive',
                    onPress: () => {
                        forceAddItemToCart({ ...item, qty: 1 }, restaurant);
                    },
                },
            ]
        );
    };

    const handlePlaceOrder = async () => {
        if (visibleCartItems.length === 0) {
            Alert.alert('Cart Empty', 'Add some items first!');
            return;
        }

        try {
            if (!restaurant?.restaurant_id) {
                Alert.alert('Restaurant Missing', 'Please select a restaurant to continue.');
                return;
            }

            setPlacingOrder(true);
            const order = await createOrder(restaurant.restaurant_id, visibleCartItems, customerName);
            await upsertOrderInCache(order);

            navigation.navigate('Order', { orderId: order.order_id });
            clearCart();

            // Try location tracking in background (non-blocking)
            try {
                const hasPermission = await requestPermissions({ requestBackground: true });
                if (hasPermission) {
                    const hasCoordinates = Number.isFinite(restaurant.latitude) && Number.isFinite(restaurant.longitude);
                    if (hasCoordinates) {
                        await startLocationTracking(
                            {
                                latitude: Number(restaurant.latitude),
                                longitude: Number(restaurant.longitude),
                                restaurantId: restaurant.restaurant_id,
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
                                    console.warn('[MenuScreen] Failed to send arrival event:', arrivalError);
                                }
                            },
                            async (sampleOrderId, sample) => {
                                try {
                                    await sendLocationSample(sampleOrderId, sample);
                                } catch (sampleError) {
                                    console.warn('[MenuScreen] Failed to send location sample:', sampleError);
                                }
                            },
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
        } finally {
            setPlacingOrder(false);
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
            {!isCurrentRestaurantCart && cartItems.length > 0 ? (
                <TouchableOpacity style={styles.crossRestaurantBanner} onPress={() => navigation.navigate('Cart')}>
                    <Text style={styles.crossRestaurantText}>
                        You have {cartCount} item(s) in {cartRestaurant?.name || 'another cart'}.
                    </Text>
                    <Text style={styles.crossRestaurantLink}>Open Cart ›</Text>
                </TouchableOpacity>
            ) : null}

            {loading ? (
                <View style={styles.center}>
                    <ActivityIndicator size="large" color={theme.colors.primary} />
                </View>
            ) : (
                <SectionList
                    sections={menuSections}
                    renderItem={renderMenuItem}
                    renderSectionHeader={({ section }) => (
                        <View style={styles.sectionHeader}>
                            <Text style={styles.sectionTitle}>{section.title}</Text>
                        </View>
                    )}
                    keyExtractor={(item, index) => `${item.id || item.name || 'item'}-${index}`}
                    contentContainerStyle={styles.list}
                    ListEmptyComponent={<Text style={styles.emptyText}>No items available</Text>}
                    stickySectionHeadersEnabled={false}
                />
            )}

            {visibleCartItems.length > 0 && (
                <View style={styles.cartBar}>
                    <TouchableOpacity style={styles.cartSummary} onPress={() => navigation.navigate('Cart')}>
                        <Text style={styles.cartText}>{cartCount} items · ${(cartTotalCents / 100).toFixed(2)}</Text>
                        <Text style={styles.cartLink}>View Cart</Text>
                    </TouchableOpacity>

                    <TouchableOpacity
                        style={[styles.orderButton, placingOrder && styles.orderButtonDisabled]}
                        onPress={handlePlaceOrder}
                        disabled={placingOrder}
                    >
                        {placingOrder
                            ? <ActivityIndicator color={theme.colors.white} />
                            : <Text style={styles.orderButtonText}>Place Order</Text>}
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
    headerCartButton: {
        borderWidth: 1,
        borderColor: theme.colors.border,
        borderRadius: theme.radii.chip,
        paddingHorizontal: theme.spacing.sm,
        paddingVertical: theme.spacing.xs,
        backgroundColor: theme.colors.surface,
    },
    headerActions: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: theme.spacing.xs,
    },
    headerFavoriteButton: {
        borderWidth: 1,
        borderColor: theme.colors.border,
        borderRadius: theme.radii.chip,
        width: 34,
        height: 34,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: theme.colors.surface,
    },
    headerFavoriteText: {
        color: theme.colors.primary,
        fontSize: 18,
        lineHeight: 20,
    },
    headerCartText: {
        ...theme.typography.caption,
        color: theme.colors.text,
        fontWeight: '700',
    },
    crossRestaurantBanner: {
        marginHorizontal: theme.spacing.lg,
        marginTop: theme.spacing.sm,
        marginBottom: theme.spacing.xs,
        borderWidth: 1,
        borderColor: theme.colors.border,
        borderRadius: theme.radii.input,
        backgroundColor: theme.colors.glassSurface,
        paddingHorizontal: theme.spacing.md,
        paddingVertical: theme.spacing.sm,
    },
    crossRestaurantText: {
        ...theme.typography.bodySm,
        color: theme.colors.textSecondary,
    },
    crossRestaurantLink: {
        ...theme.typography.caption,
        color: theme.colors.primary,
        marginTop: theme.spacing.xs,
        fontWeight: '700',
    },
    menuItem: {
        ...theme.layout.card,
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 20,
        backgroundColor: '#fff',
    },
    itemInfo: { flex: 1 },
    itemName: { color: theme.colors.text, fontSize: 18, fontWeight: '600', fontFamily: theme.typography.header.fontFamily },
    itemDesc: { color: theme.colors.textMuted, fontSize: 14, marginTop: 4 },
    itemPrice: { color: theme.colors.accent, fontSize: 16, fontWeight: '700', marginTop: 8 },
    sectionHeader: {
        paddingTop: theme.spacing.sm,
        paddingBottom: theme.spacing.xs,
    },
    sectionTitle: {
        ...theme.typography.bodySm,
        color: theme.colors.textSecondary,
        fontWeight: '700',
        textTransform: 'uppercase',
        letterSpacing: 0.5,
    },
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
        paddingHorizontal: 16,
        paddingVertical: 12,
        borderTopWidth: 1,
        borderTopColor: '#eee',
        alignItems: 'center',
        gap: 10,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: -4 },
        shadowOpacity: 0.05,
        shadowRadius: 10,
    },
    cartSummary: {
        flex: 1,
    },
    cartText: {
        ...theme.typography.body,
        color: theme.colors.text,
        fontWeight: '700',
    },
    cartLink: {
        ...theme.typography.caption,
        color: theme.colors.primary,
        marginTop: 2,
    },
    orderButton: {
        backgroundColor: theme.colors.primary,
        paddingHorizontal: 18,
        paddingVertical: 12,
        borderRadius: 50,
        minWidth: 130,
        alignItems: 'center',
    },
    orderButtonDisabled: {
        opacity: 0.7,
    },
    orderButtonText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
