import React from 'react';
import { TouchableOpacity, Text, StyleSheet, StyleProp, ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { theme } from '../../theme';

interface Props {
    label: string;
    onPress: () => void;
    disabled?: boolean;
    style?: StyleProp<ViewStyle>;
    testID?: string;
}

export const PrimaryButton: React.FC<Props> = ({ label, onPress, disabled = false, style, testID }) => {
    return (
        <TouchableOpacity
            onPress={onPress}
            disabled={disabled}
            activeOpacity={0.9}
            style={[styles.touchable, disabled && styles.disabled, style]}
            testID={testID}
        >
            <LinearGradient
                colors={theme.gradients.primary}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={styles.container}
            >
                <Text style={styles.label}>{label}</Text>
            </LinearGradient>
        </TouchableOpacity>
    );
};

const styles = StyleSheet.create({
    touchable: {
        borderRadius: theme.radii.button,
        overflow: 'hidden',
    },
    container: {
        minHeight: 48,
        borderRadius: theme.radii.button,
        alignItems: 'center',
        justifyContent: 'center',
        paddingHorizontal: theme.spacing.lg,
    },
    label: {
        ...theme.typography.body,
        color: theme.colors.white,
        fontWeight: '700',
    },
    disabled: {
        opacity: 0.5,
    },
});
