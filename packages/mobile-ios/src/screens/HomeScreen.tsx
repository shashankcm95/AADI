import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import { theme } from '../theme';
import { PeacockHeader } from '../components/ui/PeacockHeader';
import { SearchBar } from '../components/ui/SearchBar';
import { CategoryChip } from '../components/ui/CategoryChip';
import { PromoBannerCard } from '../components/ui/PromoBannerCard';
import { RestaurantCard } from '../components/ui/RestaurantCard';
import { getRestaurants, Restaurant } from '../services/api';

// UI-only category chips for local filtering.
const CATEGORIES = [
    { id: '1', label: 'All' },
    { id: '2', label: 'Burgers' },
    { id: '3', label: 'Pizza' },
    { id: '4', label: 'Asian' },
    { id: '5', label: 'Dessert' },
];

export const HomeScreen: React.FC = ({ navigation }: any) => {
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState('1');
    const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadRestaurants();
    }, []);

    const loadRestaurants = async () => {
        try {
            const data = await getRestaurants();
            setRestaurants(data);
        } catch (error) {
            console.error('Failed to load restaurants:', error);
            // Don't alert immediately on mount to be less annoying, or use a toast
        } finally {
            setLoading(false);
        }
    };

    const selectedCategoryLabel = CATEGORIES.find((cat) => cat.id === selectedCategory)?.label || 'All';

    const filteredRestaurants = restaurants.filter((r) => {
        const matchesSearch = (
            r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
            r.cuisine.toLowerCase().includes(searchQuery.toLowerCase())
        );
        const matchesCategory = (
            selectedCategoryLabel === 'All' ||
            r.cuisine.toLowerCase().includes(selectedCategoryLabel.toLowerCase())
        );
        return matchesSearch && matchesCategory;
    });

    return (
        <View style={styles.container}>
            {/* Header Area */}
            <PeacockHeader
                title="AADI"
            />

            <View style={styles.body}>
                <SearchBar
                    value={searchQuery}
                    onChangeText={setSearchQuery}
                    onSubmit={() => { }}
                />

                <ScrollView
                    showsVerticalScrollIndicator={false}
                    contentContainerStyle={styles.scrollContent}
                >
                    {/* Categories */}
                    <ScrollView
                        horizontal
                        showsHorizontalScrollIndicator={false}
                        style={styles.categoriesContainer}
                        contentContainerStyle={{ paddingHorizontal: theme.layout.spacing.lg }}
                    >
                        {CATEGORIES.map(cat => (
                            <CategoryChip
                                key={cat.id}
                                label={cat.label}
                                selected={selectedCategory === cat.id}
                                onPress={() => setSelectedCategory(cat.id)}
                            />
                        ))}
                    </ScrollView>

                    {/* Promo Banner */}
                    <View style={styles.section}>
                        <PromoBannerCard
                            title="30% OFF Your First Order"
                            subtitle="Welcome to AADI"
                            onPress={() => { }}
                        />
                    </View>

                    {/* Popular Near You */}
                    <View style={styles.sectionHeader}>
                        <Text style={styles.sectionTitle}>Popular Near You</Text>
                        <Text style={styles.seeAll}>See All ›</Text>
                    </View>

                    {/* Restaurant List */}
                    {loading ? (
                        <ActivityIndicator size="large" color={theme.colors.teal1} style={{ marginTop: 20 }} />
                    ) : (
                        <View style={styles.listContainer}>
                            {filteredRestaurants.map(rest => (
                                <RestaurantCard
                                    key={rest.restaurant_id}
                                    name={rest.name}
                                    cuisine={rest.cuisine}
                                    rating={rest.rating}
                                    priceTier={rest.price_tier || 2}
                                    deliveryTime="Live status"
                                    emoji={rest.emoji}
                                    onPress={() => navigation?.navigate('Menu', {
                                        restaurant: rest
                                    })}
                                />
                            ))}
                        </View>
                    )}

                    {/* Bottom Padding for Tab Bar */}
                    <View style={{ height: 100 }} />
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
    body: {
        flex: 1,
    },
    scrollContent: {
        paddingTop: 8,
    },
    categoriesContainer: {
        marginBottom: theme.layout.spacing.xl,
        maxHeight: 40,
    },
    section: {
        marginBottom: theme.layout.spacing.xl,
    },
    sectionHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        paddingHorizontal: theme.layout.spacing.lg,
        marginBottom: theme.layout.spacing.md,
    },
    sectionTitle: {
        fontSize: theme.typography.subHeader.fontSize,
        fontWeight: 'bold',
        color: theme.colors.text,
    },
    seeAll: {
        fontSize: 14,
        color: theme.colors.blue4,
        fontWeight: '600',
    },
    listContainer: {
        paddingHorizontal: theme.layout.spacing.lg,
    }
});
