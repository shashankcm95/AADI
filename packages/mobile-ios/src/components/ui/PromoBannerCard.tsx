import React from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    ImageBackground,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { theme } from '../../theme';

interface Props {
    title: string;
    subtitle: string;
    ctaLabel?: string;
    onPress: () => void;
}

export const PromoBannerCard: React.FC<Props> = ({
    title,
    subtitle,
    ctaLabel = 'Browse Restaurants',
    onPress,
}) => {
    return (
        <TouchableOpacity activeOpacity={0.92} onPress={onPress} style={styles.wrapper}>
            <ImageBackground
                source={require('../../../assets/explore_restaurants_bg.jpg')}
                style={styles.container}
                imageStyle={styles.backgroundImage}
                resizeMode="cover"
            >
                <LinearGradient
                    colors={['rgba(0,0,0,0.55)', 'rgba(0,0,0,0.25)', 'rgba(0,0,0,0.10)']}
                    start={{ x: 0, y: 1 }}
                    end={{ x: 1, y: 0 }}
                    style={styles.scrimOverlay}
                />

                <View style={styles.content}>
                    <Text style={styles.title} numberOfLines={2}>
                        {title}
                    </Text>
                    <Text style={styles.subtitle} numberOfLines={2}>
                        {subtitle}
                    </Text>
                    <View style={styles.ctaPill}>
                        <Text style={styles.ctaLabel}>{ctaLabel}</Text>
                    </View>
                </View>
            </ImageBackground>
        </TouchableOpacity>
    );
};

const styles = StyleSheet.create({
    wrapper: {
        shadowColor: theme.shadows.hero.shadowColor,
        shadowOffset: theme.shadows.hero.shadowOffset,
        shadowOpacity: theme.shadows.hero.shadowOpacity,
        shadowRadius: theme.shadows.hero.shadowRadius,
        elevation: theme.shadows.hero.elevation,
    },
    container: {
        borderRadius: theme.radii.card,
        minHeight: 190,
        overflow: 'hidden',
        justifyContent: 'flex-end',
        padding: theme.spacing.lg,
    },
    backgroundImage: {
        borderRadius: theme.radii.card,
    },
    scrimOverlay: {
        ...StyleSheet.absoluteFillObject,
        borderRadius: theme.radii.card,
    },
    content: {
        zIndex: 2,
    },
    title: {
        ...theme.typography.h1,
        color: theme.colors.white,
        marginBottom: theme.spacing.xs,
    },
    subtitle: {
        ...theme.typography.h2,
        color: theme.colors.white,
        marginBottom: theme.spacing.lg,
    },
    ctaPill: {
        alignSelf: 'flex-start',
        backgroundColor: theme.colors.glassSurface,
        borderRadius: theme.radii.chip,
        paddingVertical: theme.spacing.sm,
        paddingHorizontal: theme.spacing.lg,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    ctaLabel: {
        ...theme.typography.body,
        color: theme.colors.text,
        fontWeight: '700',
    },
});
