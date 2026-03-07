import React, { useEffect, useMemo, useState } from 'react';
import {
    Alert,
    RefreshControl,
    ScrollView,
    StyleSheet,
    Text,
    TouchableOpacity,
    useWindowDimensions,
    View,
    ImageSourcePropType,
} from 'react-native';
import { theme } from '../theme';
import { PeacockHeader } from '../components/ui/PeacockHeader';
import { SearchBar } from '../components/ui/SearchBar';
import { CategoryChip } from '../components/ui/CategoryChip';
import { PromoBannerCard } from '../components/ui/PromoBannerCard';
import { RestaurantCard } from '../components/ui/RestaurantCard';
// BottomTabBar removed — tabs now handled by React Navigation in App.tsx
import { PrimaryButton } from '../components/ui/PrimaryButton';
import { Restaurant } from '../services/api';
import {
    favoriteIdsToMap,
    getFavoritesWithCache,
    setFavoriteForCurrentUser,
} from '../services/favorites';
import { getRestaurantsWithCache } from '../services/restaurantsCatalog';
import { useCart } from '../state/CartContext';

type Props = {
    navigation: any;
    route: any;
};

const ALL_TAG = 'All';

// Tab items now defined in App.tsx via createBottomTabNavigator

function primaryRestaurantImage(restaurant: Restaurant): ImageSourcePropType | undefined {
    const firstUploaded = Array.isArray(restaurant.restaurant_images) ? restaurant.restaurant_images[0] : undefined;
    const sourceUrl = firstUploaded || restaurant.image_url;
    return sourceUrl ? { uri: sourceUrl } : undefined;
}

// bannerRestaurantImage removed — banner now uses static background asset

export const HomeScreen: React.FC<Props> = ({ navigation, route }) => {
    const { width } = useWindowDimensions();
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState(ALL_TAG);
    const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
    const [favorites, setFavorites] = useState<Record<string, boolean>>({});
    const [favoriteUpdating, setFavoriteUpdating] = useState<Record<string, boolean>>({});
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [restaurantsError, setRestaurantsError] = useState('');
    const { cartCount } = useCart();

    useEffect(() => {
        loadHomeData();
    }, []);

    const loadHomeData = async () => {
        setLoading(true);
        setRestaurantsError('');

        try {
            const [restaurantRes, favoritesRes] = await Promise.allSettled([
                getRestaurantsWithCache(),
                getFavoritesWithCache(),
            ]);

            if (restaurantRes.status === 'fulfilled') {
                setRestaurants(restaurantRes.value.restaurants || []);
                setRestaurantsError('');

                if (restaurantRes.value.fromCache) {
                    getRestaurantsWithCache({ forceRefresh: true })
                        .then((fresh) => {
                            setRestaurants(fresh.restaurants || []);
                            setRestaurantsError('');
                        })
                        .catch(() => {
                            // Keep cached restaurants if background refresh fails.
                        });
                }
            } else {
                console.error('Failed to load restaurants:', restaurantRes.reason);
                setRestaurants([]);
                setRestaurantsError('Could not connect to restaurants. Check your connection and try again.');
            }

            if (favoritesRes.status === 'fulfilled') {
                setFavorites(favoriteIdsToMap(favoritesRes.value.favoriteRestaurantIds));
            } else {
                console.warn('Failed to load favorites:', favoritesRes.reason);
                setFavorites({});
            }
        } finally {
            setLoading(false);
        }
    };

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            const [restaurantRes, favoritesRes] = await Promise.allSettled([
                getRestaurantsWithCache({ forceRefresh: true }),
                getFavoritesWithCache({ forceRefresh: true }),
            ]);
            if (restaurantRes.status === 'fulfilled') {
                setRestaurants(restaurantRes.value.restaurants || []);
                setRestaurantsError('');
            }
            if (favoritesRes.status === 'fulfilled') {
                setFavorites(favoriteIdsToMap(favoritesRes.value.favoriteRestaurantIds));
            }
        } finally {
            setRefreshing(false);
        }
    };

    const availableTags = useMemo(() => {
        const tagSet = new Set<string>();
        for (const r of restaurants) {
            if (!r?.restaurant_id) continue;
            if (r.cuisine) tagSet.add(r.cuisine);
            if (Array.isArray(r.tags)) {
                for (const t of r.tags) {
                    if (t) tagSet.add(t);
                }
            }
        }
        const sorted = Array.from(tagSet).sort((a, b) => a.localeCompare(b));
        return [ALL_TAG, ...sorted];
    }, [restaurants]);

    const tagCounts = useMemo(() => {
        const counts: Record<string, number> = {};
        const valid = restaurants.filter((r) => r?.restaurant_id);
        counts[ALL_TAG] = valid.length;
        for (const tag of availableTags) {
            if (tag === ALL_TAG) continue;
            counts[tag] = valid.filter(
                (r) => r.cuisine === tag || (Array.isArray(r.tags) && r.tags.includes(tag)),
            ).length;
        }
        return counts;
    }, [restaurants, availableTags]);

    const filteredRestaurants = useMemo(() => {
        const normalizedSearch = searchQuery.trim().toLowerCase();

        return restaurants.filter((restaurant) => {
            if (!restaurant?.restaurant_id) return false;

            const probe = `${restaurant.name ?? ''} ${restaurant.cuisine ?? ''} ${(restaurant.tags || []).join(' ')}`.toLowerCase();
            const matchesSearch = !normalizedSearch || probe.includes(normalizedSearch);

            let matchesTag = true;
            if (selectedCategory !== ALL_TAG) {
                matchesTag =
                    restaurant.cuisine === selectedCategory ||
                    (Array.isArray(restaurant.tags) && restaurant.tags.includes(selectedCategory));
            }

            return matchesSearch && matchesTag;
        });
    }, [restaurants, searchQuery, selectedCategory]);

    const isSmallPhone = width < 360;
    const cardLayout = isSmallPhone ? 'list' : 'grid';
    const cardWidth = isSmallPhone
        ? width - theme.screenPadding.horizontal * 2
        : (width - theme.screenPadding.horizontal * 2 - theme.spacing.md) / 2;

    const handleFavoriteToggle = async (restaurantId: string) => {
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

    const renderCardSkeletons = () => {
        const count = isSmallPhone ? 3 : 4;

        return (
            <View style={styles.grid}>
                {Array.from({ length: count }).map((_, index) => (
                    <View
                        key={`skeleton-${index}`}
                        style={[
                            styles.skeletonCard,
                            {
                                width: cardWidth,
                                marginRight: !isSmallPhone && index % 2 === 0 ? theme.spacing.md : 0,
                            },
                        ]}
                    >
                        <View style={styles.skeletonImage} />
                        <View style={styles.skeletonLineLg} />
                        <View style={styles.skeletonLineMd} />
                        <View style={styles.skeletonPill} />
                    </View>
                ))}
            </View>
        );
    };

    const renderRestaurantGrid = () => {
        if (loading) {
            return renderCardSkeletons();
        }

        if (restaurantsError && restaurants.length === 0) {
            return (
                <View style={styles.emptyState}>
                    <Text style={styles.emptyTitle}>Unable to load restaurants</Text>
                    <Text style={styles.emptySubtitle}>{restaurantsError}</Text>
                    <PrimaryButton
                        label="Retry"
                        onPress={loadHomeData}
                        style={styles.emptyButton}
                    />
                </View>
            );
        }

        if (filteredRestaurants.length === 0) {
            return (
                <View style={styles.emptyState}>
                    <Text style={styles.emptyTitle}>No results near your location</Text>
                    <Text style={styles.emptySubtitle}>Try a different search or update your delivery area.</Text>
                    <PrimaryButton
                        label="Browse all restaurants"
                        onPress={() => {
                            setSelectedCategory(ALL_TAG);
                            setSearchQuery('');
                        }}
                        style={styles.emptyButton}
                    />
                </View>
            );
        }

        return (
            <View style={styles.grid}>
                {filteredRestaurants.map((restaurant, index) => {
                    const image = primaryRestaurantImage(restaurant);
                    const priceTier = restaurant.price_tier || 2;
                    const cuisineTag = restaurant.cuisine || 'Cuisine';
                    return (
                        <View
                            key={restaurant.restaurant_id}
                            style={[
                                styles.cardWrap,
                                {
                                    width: cardWidth,
                                    marginRight: !isSmallPhone && index % 2 === 0 ? theme.spacing.md : 0,
                                },
                            ]}
                        >
                            <RestaurantCard
                                name={restaurant.name || 'Restaurant'}
                                image={image}
                                tags={restaurant.tags && restaurant.tags.length ? restaurant.tags : [cuisineTag]}
                                isFavorite={Boolean(favorites[restaurant.restaurant_id])}
                                onFavoriteToggle={() => handleFavoriteToggle(restaurant.restaurant_id)}
                                layout={cardLayout}
                                cuisine={cuisineTag}
                                priceTier={priceTier}
                                emoji={restaurant.emoji || '🍽️'}
                                onPress={() =>
                                    navigation?.navigate?.('Menu', {
                                        restaurant,
                                        customerName: route?.params?.customerName || 'Guest',
                                    })
                                }
                            />
                        </View>
                    );
                })}
            </View>
        );
    };

    return (
        <View style={styles.container}>
            <PeacockHeader
                title="AADI"
                rightIcon={<Text style={styles.headerIcon}>🛒</Text>}
                rightBadgeCount={cartCount}
                onRightPress={() => navigation.navigate('Cart')}
            >
                <SearchBar
                    value={searchQuery}
                    onChange={setSearchQuery}
                    placeholder="Search by name or cuisine"
                    rightIcon={<Text style={styles.searchRightIcon}>⌄</Text>}
                    style={styles.searchBar}
                />

                <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.chipRow}
                >
                    {availableTags.map((tag) => (
                        <CategoryChip
                            key={tag}
                            label={tag}
                            count={tagCounts[tag] || 0}
                            selected={selectedCategory === tag}
                            onPress={() => setSelectedCategory(tag)}
                            onTintedBackground
                        />
                    ))}
                </ScrollView>
            </PeacockHeader>

            <View style={styles.contentArea}>
                <ScrollView
                    showsVerticalScrollIndicator={false}
                    contentContainerStyle={styles.scrollContent}
                    keyboardDismissMode="on-drag"
                    keyboardShouldPersistTaps="handled"
                    refreshControl={
                        <RefreshControl
                            refreshing={refreshing}
                            onRefresh={handleRefresh}
                            tintColor={theme.colors.primary}
                        />
                    }
                >
                    <View style={styles.section}>
                        {loading ? (
                            <View style={styles.skeletonBanner} />
                        ) : (
                            <PromoBannerCard
                                title="Explore Nearby"
                                subtitle="Up to 50% Off"
                                ctaLabel="Browse Restaurants"
                                onPress={() => {}}
                            />
                        )}
                    </View>

                    <View style={styles.sectionHeader}>
                        <Text style={styles.sectionTitle}>Popular Near You</Text>
                        <TouchableOpacity onPress={() => navigation.getParent()?.navigate('Browse')}>
                            <Text style={styles.seeAll}>See all ›</Text>
                        </TouchableOpacity>
                    </View>

                    {renderRestaurantGrid()}
                </ScrollView>
            </View>
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
    },
    headerIcon: {
        color: theme.colors.white,
        fontSize: 20,
    },
    searchRightIcon: {
        ...theme.typography.h2,
        color: theme.colors.textSecondary,
        lineHeight: 18,
    },
    searchBar: {
        marginTop: theme.spacing.sm,
    },
    chipRow: {
        paddingTop: theme.spacing.sm,
        paddingBottom: theme.spacing.xs,
    },
    contentArea: {
        flex: 1,
    },
    scrollContent: {
        paddingHorizontal: theme.screenPadding.horizontal,
        paddingTop: theme.spacing.lg,
        paddingBottom: theme.spacing.lg,
    },
    section: {
        marginBottom: theme.screenPadding.sectionGap,
    },
    sectionHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: theme.spacing.md,
    },
    sectionTitle: {
        ...theme.typography.h2,
        color: theme.colors.text,
    },
    seeAll: {
        ...theme.typography.body,
        color: theme.colors.textSecondary,
    },
    grid: {
        flexDirection: 'row',
        flexWrap: 'wrap',
    },
    cardWrap: {
        marginBottom: theme.spacing.md,
    },
    skeletonBanner: {
        height: 190,
        borderRadius: theme.radii.card,
        backgroundColor: theme.colors.overlayTopTint,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    skeletonCard: {
        marginBottom: theme.spacing.md,
        borderRadius: theme.radii.card,
        backgroundColor: theme.colors.surface,
        borderWidth: 1,
        borderColor: theme.colors.border,
        padding: theme.spacing.md,
    },
    skeletonImage: {
        height: 128,
        borderRadius: theme.radii.input,
        backgroundColor: theme.colors.overlayTopTint,
        marginBottom: theme.spacing.sm,
    },
    skeletonLineLg: {
        height: 18,
        width: '72%',
        borderRadius: theme.radii.chip,
        backgroundColor: theme.colors.overlayTopTint,
        marginBottom: theme.spacing.xs,
    },
    skeletonLineMd: {
        height: 14,
        width: '88%',
        borderRadius: theme.radii.chip,
        backgroundColor: theme.colors.overlayTopTint,
        marginBottom: theme.spacing.sm,
    },
    skeletonPill: {
        height: 24,
        width: 110,
        borderRadius: theme.radii.chip,
        backgroundColor: theme.colors.overlayTopTint,
    },
    emptyState: {
        padding: theme.spacing.xl,
        borderRadius: theme.radii.card,
        borderWidth: 1,
        borderColor: theme.colors.border,
        backgroundColor: theme.colors.glassSurface,
        alignItems: 'center',
    },
    emptyTitle: {
        ...theme.typography.h3,
        color: theme.colors.text,
        marginBottom: theme.spacing.xs,
        textAlign: 'center',
    },
    emptySubtitle: {
        ...theme.typography.body,
        color: theme.colors.textSecondary,
        textAlign: 'center',
    },
    emptyButton: {
        marginTop: theme.spacing.lg,
        width: '100%',
    },
});
