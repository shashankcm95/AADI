import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Image } from 'react-native';
import { theme } from '../../theme';

interface Props {
    name: string;
    cuisine: string;
    rating: number;
    priceTier?: number;
    deliveryTime?: string;
    onPress: () => void;
    imagePlaceholderColor?: string; // Fallback since we don't have real images
    emoji?: string;
}

export const RestaurantCard: React.FC<Props> = ({
    name,
    cuisine,
    rating,
    priceTier = 2,
    deliveryTime = '20-30 min',
    onPress,
    imagePlaceholderColor = theme.colors.offWhite,
    emoji = '🍽️'
}) => {
    return (
        <TouchableOpacity activeOpacity={0.9} onPress={onPress} style={styles.container}>
            {/* Image Area */}
            <View style={[styles.imageArea, { backgroundColor: imagePlaceholderColor }]}>
                <Text style={{ fontSize: 40 }}>{emoji}</Text>

                {/* Favorite Heart Placeholder */}
                <View style={styles.favoriteButton}>
                    <Text>♡</Text>
                </View>

                {/* Promo Tag (Optional) */}
                <View style={styles.promoTag}>
                    <Text style={styles.promoText}>Free Delivery</Text>
                </View>
            </View>

            {/* Content Area */}
            <View style={styles.content}>
                <View style={styles.headerRow}>
                    <Text style={styles.name} numberOfLines={1}>{name}</Text>
                    <View style={styles.ratingContainer}>
                        <Text style={styles.ratingText}>{rating}</Text>
                        <Text style={styles.star}>★</Text>
                    </View>
                </View>

                <Text style={styles.meta}>
                    {'$'.repeat(priceTier)} • {cuisine} • {deliveryTime}
                </Text>
            </View>
        </TouchableOpacity>
    );
};

const styles = StyleSheet.create({
    container: {
        backgroundColor: theme.colors.white,
        borderRadius: theme.layout.radius.card,
        marginBottom: theme.layout.spacing.lg,
        // Card Shadow
        shadowColor: theme.layout.shadows.card.shadowColor,
        shadowOffset: theme.layout.shadows.card.shadowOffset,
        shadowOpacity: theme.layout.shadows.card.shadowOpacity,
        shadowRadius: theme.layout.shadows.card.shadowRadius,
        elevation: theme.layout.shadows.card.elevation,
    },
    imageArea: {
        height: 160,
        borderTopLeftRadius: theme.layout.radius.card,
        borderTopRightRadius: theme.layout.radius.card,
        justifyContent: 'center',
        alignItems: 'center',
        position: 'relative',
    },
    favoriteButton: {
        position: 'absolute',
        top: 12,
        right: 12,
        width: 32,
        height: 32,
        borderRadius: 16,
        backgroundColor: 'rgba(255,255,255,0.8)',
        justifyContent: 'center',
        alignItems: 'center',
    },
    promoTag: {
        position: 'absolute',
        top: 12,
        left: 12,
        backgroundColor: theme.colors.teal3,
        paddingHorizontal: 8,
        paddingVertical: 4,
        borderRadius: 4,
    },
    promoText: {
        color: theme.colors.white,
        fontSize: 10,
        fontWeight: '700',
        textTransform: 'uppercase',
    },
    content: {
        padding: 12,
    },
    headerRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 4,
    },
    name: {
        fontSize: 16,
        fontWeight: '700',
        color: theme.colors.text,
        flex: 1,
        marginRight: 8,
    },
    ratingContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: theme.colors.offWhite,
        paddingHorizontal: 6,
        paddingVertical: 2,
        borderRadius: 12,
    },
    ratingText: {
        fontSize: 12,
        fontWeight: '700',
        color: theme.colors.text,
        marginRight: 2,
    },
    star: {
        fontSize: 10,
        color: theme.colors.gold,
    },
    meta: {
        fontSize: 14,
        color: theme.colors.textSecondary,
    }
});
