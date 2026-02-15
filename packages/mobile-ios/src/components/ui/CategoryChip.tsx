import React from 'react';
import { Text, TouchableOpacity, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { theme } from '../../theme';

interface Props {
    label: string;
    selected?: boolean;
    onPress: () => void;
}

export const CategoryChip: React.FC<Props> = ({ label, selected = false, onPress }) => {
    if (selected) {
        return (
            <TouchableOpacity onPress={onPress} activeOpacity={0.8}>
                <LinearGradient
                    colors={[theme.colors.teal2, theme.colors.blue2]}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 1 }}
                    style={[styles.container, styles.selectedContainer]}
                >
                    <Text style={[styles.text, styles.selectedText]}>{label}</Text>
                </LinearGradient>
            </TouchableOpacity>
        );
    }

    return (
        <TouchableOpacity onPress={onPress} style={[styles.container, styles.unselectedContainer]}>
            <Text style={[styles.text, styles.unselectedText]}>{label}</Text>
        </TouchableOpacity>
    );
};

const styles = StyleSheet.create({
    container: {
        paddingHorizontal: 16,
        paddingVertical: 8,
        borderRadius: theme.layout.radius.chip,
        marginRight: 8,
        minWidth: 80,
        alignItems: 'center',
        justifyContent: 'center',
    },
    selectedContainer: {
        borderWidth: 0,
    },
    unselectedContainer: {
        backgroundColor: theme.colors.white,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    text: {
        fontSize: 14,
        fontWeight: '600',
    },
    selectedText: {
        color: theme.colors.white,
    },
    unselectedText: {
        color: theme.colors.textSecondary,
    }
});
