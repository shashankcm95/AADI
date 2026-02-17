import React, { useEffect, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    Image,
    StyleSheet,
    Text,
    TouchableOpacity,
    View,
} from 'react-native';
import { signOut } from 'aws-amplify/auth';
import { theme } from '../theme';
import { clearAuthHeaderCache } from '../services/api';
import { clearMyOrdersCache } from '../services/orderHistory';
import { clearMyFavoritesCache } from '../services/favorites';
import { clearRestaurantsCache } from '../services/restaurantsCatalog';
import { getCurrentUserProfile, UserProfile } from '../services/session';
import { useCart } from '../state/CartContext';

interface Props {
    navigation: any;
}

export default function ProfileScreen({ navigation }: Props) {
    const [profile, setProfile] = useState<UserProfile | null>(null);
    const [loading, setLoading] = useState(true);
    const { clearCart } = useCart();

    useEffect(() => {
        let cancelled = false;

        getCurrentUserProfile()
            .then((result) => {
                if (!cancelled) {
                    setProfile(result);
                }
            })
            .finally(() => {
                if (!cancelled) {
                    setLoading(false);
                }
            });

        return () => {
            cancelled = true;
        };
    }, []);

    const handleSignOut = () => {
        Alert.alert('Sign Out', 'Do you want to sign out from this customer account?', [
            { text: 'Cancel', style: 'cancel' },
            {
                text: 'Sign Out',
                style: 'destructive',
                onPress: async () => {
                    try {
                        clearCart();
                        await clearMyOrdersCache();
                        await clearMyFavoritesCache();
                        await clearRestaurantsCache();
                        clearAuthHeaderCache();
                        await signOut();
                    } catch (error) {
                        console.warn('[ProfileScreen] Sign-out warning:', error);
                    } finally {
                        navigation.reset({ index: 0, routes: [{ name: 'Login' }] });
                    }
                },
            },
        ]);
    };

    if (loading) {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" color={theme.colors.primary} />
                <Text style={styles.loadingText}>Loading profile...</Text>
            </View>
        );
    }

    const showImage = Boolean(profile?.picture);

    return (
        <View style={styles.container}>
            <View style={styles.card}>
                <View style={styles.headerRow}>
                    {showImage ? (
                        <Image source={{ uri: profile?.picture }} style={styles.avatarImage} resizeMode="cover" />
                    ) : (
                        <Image
                            source={require('../../assets/logo_icon_stylized.png')}
                            style={styles.avatarFallback}
                            resizeMode="cover"
                        />
                    )}

                    <View style={styles.identityWrap}>
                        <Text style={styles.name}>{profile?.displayName || 'Customer'}</Text>
                        <Text style={styles.meta}>{profile?.email || 'No email on file'}</Text>
                        {profile?.userId ? (
                            <Text style={styles.meta}>User ID: {profile.userId.slice(0, 10)}...</Text>
                        ) : null}
                    </View>
                </View>

                <TouchableOpacity style={styles.actionRow} onPress={() => navigation.navigate('Orders')}>
                    <Text style={styles.actionTitle}>Order History</Text>
                    <Text style={styles.chevron}>›</Text>
                </TouchableOpacity>

                <TouchableOpacity style={styles.actionRow} onPress={() => navigation.navigate('Cart')}>
                    <Text style={styles.actionTitle}>Cart</Text>
                    <Text style={styles.chevron}>›</Text>
                </TouchableOpacity>

                <TouchableOpacity style={styles.actionRow} onPress={() => navigation.navigate('Favorites')}>
                    <Text style={styles.actionTitle}>Favorites</Text>
                    <Text style={styles.chevron}>›</Text>
                </TouchableOpacity>

                <TouchableOpacity style={styles.signOutButton} onPress={handleSignOut}>
                    <Text style={styles.signOutText}>Sign Out</Text>
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
        padding: theme.spacing.lg,
    },
    center: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: theme.colors.background,
    },
    loadingText: {
        ...theme.typography.body,
        color: theme.colors.textSecondary,
        marginTop: theme.spacing.md,
    },
    card: {
        ...theme.layout.card,
        padding: theme.spacing.lg,
    },
    headerRow: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: theme.spacing.lg,
    },
    avatarImage: {
        width: 72,
        height: 72,
        borderRadius: 36,
        marginRight: theme.spacing.md,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    avatarFallback: {
        width: 72,
        height: 72,
        borderRadius: 18,
        marginRight: theme.spacing.md,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    identityWrap: {
        flex: 1,
    },
    name: {
        ...theme.typography.h2,
        color: theme.colors.text,
    },
    meta: {
        ...theme.typography.bodySm,
        color: theme.colors.textSecondary,
        marginTop: theme.spacing.xs,
    },
    actionRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderWidth: 1,
        borderColor: theme.colors.border,
        borderRadius: theme.radii.input,
        paddingHorizontal: theme.spacing.md,
        paddingVertical: theme.spacing.md,
        marginBottom: theme.spacing.sm,
        backgroundColor: theme.colors.surface,
    },
    actionTitle: {
        ...theme.typography.body,
        color: theme.colors.text,
        fontWeight: '600',
    },
    chevron: {
        ...theme.typography.h3,
        color: theme.colors.textSecondary,
        lineHeight: 18,
    },
    signOutButton: {
        marginTop: theme.spacing.xl,
        borderRadius: theme.radii.button,
        alignItems: 'center',
        justifyContent: 'center',
        paddingVertical: theme.spacing.md,
        backgroundColor: theme.colors.surface,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    signOutText: {
        ...theme.typography.body,
        color: theme.colors.primary,
        fontWeight: '700',
    },
});
