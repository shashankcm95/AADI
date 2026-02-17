import React, { ReactNode } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Image } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { theme } from '../../theme';

interface Props {
    title?: string;
    leftIcon?: ReactNode;
    rightIcon?: ReactNode;
    onLeftPress?: () => void;
    onRightPress?: () => void;
    rightBadgeCount?: number;
    showLogo?: boolean;
    children?: ReactNode;
    onProfilePress?: () => void;
    onActionPress?: () => void;
    actionLabel?: string;
}

export const PeacockHeader: React.FC<Props> = ({
    title = 'AADI',
    leftIcon,
    rightIcon,
    onLeftPress,
    onRightPress,
    rightBadgeCount,
    showLogo = true,
    children,
    onProfilePress,
    onActionPress,
    actionLabel,
}) => {
    const insets = useSafeAreaInsets();
    const handleRightAction = onRightPress || onActionPress || onProfilePress;
    const headerMinHeight = Math.max(96, insets.top + 72);

    return (
        <LinearGradient
            colors={theme.gradients.primary}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={[styles.container, { paddingTop: insets.top, minHeight: headerMinHeight }]}
        >
            <View style={styles.tintOverlay} />

            <View style={styles.content}>
                <View style={styles.leftCluster}>
                    {leftIcon ? (
                        <TouchableOpacity
                            accessibilityRole="button"
                            onPress={onLeftPress}
                            style={styles.iconButton}
                            testID="peacock-header-left-button"
                        >
                            {leftIcon}
                        </TouchableOpacity>
                    ) : null}

                    <View style={styles.brandRow}>
                        {showLogo ? (
                            <Image
                                source={require('../../../assets/logo_icon_stylized.png')}
                                style={styles.logo}
                                resizeMode="cover"
                            />
                        ) : null}
                        <Text style={styles.titleText} numberOfLines={1}>
                            {title}
                        </Text>
                    </View>
                </View>

                <TouchableOpacity
                    accessibilityRole="button"
                    onPress={handleRightAction}
                    style={styles.rightButton}
                    testID="peacock-header-right-button"
                >
                    {actionLabel ? (
                        <Text style={styles.actionText}>{actionLabel}</Text>
                    ) : (
                        rightIcon || <Text style={styles.defaultRightIcon}>🛒</Text>
                    )}
                    {typeof rightBadgeCount === 'number' && rightBadgeCount > 0 ? (
                        <View style={styles.badge}>
                            <Text style={styles.badgeText}>{rightBadgeCount}</Text>
                        </View>
                    ) : null}
                </TouchableOpacity>
            </View>

            {children ? <View style={styles.childrenContainer}>{children}</View> : null}
        </LinearGradient>
    );
};

const styles = StyleSheet.create({
    container: {
        position: 'relative',
        borderBottomLeftRadius: theme.layout.radius.card,
        borderBottomRightRadius: theme.layout.radius.card,
        overflow: 'hidden',
        paddingBottom: theme.spacing.md,
    },
    tintOverlay: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: theme.colors.overlayTopTint,
    },
    content: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: theme.screenPadding.horizontal,
        minHeight: 56,
    },
    leftCluster: {
        flexDirection: 'row',
        alignItems: 'center',
        flex: 1,
        marginRight: theme.spacing.md,
    },
    iconButton: {
        width: 36,
        height: 36,
        borderRadius: 18,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(255,255,255,0.2)',
        marginRight: theme.spacing.sm,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.3)',
    },
    brandRow: {
        flexDirection: 'row',
        alignItems: 'center',
        flex: 1,
    },
    logo: {
        width: 44,
        height: 44,
        borderRadius: 12,
        marginRight: theme.spacing.sm,
    },
    titleText: {
        ...theme.typography.h1,
        color: theme.colors.white,
        flexShrink: 1,
    },
    rightButton: {
        width: 44,
        height: 44,
        borderRadius: 22,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(255,255,255,0.2)',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.35)',
        position: 'relative',
    },
    defaultRightIcon: {
        fontSize: 22,
        color: theme.colors.white,
    },
    actionText: {
        color: theme.colors.white,
        ...theme.typography.caption,
        fontWeight: '700',
    },
    badge: {
        position: 'absolute',
        top: -2,
        right: -2,
        minWidth: 18,
        height: 18,
        borderRadius: 9,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: 4,
        backgroundColor: theme.colors.teal3,
        borderWidth: 1,
        borderColor: theme.colors.white,
    },
    badgeText: {
        ...theme.typography.caption,
        color: theme.colors.white,
        fontSize: 10,
        lineHeight: 12,
    },
    childrenContainer: {
        paddingHorizontal: theme.screenPadding.horizontal,
        paddingTop: theme.spacing.sm,
    },
});
