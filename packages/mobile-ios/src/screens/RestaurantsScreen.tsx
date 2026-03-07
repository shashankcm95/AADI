/**
 * Restaurants Screen
 * Shows list of available restaurants to order from
 */
import React, { useEffect, useState } from 'react';
import {
    View,
    Text,
    FlatList,
    TouchableOpacity,
    StyleSheet,
    Alert,
    Image,
} from 'react-native';
import { Restaurant } from '../services/api';
import {
    favoriteIdsToMap,
    getFavoritesWithCache,
    setFavoriteForCurrentUser,
} from '../services/favorites';
import { getRestaurantsWithCache } from '../services/restaurantsCatalog';
import { SkeletonBox } from '../components/ui/SkeletonBox';
import { theme } from '../theme';

interface Props {
    navigation: any;
    route: any;
}

function primaryRestaurantImage(restaurant: Restaurant): { uri: string } | undefined {
    const uploaded = Array.isArray(restaurant.restaurant_images) ? restaurant.restaurant_images : [];
    const sourceUrl = uploaded[0] || restaurant.image_url;
    return sourceUrl ? { uri: sourceUrl } : undefined;
}

export default function RestaurantsScreen({ navigation, route }: Props) {
    const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
    const [favorites, setFavorites] = useState<Record<string, boolean>>({});
    const [favoriteUpdating, setFavoriteUpdating] = useState<Record<string, boolean>>({});
    const [loading, setLoading] = useState(true);
    const { customerName } = route.params || {};

    useEffect(() => {
        loadRestaurants();
    }, []);

    const loadRestaurants = async () => {
        try {
            const [restaurantsRes, favoritesRes] = await Promise.allSettled([
                getRestaurantsWithCache(),
                getFavoritesWithCache(),
            ]);

            if (restaurantsRes.status === 'fulfilled') {
                setRestaurants(restaurantsRes.value.restaurants || []);

                if (restaurantsRes.value.fromCache) {
                    getRestaurantsWithCache({ forceRefresh: true })
                        .then((fresh) => {
                            setRestaurants(fresh.restaurants || []);
                        })
                        .catch(() => {
                            // Keep cached restaurants if background refresh fails.
                        });
                }
            } else {
                console.error('Failed to load restaurants:', restaurantsRes.reason);
                setRestaurants([]);
            }

            if (favoritesRes.status === 'fulfilled') {
                setFavorites(favoriteIdsToMap(favoritesRes.value.favoriteRestaurantIds));
            } else {
                setFavorites({});
            }
        } finally {
            setLoading(false);
        }
    };

    const handleSelectRestaurant = (restaurant: Restaurant) => {
        navigation.navigate('Menu', {
            restaurant,
            customerName,
        });
    };

    const handleToggleFavorite = async (restaurantId: string) => {
        if (!restaurantId || favoriteUpdating[restaurantId]) {
            return;
        }

        const nextValue = !Boolean(favorites[restaurantId]);
        setFavorites((current) => ({
            ...current,
            [restaurantId]: nextValue,
        }));
        setFavoriteUpdating((current) => ({
            ...current,
            [restaurantId]: true,
        }));

        try {
            await setFavoriteForCurrentUser(restaurantId, nextValue);
        } catch (error) {
            setFavorites((current) => ({
                ...current,
                [restaurantId]: !nextValue,
            }));
            Alert.alert('Favorites', 'Could not update favorites. Please try again.');
        } finally {
            setFavoriteUpdating((current) => {
                const next = { ...current };
                delete next[restaurantId];
                return next;
            });
        }
    };

    const renderRestaurant = ({ item }: { item: Restaurant }) => {
        const coverImage = primaryRestaurantImage(item)

        return (
            <TouchableOpacity
                style={styles.card}
                onPress={() => handleSelectRestaurant(item)}
            >
                {coverImage ? (
                    <Image source={coverImage} style={styles.thumbnail} resizeMode="cover" />
                ) : (
                    <View style={styles.thumbnailFallback}>
                        <Text style={styles.emoji}>{item.emoji || '🍽️'}</Text>
                    </View>
                )}
                <View style={styles.info}>
                    <Text style={styles.name}>{item.name}</Text>
                    <Text style={styles.cuisine}>
                        {item.cuisine} • {'$'.repeat(item.price_tier || 1)} • {item.address}
                    </Text>
                    {/* Optional: Display tags if available handled in a robust way */}
                    {item.tags && item.tags.length > 0 && (
                        <Text style={styles.tags}>{item.tags.join(', ')}</Text>
                    )}
                    <View style={styles.ratingRow}>
                        <Text style={styles.star}>⭐</Text>
                        <Text style={styles.rating}>{item.rating}</Text>
                    </View>
                </View>
                <TouchableOpacity
                    style={styles.favoriteButton}
                    onPress={(event) => {
                        event.stopPropagation();
                        handleToggleFavorite(item.restaurant_id);
                    }}
                    accessibilityRole="button"
                >
                    <Text style={styles.favoriteText}>{favorites[item.restaurant_id] ? '♥' : '♡'}</Text>
                </TouchableOpacity>
            </TouchableOpacity>
        )
    };

    if (loading) {
        return (
            <View style={styles.container}>
                <Text style={styles.greeting}>Hi, {customerName || 'Guest'}! 👋</Text>
                <Text style={styles.title}>Where are you dining?</Text>
                {Array.from({ length: 4 }).map((_, i) => (
                    <View key={`skel-${i}`} style={styles.skeletonCard}>
                        <SkeletonBox width={62} height={62} borderRadius={14} />
                        <View style={{ flex: 1, marginLeft: 14 }}>
                            <SkeletonBox width="60%" height={16} borderRadius={8} />
                            <SkeletonBox width="80%" height={12} borderRadius={6} style={{ marginTop: 8 }} />
                            <SkeletonBox width="30%" height={12} borderRadius={6} style={{ marginTop: 8 }} />
                        </View>
                    </View>
                ))}
            </View>
        );
    }

    return (
        <View style={styles.container}>
            <Text style={styles.greeting}>Hi, {customerName || 'Guest'}! 👋</Text>
            <Text style={styles.title}>Where are you dining?</Text>

            <FlatList
                data={restaurants}
                renderItem={renderRestaurant}
                keyExtractor={(item) => item.restaurant_id}
                contentContainerStyle={styles.list}
                showsVerticalScrollIndicator={false}
            />
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
        padding: 20,
    },
    greeting: {
        fontSize: 16,
        color: theme.colors.textMuted,
        marginBottom: 4,
    },
    title: {
        fontSize: 28,
        fontWeight: '700',
        color: theme.colors.primary,
        marginBottom: 24,
        fontFamily: theme.typography.header.fontFamily,
    },
    list: {
        paddingBottom: 24,
    },
    card: {
        ...theme.layout.card,
        flexDirection: 'row',
        alignItems: 'center',
    },
    thumbnail: {
        width: 62,
        height: 62,
        borderRadius: 14,
        marginRight: 14,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    thumbnailFallback: {
        width: 62,
        height: 62,
        borderRadius: 14,
        marginRight: 14,
        backgroundColor: theme.colors.glassSurface,
        borderWidth: 1,
        borderColor: theme.colors.border,
        alignItems: 'center',
        justifyContent: 'center',
    },
    emoji: {
        fontSize: 30,
    },
    info: {
        flex: 1,
    },
    name: {
        fontSize: 18,
        fontWeight: '700',
        color: theme.colors.text,
        marginBottom: 4,
    },
    cuisine: {
        fontSize: 14,
        color: theme.colors.textMuted,
        marginBottom: 6,
    },
    tags: {
        fontSize: 12,
        color: theme.colors.primary,
        marginBottom: 4,
        fontWeight: '500',
    },
    ratingRow: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    star: {
        fontSize: 14,
        marginRight: 4,
    },
    rating: {
        fontSize: 14,
        color: theme.colors.accent,
        fontWeight: '600',
    },
    favoriteButton: {
        width: 36,
        height: 36,
        borderRadius: 18,
        borderWidth: 1,
        borderColor: theme.colors.border,
        backgroundColor: theme.colors.surface,
        alignItems: 'center',
        justifyContent: 'center',
        marginLeft: theme.spacing.sm,
    },
    favoriteText: {
        color: theme.colors.primary,
        fontSize: 20,
        lineHeight: 22,
    },
    skeletonCard: {
        ...theme.layout.card,
        flexDirection: 'row',
        alignItems: 'center',
    },
});
