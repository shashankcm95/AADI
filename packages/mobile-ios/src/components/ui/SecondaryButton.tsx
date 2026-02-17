import React from 'react';
import { TouchableOpacity, Text, StyleSheet, StyleProp, ViewStyle } from 'react-native';
import { theme } from '../../theme';

interface Props {
    label: string;
    onPress: () => void;
    disabled?: boolean;
    style?: StyleProp<ViewStyle>;
    testID?: string;
}

export const SecondaryButton: React.FC<Props> = ({ label, onPress, disabled = false, style, testID }) => {
    return (
        <TouchableOpacity
            onPress={onPress}
            disabled={disabled}
            activeOpacity={0.9}
            style={[styles.container, disabled && styles.disabled, style]}
            testID={testID}
        >
            <Text style={styles.label}>{label}</Text>
        </TouchableOpacity>
    );
};

const styles = StyleSheet.create({
    container: {
        minHeight: 48,
        borderRadius: theme.radii.button,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: theme.spacing.lg,
        backgroundColor: theme.colors.surface,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    label: {
        ...theme.typography.body,
        color: theme.colors.text,
        fontWeight: '700',
    },
    disabled: {
        opacity: 0.5,
    },
});
