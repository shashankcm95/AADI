import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Image, Platform } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { SafeAreaView } from 'react-native-safe-area-context';
import { theme } from '../../theme';

interface Props {
    title?: string;
    onProfilePress?: () => void;
}

export const PeacockHeader: React.FC<Props> = ({ title = 'AADI', onProfilePress }) => {
    return (
        <LinearGradient
            colors={[theme.colors.teal1, theme.colors.blue4]}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
            style={styles.container}
        >
            <SafeAreaView edges={['top', 'left', 'right']} style={styles.safeArea}>
                <View style={styles.content}>
                    <View style={styles.left}>
                        {/* Placeholder for small logo if needed */}
                        <Text style={styles.logoText}>{title}</Text>
                    </View>

                    <TouchableOpacity onPress={onProfilePress} style={styles.profileButton}>
                        {/* Placeholder for profile image - using a generic circle for now */}
                        <View style={styles.avatarPlaceholder}>
                            <Text style={styles.avatarText}>👤</Text>
                        </View>
                    </TouchableOpacity>
                </View>
            </SafeAreaView>
        </LinearGradient>
    );
};

const styles = StyleSheet.create({
    container: {
        paddingBottom: theme.layout.spacing.lg,
        borderBottomLeftRadius: 24,
        borderBottomRightRadius: 24,
    },
    safeArea: {
        backgroundColor: 'transparent',
    },
    content: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: theme.layout.spacing.lg,
        paddingTop: theme.layout.spacing.sm,
    },
    left: {
        flexDirection: 'row',
        alignItems: 'center',
    },
    logoText: {
        fontSize: 28,
        fontWeight: '800',
        color: theme.colors.white,
        fontFamily: Platform.OS === 'ios' ? 'System' : 'Roboto',
        letterSpacing: 1,
    },
    profileButton: {
        padding: 4,
    },
    avatarPlaceholder: {
        width: 40,
        height: 40,
        borderRadius: 20,
        backgroundColor: 'rgba(255,255,255,0.2)',
        justifyContent: 'center',
        alignItems: 'center',
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.4)',
    },
    avatarText: {
        fontSize: 20,
    }
});
