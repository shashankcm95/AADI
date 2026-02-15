import React from 'react';
import { View, TextInput, StyleSheet, TouchableOpacity } from 'react-native';
import { theme } from '../../theme';

interface Props {
    value: string;
    onChangeText: (text: string) => void;
    placeholder?: string;
    onSubmit?: () => void;
}

export const SearchBar: React.FC<Props> = ({
    value,
    onChangeText,
    placeholder = 'Search restaurants or dishes...',
    onSubmit
}) => {
    return (
        <View style={styles.container}>
            <View style={styles.inputContainer}>
                {/* Search Icon Placeholder */}
                <View style={styles.iconContainer}>
                    {/* 🔍 Emoji as temporary icon */}
                </View>

                <TextInput
                    style={styles.input}
                    value={value}
                    onChangeText={onChangeText}
                    placeholder={placeholder}
                    placeholderTextColor={theme.colors.textSecondary}
                    onSubmitEditing={onSubmit}
                    returnKeyType="search"
                />
            </View>
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        paddingHorizontal: theme.layout.spacing.lg,
        marginTop: -24, // Overlap the header slightly
        marginBottom: theme.layout.spacing.md,
    },
    inputContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: 'rgba(255,255,255,0.95)',
        height: 50,
        borderRadius: theme.layout.radius.input,
        paddingHorizontal: theme.layout.spacing.md,
        // Shadow
        shadowColor: theme.layout.shadows.card.shadowColor,
        shadowOffset: theme.layout.shadows.card.shadowOffset,
        shadowOpacity: theme.layout.shadows.card.shadowOpacity,
        shadowRadius: theme.layout.shadows.card.shadowRadius,
        elevation: theme.layout.shadows.card.elevation,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    iconContainer: {
        marginRight: theme.layout.spacing.sm,
    },
    input: {
        flex: 1,
        fontSize: 16,
        color: theme.colors.text,
        height: '100%',
    }
});
