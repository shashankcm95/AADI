import React, { useCallback, useMemo, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    FlatList,
    RefreshControl,
    StyleSheet,
    Text,
    TouchableOpacity,
    useWindowDimensions,
    View,
} from 'react-native';
import { RestaurantCard } from '../components/ui/RestaurantCard';
import { SkeletonBox } from '../components/ui/SkeletonBox';
import { EmptyState } from '../components/ui/EmptyState';
import { theme } from '../theme';
import { Restaurant } from '../services/api';
import {
    favoriteIdsToMap,
    getFavoritesWithCache,
    setFavoriteForCurrentUser,
} from '../services/favorites';
import { getRestaurantsWithCache } from '../services/restaurantsCatalog';

interface Props {
    navigation: any;
    route: any;
}

function primaryRestaurantImage(restaurant: Restaurant): { uri: string } | undefined {
    const uploaded = Array.isArray(restaurant.restaurant_images) ? restaurant.restaurant_images : [];
    const sourceUrl = uploaded[0] || restaurant.image_url;
    return sourceUrl ? { uri: sourceUrl } : undefined;
}

function asFallbackRestaurant(restaurantId: string): Restaurant {
    const normalizedId = String(restaurantId || '').trim();
    return {
        restaurant_id: normalizedId,
        name: `Restaurant ${normalizedId ? normalizedId.slice(-4) : 'N/A'}`,
        cuisine: 'Cuisine',
        rating: 0,
        emoji: '🍽️',
        address: '',
        tags: ['Cuisine'],
        price_tier: 2,
    };
}

export default function FavoritesScreen({ navigation, route }: Props) {
    const { width } = useWindowDimensions();
    const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
    const [favoriteIds, setFavoriteIds] = useState<string[]>([]);
    const [favorites, setFavorites] = useState<Record<string, boolean>>({});
    const [updating, setUpdating] = useState<Record<string, boolean>>({});
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [fromCache, setFromCache] = useState(false);
    const [error, setError] = useState('');

    const customerName = route?.params?.customerName || 'Guest';

    const loadFavorites = useCallback(async (forceRefresh = false) => {
        if (forceRefresh) {
            setRefreshing(true);
        } else {
            setLoading(true);
        }

        try {
            const [favoritesRes, restaurantsRes] = await Promise.all([
                getFavoritesWithCache({ forceRefresh }),
                getRestaurantsWithCache({ forceRefresh }).catch(() => ({ restaurants: [], fromCache: true, userId: '' })),
            ]);

            setFavoriteIds(favoritesRes.favoriteRestaurantIds);
            setFavorites(favoriteIdsToMap(favoritesRes.favoriteRestaurantIds));
            setFromCache(favoritesRes.fromCache);
            setRestaurants(restaurantsRes.restaurants || []);
            setError('');

            if (!forceRefresh && favoritesRes.fromCache) {
                getFavoritesWithCache({ forceRefresh: true })
                    .then((fresh) => {
                        setFavoriteIds(fresh.favoriteRestaurantIds);
                        setFavorites(favoriteIdsToMap(fresh.favoriteRestaurantIds));
                        setFromCache(false);
                    })
                    .catch(() => {
                        // Keep cached favorites visible if background refresh fails.
                    });
            }
        } catch (err) {
            console.error('[FavoritesScreen] Failed to load favorites:', err);
            setError('Could not load favorites right now.');
        } finally {
            setRefreshing(false);
            setLoading(false);
        }
    }, []);

    React.useEffect(() => {
        loadFavorites(false);
    }, [loadFavorites]);

    const restaurantsById = useMemo(() => {
        const map: Record<string, Restaurant> = {};
        restaurants.forEach((restaurant) => {
            if (restaurant?.restaurant_id) {
                map[restaurant.restaurant_id] = restaurant;
            }
        });
        return map;
    }, [restaurants]);

    const favoriteRestaurants = useMemo(() => {
        return favoriteIds.map((restaurantId) => restaurantsById[restaurantId] || asFallbackRestaurant(restaurantId));
    }, [favoriteIds, restaurantsById]);

    const isSmallPhone = width < 360;
    const cardLayout = isSmallPhone ? 'list' : 'grid';
    const cardWidth = isSmallPhone
        ? width - theme.screenPadding.horizontal * 2
        : (width - theme.screenPadding.horizontal * 2 - theme.spacing.md) / 2;

    const handleFavoriteToggle = async (restaurantId: string) => {
        if (!restaurantId || updating[restaurantId]) {
            return;
        }

        const wasFavorite = Boolean(favorites[restaurantId]);
        const nextFavoriteIds = favoriteIds.filter((id) => id !== restaurantId);

        setFavorites((current) => ({
            ...current,
            [restaurantId]: false,
        }));
        setFavoriteIds(nextFavoriteIds);
        setUpdating((current) => ({
            ...current,
            [restaurantId]: true,
        }));

        try {
            await setFavoriteForCurrentUser(restaurantId, false);
        } catch (err) {
            setFavorites((current) => ({
                ...current,
                [restaurantId]: wasFavorite,
            }));
            setFavoriteIds((current) => (current.includes(restaurantId) ? current : [restaurantId, ...current]));
            Alert.alert('Favorites', 'Could not update favorites. Please try again.');
        } finally {
            setUpdating((current) => {
                const next = { ...current };
                delete next[restaurantId];
                return next;
            });
        }
    };

    if (loading) {
        return (
            <View style={styles.skeletonContainer}>
                {Array.from({ length: 4 }).map((_, i) => (
                    <View key={`skel-${i}`} style={[styles.skeletonCard, { width: cardWidth }]}>
                        <SkeletonBox width="100%" height={140} borderRadius={12} />
                        <SkeletonBox width="70%" height={16} borderRadius={8} style={{ marginTop: 12 }} />
                        <SkeletonBox width="50%" height={12} borderRadius={6} style={{ marginTop: 8 }} />
                    </View>
                ))}
            </View>
        );
    }

    return (
        <View style={styles.container}>
            {fromCache ? (
                <View style={styles.cachePill}>
                    <Text style={styles.cacheText}>Showing cached favorites. Pull to refresh.</Text>
                </View>
            ) : null}

            {error ? <Text style={styles.errorText}>{error}</Text> : null}

            <FlatList
                data={favoriteRestaurants}
                key={isSmallPhone ? 'favorites-list' : 'favorites-grid'}
                numColumns={isSmallPhone ? 1 : 2}
                refreshControl={(
                    <RefreshControl
                        refreshing={refreshing}
                        onRefresh={() => loadFavorites(true)}
                        tintColor={theme.colors.primary}
                    />
                )}
                contentContainerStyle={favoriteRestaurants.length === 0 ? styles.emptyList : styles.list}
                columnWrapperStyle={isSmallPhone ? undefined : styles.gridRow}
                keyExtractor={(item) => item.restaurant_id}
                ListEmptyComponent={(
                    <EmptyState
                        emoji="❤️"
                        title="No favorites yet"
                        subtitle="Tap the heart on a restaurant to save it"
                        buttonLabel="Browse restaurants"
                        onButtonPress={() => navigation.navigate('Home', { customerName })}
                    />
                )}
                renderItem={({ item, index }) => {
                    const image = primaryRestaurantImage(item);

                    const priceTier = item.price_tier || 2;
                    const cuisineTag = item.cuisine || 'Cuisine';

                    return (
                        <View
                            style={[
                                styles.cardWrap,
                                {
                                    width: cardWidth,
                                },
                            ]}
                        >
                            <RestaurantCard
                                name={item.name || 'Restaurant'}
                                image={image}
                                tags={item.tags && item.tags.length ? item.tags : [cuisineTag]}
                                isFavorite={Boolean(favorites[item.restaurant_id])}
                                onFavoriteToggle={() => handleFavoriteToggle(item.restaurant_id)}
                                layout={cardLayout}
                                cuisine={cuisineTag}
                                priceTier={priceTier}
                                emoji={item.emoji || '🍽️'}
                                onPress={() => navigation.navigate('Menu', { restaurant: item, customerName })}
                            />
                        </View>
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
        paddingHorizontal: theme.screenPadding.horizontal,
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
    gridRow: {
        justifyContent: 'space-between',
        marginBottom: theme.spacing.md,
    },
    cardWrap: {
        marginBottom: theme.spacing.md,
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
    emptyList: {
        flexGrow: 1,
    },
    skeletonContainer: {
        flex: 1,
        flexDirection: 'row',
        flexWrap: 'wrap',
        justifyContent: 'space-between',
        paddingHorizontal: theme.screenPadding.horizontal,
        paddingTop: theme.spacing.lg,
    },
    skeletonCard: {
        marginBottom: theme.spacing.md,
        borderRadius: theme.radii.card,
        backgroundColor: theme.colors.surface,
        padding: theme.spacing.md,
    },
});
