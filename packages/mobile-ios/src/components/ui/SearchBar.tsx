import React, { ReactNode } from 'react';
import {
    View,
    TextInput,
    StyleSheet,
    TouchableOpacity,
    StyleProp,
    ViewStyle,
    Text,
} from 'react-native';
import { theme } from '../../theme';

interface Props {
    value: string;
    onChange?: (text: string) => void;
    onChangeText?: (text: string) => void;
    placeholder?: string;
    onSubmit?: () => void;
    rightIcon?: ReactNode;
    onRightIconPress?: () => void;
    style?: StyleProp<ViewStyle>;
}

export const SearchBar: React.FC<Props> = ({
    value,
    onChange,
    onChangeText,
    placeholder = 'Search restaurants or dishes...',
    onSubmit,
    rightIcon,
    onRightIconPress,
    style,
}) => {
    const handleChange = onChangeText || onChange;

    return (
        <View style={style}>
            <View style={styles.inputContainer}>
                <Text style={styles.searchIcon}>⌕</Text>

                <TextInput
                    style={styles.input}
                    value={value}
                    onChangeText={handleChange}
                    placeholder={placeholder}
                    placeholderTextColor={theme.colors.textSecondary}
                    onSubmitEditing={onSubmit}
                    returnKeyType="search"
                />

                {rightIcon ? (
                    <TouchableOpacity
                        style={styles.rightIconButton}
                        onPress={onRightIconPress}
                        accessibilityRole="button"
                    >
                        {rightIcon}
                    </TouchableOpacity>
                ) : null}
            </View>
        </View>
    );
};

const styles = StyleSheet.create({
    inputContainer: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: theme.colors.glassInput,
        borderRadius: theme.radii.input,
        borderWidth: 1,
        borderColor: theme.colors.border,
        height: 50,
        paddingHorizontal: theme.spacing.md,
        shadowColor: theme.shadows.card.shadowColor,
        shadowOffset: theme.shadows.card.shadowOffset,
        shadowOpacity: theme.shadows.card.shadowOpacity,
        shadowRadius: theme.shadows.card.shadowRadius,
        elevation: theme.shadows.card.elevation,
    },
    searchIcon: {
        ...theme.typography.h3,
        color: theme.colors.textSecondary,
        marginRight: theme.spacing.sm,
        lineHeight: 20,
    },
    input: {
        ...theme.typography.body,
        flex: 1,
        color: theme.colors.text,
        height: '100%',
    },
    rightIconButton: {
        marginLeft: theme.spacing.sm,
        alignItems: 'center',
        justifyContent: 'center',
    },
});
