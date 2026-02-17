import React, { ReactNode } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { theme } from '../../theme';

export interface BottomTabItem {
    key: string;
    label: string;
    icon?: ReactNode;
}

interface Props {
    items: BottomTabItem[];
    activeKey: string;
    onTabPress: (key: string) => void;
}

export const BottomTabBar: React.FC<Props> = ({ items, activeKey, onTabPress }) => {
    const insets = useSafeAreaInsets();

    return (
        <View style={[styles.container, { paddingBottom: Math.max(insets.bottom, theme.spacing.sm) }]}>
            <View style={styles.row}>
                {items.map((item) => {
                    const active = item.key === activeKey;

                    return (
                        <TouchableOpacity
                            key={item.key}
                            onPress={() => onTabPress(item.key)}
                            style={styles.item}
                            accessibilityRole="button"
                        >
                            <View style={[styles.iconWrap, active ? styles.activeIconWrap : styles.inactiveIconWrap]}>
                                <Text style={active ? styles.activeIconText : styles.inactiveIconText}>
                                    {item.icon || '•'}
                                </Text>
                            </View>
                            <Text style={[styles.label, active ? styles.activeLabel : styles.inactiveLabel]}>
                                {item.label}
                            </Text>
                        </TouchableOpacity>
                    );
                })}
            </View>
        </View>
    );
};

const styles = StyleSheet.create({
    container: {
        backgroundColor: theme.colors.surface,
        borderTopWidth: 1,
        borderTopColor: theme.colors.border,
        paddingTop: theme.spacing.sm,
        paddingHorizontal: theme.spacing.md,
    },
    row: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    item: {
        alignItems: 'center',
        justifyContent: 'center',
        flex: 1,
        paddingVertical: theme.spacing.xs,
    },
    iconWrap: {
        width: 36,
        height: 36,
        borderRadius: 18,
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: theme.spacing.xs,
    },
    activeIconWrap: {
        backgroundColor: theme.colors.offWhite,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    inactiveIconWrap: {
        backgroundColor: 'transparent',
    },
    activeIconText: {
        color: theme.colors.blue4,
        fontSize: 18,
        lineHeight: 20,
    },
    inactiveIconText: {
        color: theme.colors.textSecondary,
        fontSize: 18,
        lineHeight: 20,
    },
    label: {
        ...theme.typography.caption,
    },
    activeLabel: {
        color: theme.colors.blue4,
    },
    inactiveLabel: {
        color: theme.colors.textSecondary,
    },
});
