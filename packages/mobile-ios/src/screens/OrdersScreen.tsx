import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
    ActivityIndicator,
    FlatList,
    RefreshControl,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';
import { theme } from '../theme';
import { Order, Restaurant } from '../services/api';
import { getMyOrdersWithCache } from '../services/orderHistory';
import { getRestaurantsWithCache } from '../services/restaurantsCatalog';

interface Props {
    navigation: any;
}

const STATUS_LABEL: Record<string, string> = {
    PENDING_NOT_SENT: 'Confirmed',
    SENT_TO_DESTINATION: 'Sent to kitchen',
    WAITING_FOR_CAPACITY: 'Queued',
    IN_PROGRESS: 'Preparing',
    READY: 'Ready',
    FULFILLING: 'Serving',
    COMPLETED: 'Completed',
    CANCELED: 'Canceled',
    DECLINED: 'Declined',
    EXPIRED: 'Expired',
};

function statusLabel(status: string | undefined): string {
    return STATUS_LABEL[String(status || '').toUpperCase()] || 'In progress';
}

function currency(cents: number | undefined): string {
    return `$${((Number(cents) || 0) / 100).toFixed(2)}`;
}

function orderPlacedAt(order: Order): string {
    const raw = order.updated_at || order.created_at;
    if (!raw) {
        return 'Recent';
    }

    const dt = new Date(raw);
    if (Number.isNaN(dt.getTime())) {
        return 'Recent';
    }

    return dt.toLocaleString();
}

export default function OrdersScreen({ navigation }: Props) {
    const [orders, setOrders] = useState<Order[]>([]);
    const [restaurants, setRestaurants] = useState<Record<string, Restaurant>>({});
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [fromCache, setFromCache] = useState(false);
    const [error, setError] = useState('');

    const restaurantsById = useMemo(() => restaurants, [restaurants]);

    const loadOrders = useCallback(async (forceRefresh = false) => {
        if (forceRefresh) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }

        try {
            const [ordersRes, restaurantList] = await Promise.all([
                getMyOrdersWithCache({ forceRefresh }),
                getRestaurantsWithCache({ forceRefresh }).then((result) => result.restaurants).catch(() => []),
            ]);

            const restaurantMap: Record<string, Restaurant> = {};
            restaurantList.forEach((restaurant) => {
                if (restaurant?.restaurant_id) {
                    restaurantMap[restaurant.restaurant_id] = restaurant;
                }
            });

            setRestaurants(restaurantMap);
            setOrders(Array.isArray(ordersRes.orders) ? ordersRes.orders : []);
            setFromCache(ordersRes.fromCache);
            setError('');

            // Stale-while-revalidate: if cache returned, silently refresh network.
            if (!forceRefresh && ordersRes.fromCache) {
                getMyOrdersWithCache({ forceRefresh: true })
                    .then((fresh) => {
                        setOrders(Array.isArray(fresh.orders) ? fresh.orders : []);
                        setFromCache(false);
                    })
                    .catch(() => {
                        // Keep cached view if background refresh fails.
                    });
            }
        } catch (err) {
            console.error('[OrdersScreen] Failed to load orders:', err);
            setError('Could not load your orders right now.');
        } finally {
            setRefreshing(false);
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadOrders(false);
    }, [loadOrders]);

    if (loading) {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" color={theme.colors.primary} />
                <Text style={styles.helper}>Loading your orders...</Text>
            </View>
        );
    }

    return (
        <View style={styles.container}>
            {fromCache ? (
                <View style={styles.cachePill}>
                    <Text style={styles.cacheText}>Showing cached orders. Pull to refresh.</Text>
                </View>
            ) : null}

            {error ? <Text style={styles.errorText}>{error}</Text> : null}

            <FlatList
                data={orders}
                keyExtractor={(item) => item.order_id}
                refreshControl={(
                    <RefreshControl
                        refreshing={refreshing}
                        onRefresh={() => loadOrders(true)}
                        tintColor={theme.colors.primary}
                    />
                )}
                ListEmptyComponent={(
                    <View style={styles.emptyWrap}>
                        <Text style={styles.emptyTitle}>No past orders yet</Text>
                        <Text style={styles.emptyBody}>When you place your first order, it will show up here.</Text>
                        <TouchableOpacity
                            style={styles.browseButton}
                            onPress={() => navigation.navigate('Home')}
                        >
                            <Text style={styles.browseText}>Browse restaurants</Text>
                        </TouchableOpacity>
                    </View>
                )}
                contentContainerStyle={orders.length === 0 ? styles.emptyList : styles.list}
                renderItem={({ item }) => {
                    const restaurant = restaurantsById[item.restaurant_id];
                    const totalItems = Array.isArray(item.items)
                        ? item.items.reduce((sum, orderItem) => sum + (Number(orderItem.qty) || 0), 0)
                        : 0;

                    return (
                        <TouchableOpacity
                            style={styles.card}
                            onPress={() => navigation.navigate('Order', { orderId: item.order_id })}
                        >
                            <View style={styles.cardHeader}>
                                <Text style={styles.restaurantName} numberOfLines={1}>
                                    {restaurant?.name || `Restaurant ${item.restaurant_id.slice(-6)}`}
                                </Text>
                                <Text style={styles.status}>{statusLabel(item.status)}</Text>
                            </View>

                            <Text style={styles.meta}>
                                {totalItems} item{totalItems === 1 ? '' : 's'} • {currency(item.total_cents)}
                            </Text>
                            <Text style={styles.meta}>{orderPlacedAt(item)}</Text>
                        </TouchableOpacity>
                    );
                }}
            />
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
        paddingHorizontal: theme.spacing.lg,
        paddingTop: theme.spacing.md,
    },
    center: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        backgroundColor: theme.colors.background,
    },
    helper: {
        ...theme.typography.body,
        color: theme.colors.textSecondary,
        marginTop: theme.spacing.md,
    },
    list: {
        paddingBottom: theme.spacing.xl,
    },
    cachePill: {
        alignSelf: 'flex-start',
        borderWidth: 1,
        borderColor: theme.colors.border,
        borderRadius: theme.radii.chip,
        paddingHorizontal: theme.spacing.sm,
        paddingVertical: theme.spacing.xs,
        marginBottom: theme.spacing.sm,
        backgroundColor: theme.colors.glassSurface,
    },
    cacheText: {
        ...theme.typography.caption,
        color: theme.colors.textSecondary,
    },
    errorText: {
        ...theme.typography.bodySm,
        color: theme.colors.error,
        marginBottom: theme.spacing.sm,
    },
    card: {
        ...theme.layout.card,
        marginBottom: theme.spacing.md,
        padding: theme.spacing.lg,
    },
    cardHeader: {
        flexDirection: 'row',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        gap: theme.spacing.sm,
    },
    restaurantName: {
        ...theme.typography.h3,
        color: theme.colors.text,
        flex: 1,
    },
    status: {
        ...theme.typography.caption,
        color: theme.colors.teal3,
        borderWidth: 1,
        borderColor: theme.colors.border,
        borderRadius: theme.radii.chip,
        paddingHorizontal: theme.spacing.sm,
        paddingVertical: theme.spacing.xs,
    },
    meta: {
        ...theme.typography.bodySm,
        color: theme.colors.textSecondary,
        marginTop: theme.spacing.xs,
    },
    emptyList: {
        flexGrow: 1,
    },
    emptyWrap: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: theme.spacing.xl,
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
        backgroundColor: theme.colors.surface,
        paddingHorizontal: theme.spacing.lg,
        paddingVertical: theme.spacing.md,
    },
    browseText: {
        ...theme.typography.body,
        color: theme.colors.text,
        fontWeight: '700',
    },
});
