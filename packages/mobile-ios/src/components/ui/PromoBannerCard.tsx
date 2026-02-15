import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Image } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { theme } from '../../theme';

interface Props {
    title: string;
    subtitle: string;
    ctaLabel?: string;
    onPress: () => void;
}

export const PromoBannerCard: React.FC<Props> = ({ title, subtitle, ctaLabel = 'Order Now >', onPress }) => {
    return (
        <TouchableOpacity activeOpacity={0.9} onPress={onPress} style={styles.wrapper}>
            <LinearGradient
                colors={[theme.colors.teal2, theme.colors.blue2]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 0 }}
                style={styles.container}
            >
                <View style={styles.content}>
                    <Text style={styles.subtitle}>{subtitle}</Text>
                    <Text style={styles.title}>{title}</Text>

                    <View style={styles.ctaContainer}>
                        <Text style={styles.cta}>{ctaLabel}</Text>
                    </View>
                </View>
                {/* Decorative circle or image could go here */}
                <View style={styles.decorativeCircle} />
            </LinearGradient>
        </TouchableOpacity>
    );
};

const styles = StyleSheet.create({
    wrapper: {
        marginHorizontal: theme.layout.spacing.lg,
        shadowColor: theme.layout.shadows.hero.shadowColor,
        shadowOffset: theme.layout.shadows.hero.shadowOffset,
        shadowOpacity: theme.layout.shadows.hero.shadowOpacity,
        shadowRadius: theme.layout.shadows.hero.shadowRadius,
        elevation: theme.layout.shadows.hero.elevation,
    },
    container: {
        borderRadius: theme.layout.radius.card,
        padding: theme.layout.spacing.xl,
        overflow: 'hidden',
        minHeight: 140,
    },
    content: {
        zIndex: 2,
        flex: 1,
        justifyContent: 'center',
    },
    title: {
        fontSize: 24,
        fontWeight: '800',
        color: theme.colors.white,
        marginBottom: theme.layout.spacing.sm,
        maxWidth: '70%',
    },
    subtitle: {
        fontSize: 14,
        fontWeight: '600',
        color: 'rgba(255,255,255,0.9)',
        marginBottom: 4,
        letterSpacing: 0.5,
        textTransform: 'uppercase',
    },
    ctaContainer: {
        marginTop: theme.layout.spacing.sm,
        backgroundColor: 'rgba(255,255,255,0.2)',
        paddingHorizontal: 12,
        paddingVertical: 6,
        borderRadius: theme.layout.radius.chip,
        alignSelf: 'flex-start',
    },
    cta: {
        color: theme.colors.white,
        fontWeight: '700',
        fontSize: 12,
    },
    decorativeCircle: {
        position: 'absolute',
        right: -40,
        bottom: -40,
        width: 140,
        height: 140,
        borderRadius: 70,
        backgroundColor: 'rgba(255,255,255,0.1)',
        zIndex: 1,
    }
});
