import React, { useMemo, useRef, useState } from 'react';
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
    deliveryTime?: string;
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
    const [imageLoaded, setImageLoaded] = useState(false);
    const [imageFailed, setImageFailed] = useState(false);

    const showFallback = !image || !imageLoaded || imageFailed;

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

        try {
            const Haptics = require('expo-haptics');
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
        } catch {}
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
                {showFallback && (
                    <LinearGradient
                        colors={theme.gradients.secondary}
                        start={{ x: 0, y: 0 }}
                        end={{ x: 1, y: 1 }}
                        style={[styles.image, styles.imageFallback, (image && !imageFailed) ? styles.imagePlaceholder : undefined]}
                    >
                        <Text style={styles.emoji}>{emoji}</Text>
                    </LinearGradient>
                )}
                {image && !imageFailed && (
                    <Image
                        source={image}
                        style={[styles.image, !imageLoaded && styles.imageHidden]}
                        resizeMode="cover"
                        onLoad={() => setImageLoaded(true)}
                        onError={() => setImageFailed(true)}
                    />
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
                </View>

                <Text style={styles.metaLine} numberOfLines={1}>
                    {priceLabel} • {metaTags.join(' • ')}{deliveryTime ? ` • ${deliveryTime}` : ''}
                </Text>

                {deliveryFee ? (
                    <Text style={styles.feeLine} numberOfLines={1}>
                        {deliveryFee}
                    </Text>
                ) : null}
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
    imagePlaceholder: {
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 0,
    },
    imageHidden: {
        opacity: 0,
        position: 'absolute',
        top: 0,
        left: 0,
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
