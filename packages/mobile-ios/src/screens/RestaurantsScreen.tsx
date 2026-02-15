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
    ActivityIndicator,
} from 'react-native';
import { getRestaurants, Restaurant } from '../services/api';
import { theme } from '../theme';

interface Props {
    navigation: any;
    route: any;
}

export default function RestaurantsScreen({ navigation, route }: Props) {
    const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
    const [loading, setLoading] = useState(true);
    const { customerName } = route.params || {};

    useEffect(() => {
        loadRestaurants();
    }, []);

    const loadRestaurants = async () => {
        try {
            const data = await getRestaurants();
            setRestaurants(data);
        } catch (error) {
            console.error('Failed to load restaurants:', error);
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

    const renderRestaurant = ({ item }: { item: Restaurant }) => (
        <TouchableOpacity
            style={styles.card}
            onPress={() => handleSelectRestaurant(item)}
        >
            <Text style={styles.emoji}>{item.emoji}</Text>
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
            <Text style={styles.arrow}>›</Text>
        </TouchableOpacity>
    );

    if (loading) {
        return (
            <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color={theme.colors.primary} />
                <Text style={styles.loadingText}>Loading restaurants...</Text>
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
    loadingContainer: {
        flex: 1,
        backgroundColor: theme.colors.background,
        justifyContent: 'center',
        alignItems: 'center',
    },
    loadingText: {
        color: theme.colors.textMuted,
        marginTop: 16,
        fontSize: 16,
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
    emoji: {
        fontSize: 40,
        marginRight: 16,
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
    arrow: {
        fontSize: 24,
        color: theme.colors.accent,
    },
});
