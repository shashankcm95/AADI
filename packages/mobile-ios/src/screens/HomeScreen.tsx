import React, { useEffect, useMemo, useState } from 'react';
import {
    Alert,
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
import { BottomTabBar, BottomTabItem } from '../components/ui/BottomTabBar';
import { PrimaryButton } from '../components/ui/PrimaryButton';
import { SecondaryButton } from '../components/ui/SecondaryButton';
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

type Category = {
    id: string;
    label: string;
    icon: string;
};

const CATEGORIES: Category[] = [
    { id: 'restaurants', label: 'Restaurants', icon: '🍽️' },
    { id: 'grocery', label: 'Grocery', icon: '🛍️' },
    { id: 'alcohol', label: 'Alcohol', icon: '🍷' },
    { id: 'convenience', label: 'Convenience', icon: '🧃' },
];

const TAB_ITEMS: BottomTabItem[] = [
    { key: 'home', label: 'Home', icon: '⌂' },
    { key: 'browse', label: 'Browse', icon: '⌕' },
    { key: 'orders', label: 'Orders', icon: '🛒' },
    { key: 'favorites', label: 'Favorites', icon: '♥' },
    { key: 'profile', label: 'Profile', icon: '◉' },
];

function primaryRestaurantImage(restaurant: Restaurant): ImageSourcePropType | undefined {
    const firstUploaded = Array.isArray(restaurant.restaurant_images) ? restaurant.restaurant_images[0] : undefined;
    const sourceUrl = firstUploaded || restaurant.image_url;
    return sourceUrl ? { uri: sourceUrl } : undefined;
}

function bannerRestaurantImage(restaurant: Restaurant | undefined): ImageSourcePropType | undefined {
    if (!restaurant) {
        return undefined;
    }

    const uploaded = Array.isArray(restaurant.restaurant_images) ? restaurant.restaurant_images : [];
    const sourceUrl = uploaded[1] || uploaded[0] || restaurant.banner_image_url || restaurant.image_url;
    return sourceUrl ? { uri: sourceUrl } : undefined;
}

function matchesCategoryFilter(category: string, restaurant: Restaurant): boolean {
    if (category === 'restaurants') {
        return true;
    }

    const probe = `${restaurant.name ?? ''} ${restaurant.cuisine ?? ''} ${(restaurant.tags || []).join(' ')}`.toLowerCase();

    if (category === 'grocery') {
        return /(grocery|market|mart|fresh|produce)/.test(probe);
    }

    if (category === 'alcohol') {
        return /(bar|wine|beer|spirits|cocktail|pub)/.test(probe);
    }

    if (category === 'convenience') {
        return /(convenience|quick|snack|deli|corner)/.test(probe);
    }

    return true;
}

export const HomeScreen: React.FC<Props> = ({ navigation, route }) => {
    const { width } = useWindowDimensions();
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState('restaurants');
    const [activeTab, setActiveTab] = useState('home');
    const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
    const [favorites, setFavorites] = useState<Record<string, boolean>>({});
    const [favoriteUpdating, setFavoriteUpdating] = useState<Record<string, boolean>>({});
    const [loading, setLoading] = useState(true);
    const { cartCount } = useCart();

    useEffect(() => {
        loadHomeData();
    }, []);

    const loadHomeData = async () => {
        try {
            const [restaurantRes, favoritesRes] = await Promise.allSettled([
                getRestaurantsWithCache(),
                getFavoritesWithCache(),
            ]);

            if (restaurantRes.status === 'fulfilled') {
                setRestaurants(restaurantRes.value.restaurants || []);

                if (restaurantRes.value.fromCache) {
                    getRestaurantsWithCache({ forceRefresh: true })
                        .then((fresh) => {
                            setRestaurants(fresh.restaurants || []);
                        })
                        .catch(() => {
                            // Keep cached restaurants if background refresh fails.
                        });
                }
            } else {
                console.error('Failed to load restaurants:', restaurantRes.reason);
                setRestaurants([]);
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

    const filteredRestaurants = useMemo(() => {
        const normalizedSearch = searchQuery.trim().toLowerCase();

        return restaurants.filter((restaurant) => {
            if (!restaurant?.restaurant_id) {
                return false;
            }

            const probe = `${restaurant.name ?? ''} ${restaurant.cuisine ?? ''} ${(restaurant.tags || []).join(' ')}`.toLowerCase();
            const matchesSearch = !normalizedSearch || probe.includes(normalizedSearch);
            const matchesCategory = matchesCategoryFilter(selectedCategory, restaurant);

            return matchesSearch && matchesCategory;
        });
    }, [restaurants, searchQuery, selectedCategory]);

    const isSmallPhone = width < 360;
    const cardLayout = isSmallPhone ? 'list' : 'grid';
    const cardWidth = isSmallPhone
        ? width - theme.screenPadding.horizontal * 2
        : (width - theme.screenPadding.horizontal * 2 - theme.spacing.md) / 2;

    const handleTabPress = (tabKey: string) => {
        setActiveTab(tabKey);

        if (tabKey === 'home') {
            return;
        }

        if (tabKey === 'browse') {
            navigation?.navigate?.('Restaurants', {
                customerName: route?.params?.customerName || 'Guest',
            });
            return;
        }

        if (tabKey === 'orders') {
            navigation?.navigate?.('Orders');
            return;
        }

        if (tabKey === 'favorites') {
            navigation?.navigate?.('Favorites');
            return;
        }

        if (tabKey === 'profile') {
            navigation?.navigate?.('Profile');
        }
    };

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

        if (filteredRestaurants.length === 0) {
            return (
                <View style={styles.emptyState}>
                    <Text style={styles.emptyTitle}>No results near your location</Text>
                    <Text style={styles.emptySubtitle}>Try a different search or update your delivery area.</Text>
                    <PrimaryButton
                        label="Browse all restaurants"
                        onPress={() => {
                            setSelectedCategory('restaurants');
                            setSearchQuery('');
                        }}
                        style={styles.emptyButton}
                    />
                    <SecondaryButton
                        label="Change location"
                        onPress={() => Alert.alert('Location', 'Location controls will be added in the next iteration.')}
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
                    const ratingValue = Number(restaurant.rating) || 0;
                    const deliveryWindow = index % 2 === 0 ? '20-30 min' : '15-25 min';

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
                                rating={ratingValue}
                                ratingCount={900 + index * 100}
                                deliveryTime={deliveryWindow}
                                deliveryFee={index % 2 === 0 ? '$1.99 delivery' : '$0.99 delivery'}
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
                    placeholder="Deliver to Your Location"
                    rightIcon={<Text style={styles.searchRightIcon}>⌄</Text>}
                    style={styles.searchBar}
                />

                <ScrollView
                    horizontal
                    showsHorizontalScrollIndicator={false}
                    contentContainerStyle={styles.chipRow}
                >
                    {CATEGORIES.map((category) => (
                        <CategoryChip
                            key={category.id}
                            label={category.label}
                            icon={<Text style={styles.chipIcon}>{category.icon}</Text>}
                            selected={selectedCategory === category.id}
                            onPress={() => setSelectedCategory(category.id)}
                            onTintedBackground
                        />
                    ))}
                </ScrollView>
            </PeacockHeader>

            <View style={styles.contentArea}>
                <ScrollView
                    showsVerticalScrollIndicator={false}
                    contentContainerStyle={styles.scrollContent}
                >
                    <View style={styles.section}>
                        {loading ? (
                            <View style={styles.skeletonBanner} />
                        ) : (
                            <PromoBannerCard
                                title="Explore Nearby"
                                subtitle="Up to 50% Off"
                                ctaLabel="Browse Restaurants"
                                image={bannerRestaurantImage(filteredRestaurants[0])}
                                onPress={() => {}}
                            />
                        )}
                    </View>

                    <View style={styles.sectionHeader}>
                        <Text style={styles.sectionTitle}>Popular Near You</Text>
                        <TouchableOpacity onPress={() => navigation.navigate('Restaurants', { customerName: route?.params?.customerName || 'Guest' })}>
                            <Text style={styles.seeAll}>See all ›</Text>
                        </TouchableOpacity>
                    </View>

                    {renderRestaurantGrid()}
                </ScrollView>

                <BottomTabBar
                    items={TAB_ITEMS}
                    activeKey={activeTab}
                    onTabPress={handleTabPress}
                />
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
    chipIcon: {
        fontSize: 14,
        lineHeight: 18,
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
