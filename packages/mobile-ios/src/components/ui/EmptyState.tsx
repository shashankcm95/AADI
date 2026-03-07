import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { theme } from '../../theme';

interface Props {
    emoji: string;
    title: string;
    subtitle: string;
    buttonLabel: string;
    onButtonPress: () => void;
}

export const EmptyState: React.FC<Props> = ({
    emoji,
    title,
    subtitle,
    buttonLabel,
    onButtonPress,
}) => (
    <View style={styles.container}>
        <Text style={styles.emoji}>{emoji}</Text>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.subtitle}>{subtitle}</Text>
        <TouchableOpacity style={styles.button} onPress={onButtonPress}>
            <Text style={styles.buttonText}>{buttonLabel}</Text>
        </TouchableOpacity>
    </View>
);

const styles = StyleSheet.create({
    container: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        paddingHorizontal: theme.spacing.xl,
    },
    emoji: {
        fontSize: 64,
        marginBottom: theme.spacing.lg,
    },
    title: {
        ...theme.typography.h2,
        color: theme.colors.text,
        textAlign: 'center',
        marginBottom: theme.spacing.sm,
    },
    subtitle: {
        ...theme.typography.body,
        color: theme.colors.textSecondary,
        textAlign: 'center',
    },
    button: {
        marginTop: theme.spacing.lg,
        borderRadius: theme.radii.button,
        borderWidth: 1,
        borderColor: theme.colors.border,
        backgroundColor: theme.colors.primary,
        paddingHorizontal: theme.spacing.xl,
        paddingVertical: theme.spacing.md,
    },
    buttonText: {
        ...theme.typography.body,
        color: theme.colors.white,
        fontWeight: '700',
    },
});
