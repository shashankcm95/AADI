import React, { useMemo, useRef } from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    Image,
    ImageSourcePropType,
    Animated,
    GestureResponderEvent,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { theme } from '../../theme';

type CardLayout = 'grid' | 'list';

interface Props {
    name: string;
    image?: ImageSourcePropType;
    rating: number;
    ratingCount?: number;
    deliveryTime: string;
    deliveryFee?: string;
    tags?: string[];
    isFavorite?: boolean;
    onFavoriteToggle?: () => void;
    onPress: () => void;
    layout?: CardLayout;
    cuisine?: string;
    priceTier?: number;
    emoji?: string;
}

export const RestaurantCard: React.FC<Props> = ({
    name,
    image,
    rating,
    ratingCount = 90,
    deliveryTime,
    deliveryFee,
    tags,
    isFavorite = false,
    onFavoriteToggle,
    onPress,
    layout = 'grid',
    cuisine,
    priceTier = 2,
    emoji = '🍽️',
}) => {
    const favoriteScale = useRef(new Animated.Value(1)).current;

    const ratingLabel = useMemo(() => {
        if (!Number.isFinite(rating)) {
            return '-';
        }
        return rating.toFixed(1).replace(/\.0$/, '');
    }, [rating]);

    const metaTags = useMemo(() => {
        if (tags && tags.length > 0) {
            return tags;
        }
        return cuisine ? [cuisine] : ['Cuisine'];
    }, [tags, cuisine]);

    const priceLabel = '$'.repeat(Math.min(Math.max(priceTier, 1), 4));

    const onFavoritePress = () => {
        if (!onFavoriteToggle) {
            return;
        }
        Animated.sequence([
            Animated.timing(favoriteScale, {
                toValue: 1.15,
                duration: 90,
                useNativeDriver: true,
            }),
            Animated.spring(favoriteScale, {
                toValue: 1,
                useNativeDriver: true,
                speed: 18,
                bounciness: 10,
            }),
        ]).start();

        onFavoriteToggle();
    };

    const onFavoritePressWithStop = (event: GestureResponderEvent) => {
        event.stopPropagation();
        onFavoritePress();
    };

    const isList = layout === 'list';

    return (
        <TouchableOpacity
            activeOpacity={0.9}
            onPress={onPress}
            style={[styles.cardContainer, isList && styles.listContainer]}
            testID="restaurant-card"
        >
            <View style={[styles.imageWrap, isList && styles.listImageWrap]}>
                {image ? (
                    <Image source={image} style={styles.image} resizeMode="cover" />
                ) : (
                    <LinearGradient
                        colors={theme.gradients.secondary}
                        start={{ x: 0, y: 0 }}
                        end={{ x: 1, y: 1 }}
                        style={[styles.image, styles.imageFallback]}
                    >
                        <Text style={styles.emoji}>{emoji}</Text>
                    </LinearGradient>
                )}

                <View style={styles.cuisineBadge}>
                    <Text style={styles.cuisineBadgeText} numberOfLines={1}>
                        {emoji} {cuisine || 'Kitchen'}
                    </Text>
                </View>

                <Animated.View style={[styles.favoriteButton, { transform: [{ scale: favoriteScale }] }]}>
                    <TouchableOpacity onPress={onFavoritePressWithStop} accessibilityRole="button" testID="favorite-toggle">
                        <Text style={styles.favoriteText}>{isFavorite ? '♥' : '♡'}</Text>
                    </TouchableOpacity>
                </Animated.View>
            </View>

            <View style={[styles.content, isList && styles.listContent]}>
                <View style={styles.headerRow}>
                    <Text style={styles.name} numberOfLines={1}>
                        {name}
                    </Text>
                    <View style={styles.ratingRow}>
                        <Text style={styles.star}>★</Text>
                        <Text style={styles.ratingValue}>{ratingLabel}</Text>
                        <Text style={styles.ratingCount}>{ratingCount}+</Text>
                    </View>
                </View>

                <Text style={styles.metaLine} numberOfLines={1}>
                    {priceLabel} • {metaTags.join(' • ')} • {deliveryTime}
                </Text>

                <Text style={styles.feeLine} numberOfLines={1}>
                    {deliveryFee || '$0 delivery fee'}
                </Text>
            </View>
        </TouchableOpacity>
    );
};

const styles = StyleSheet.create({
    cardContainer: {
        backgroundColor: theme.colors.surface,
        borderRadius: theme.radii.card,
        overflow: 'hidden',
        shadowColor: theme.shadows.card.shadowColor,
        shadowOffset: theme.shadows.card.shadowOffset,
        shadowOpacity: theme.shadows.card.shadowOpacity,
        shadowRadius: theme.shadows.card.shadowRadius,
        elevation: theme.shadows.card.elevation,
    },
    listContainer: {
        flexDirection: 'row',
        minHeight: 140,
    },
    imageWrap: {
        position: 'relative',
        height: 164,
    },
    listImageWrap: {
        width: 132,
        height: '100%',
    },
    image: {
        width: '100%',
        height: '100%',
    },
    imageFallback: {
        alignItems: 'center',
        justifyContent: 'center',
    },
    emoji: {
        fontSize: 42,
    },
    cuisineBadge: {
        position: 'absolute',
        left: theme.spacing.sm,
        top: theme.spacing.sm,
        maxWidth: '70%',
        backgroundColor: theme.colors.glassSurface,
        borderRadius: theme.radii.chip,
        borderWidth: 1,
        borderColor: theme.colors.border,
        paddingHorizontal: theme.spacing.sm,
        paddingVertical: theme.spacing.xs,
    },
    cuisineBadgeText: {
        ...theme.typography.caption,
        color: theme.colors.text,
        fontWeight: '700',
    },
    favoriteButton: {
        position: 'absolute',
        top: theme.spacing.sm,
        right: theme.spacing.sm,
        width: 32,
        height: 32,
        borderRadius: 16,
        backgroundColor: theme.colors.glassSurface,
        borderWidth: 1,
        borderColor: theme.colors.border,
        justifyContent: 'center',
        alignItems: 'center',
    },
    favoriteText: {
        color: theme.colors.text,
        fontSize: 17,
        lineHeight: 20,
    },
    content: {
        paddingHorizontal: theme.spacing.md,
        paddingTop: theme.spacing.md,
        paddingBottom: theme.spacing.lg,
    },
    listContent: {
        flex: 1,
    },
    headerRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: theme.spacing.xs,
        gap: theme.spacing.sm,
    },
    name: {
        ...theme.typography.h3,
        color: theme.colors.text,
        flex: 1,
    },
    ratingRow: {
        flexDirection: 'row',
        alignItems: 'center',
        borderRadius: theme.radii.chip,
        backgroundColor: theme.colors.offWhite,
        borderWidth: 1,
        borderColor: theme.colors.border,
        paddingHorizontal: theme.spacing.sm,
        paddingVertical: theme.spacing.xs,
    },
    star: {
        fontSize: 11,
        color: theme.colors.gold,
        marginRight: 2,
    },
    ratingValue: {
        ...theme.typography.caption,
        color: theme.colors.text,
        fontWeight: '700',
        marginRight: 4,
    },
    ratingCount: {
        ...theme.typography.caption,
        color: theme.colors.textSecondary,
    },
    metaLine: {
        ...theme.typography.bodySm,
        color: theme.colors.textSecondary,
        marginBottom: theme.spacing.xs,
    },
    feeLine: {
        ...theme.typography.caption,
        color: theme.colors.text,
        borderWidth: 1,
        borderColor: theme.colors.border,
        alignSelf: 'flex-start',
        borderRadius: theme.radii.chip,
        paddingHorizontal: theme.spacing.sm,
        paddingVertical: theme.spacing.xs,
        overflow: 'hidden',
    },
});
