import React, { ReactNode } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { theme } from '../../theme';

interface Props {
    label: string;
    icon?: ReactNode;
    count?: number;
    selected?: boolean;
    onPress: () => void;
    onTintedBackground?: boolean;
}

export const CategoryChip: React.FC<Props> = ({
    label,
    icon,
    count,
    selected = false,
    onPress,
    onTintedBackground = false,
}) => {
    const displayLabel = count && count > 0 ? `${label} (${count})` : label;
    if (selected) {
        return (
            <TouchableOpacity onPress={onPress} activeOpacity={0.9} style={styles.outer}>
                <LinearGradient
                    colors={theme.gradients.secondary}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={[styles.container, styles.selectedContainer]}
                >
                    {icon ? <View style={styles.icon}>{icon}</View> : null}
                    <Text style={[styles.text, styles.selectedText]} numberOfLines={1}>
                        {displayLabel}
                    </Text>
                </LinearGradient>
            </TouchableOpacity>
        );
    }

    return (
        <TouchableOpacity
            onPress={onPress}
            activeOpacity={0.9}
            style={[
                styles.outer,
                styles.container,
                styles.unselectedContainer,
                onTintedBackground && styles.unselectedOnTint,
            ]}
        >
            {icon ? <View style={styles.icon}>{icon}</View> : null}
            <Text style={[styles.text, styles.unselectedText]} numberOfLines={1}>
                {displayLabel}
            </Text>
        </TouchableOpacity>
    );
};

const styles = StyleSheet.create({
    outer: {
        marginRight: theme.spacing.sm,
    },
    container: {
        minHeight: 40,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: theme.spacing.lg,
        borderRadius: theme.radii.chip,
    },
    selectedContainer: {
        borderWidth: 0,
    },
    unselectedContainer: {
        backgroundColor: theme.colors.surface,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    unselectedOnTint: {
        backgroundColor: 'rgba(255,255,255,0.65)',
    },
    icon: {
        marginRight: theme.spacing.xs,
    },
    text: {
        ...theme.typography.bodySm,
        fontWeight: '600',
    },
    selectedText: {
        color: theme.colors.white,
    },
    unselectedText: {
        color: theme.colors.text,
    },
});
