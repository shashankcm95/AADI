import React from 'react';
import {
    View,
    Text,
    TouchableOpacity,
    StyleSheet,
    Image,
    ImageSourcePropType,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { theme } from '../../theme';

interface Props {
    title: string;
    subtitle: string;
    ctaLabel?: string;
    onPress: () => void;
    image?: ImageSourcePropType;
}

export const PromoBannerCard: React.FC<Props> = ({
    title,
    subtitle,
    ctaLabel = 'Browse Restaurants',
    onPress,
    image,
}) => {
    return (
        <TouchableOpacity activeOpacity={0.92} onPress={onPress} style={styles.wrapper}>
            <LinearGradient
                colors={theme.gradients.secondary}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={styles.container}
            >
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

                {image ? (
                    <View style={styles.artPanel}>
                        <Image source={image} style={styles.bannerImage} resizeMode="cover" />
                        <LinearGradient
                            colors={['rgba(33,98,186,0.06)', 'rgba(33,98,186,0.26)']}
                            start={{ x: 0, y: 0 }}
                            end={{ x: 1, y: 1 }}
                            style={styles.artShade}
                        />
                    </View>
                ) : (
                    <View style={styles.placeholderCircle} />
                )}

                <LinearGradient
                    colors={['rgba(33,98,186,0.56)', 'rgba(33,98,186,0.18)', 'rgba(33,98,186,0.0)']}
                    start={{ x: 0, y: 0.5 }}
                    end={{ x: 1, y: 0.5 }}
                    style={styles.textScrim}
                />

                <Image
                    source={require('../../../assets/logo_icon_stylized.png')}
                    style={styles.cornerMark}
                    resizeMode="cover"
                />
            </LinearGradient>
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
        padding: theme.spacing.lg,
        overflow: 'hidden',
        justifyContent: 'space-between',
    },
    content: {
        width: '70%',
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
    artPanel: {
        position: 'absolute',
        right: 0,
        top: 0,
        bottom: 0,
        width: '54%',
        borderTopLeftRadius: theme.radii.input,
        borderBottomLeftRadius: theme.radii.input,
        overflow: 'hidden',
    },
    bannerImage: {
        width: '100%',
        height: '100%',
    },
    artShade: {
        ...StyleSheet.absoluteFillObject,
    },
    textScrim: {
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: '70%',
        zIndex: 1,
    },
    cornerMark: {
        position: 'absolute',
        right: theme.spacing.md,
        top: theme.spacing.md,
        width: 34,
        height: 34,
        borderRadius: 8,
        opacity: 0.85,
    },
    placeholderCircle: {
        position: 'absolute',
        right: -30,
        bottom: -40,
        width: 180,
        height: 180,
        borderRadius: 90,
        backgroundColor: 'rgba(255,255,255,0.2)',
    },
});
