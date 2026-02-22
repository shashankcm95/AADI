import React, { useEffect, useState } from 'react';
import {
    ActivityIndicator,
    Alert,
    Image,
    StyleSheet,
    Text,
    TextInput,
    TouchableOpacity,
    View,
    ScrollView,
    KeyboardAvoidingView,
    Platform
} from 'react-native';
import { signOut } from 'aws-amplify/auth';
import * as ImagePicker from 'expo-image-picker';
import { theme } from '../theme';
import {
    clearAuthHeaderCache,
    getUserProfile,
    updateUserProfile,
    getAvatarUploadUrl,
    uploadAvatarToS3,
    UserProfile
} from '../services/api';
import { clearMyOrdersCache } from '../services/orderHistory';

import { clearMyFavoritesCache } from '../services/favorites';
import { clearRestaurantsCache } from '../services/restaurantsCatalog';
import { getCurrentUserProfile } from '../services/session';
import { useCart } from '../state/CartContext';

interface Props {
    navigation: any;
}

function normalizeAvatarUri(value: unknown): string | null {
    const uri = String(value || '').trim();
    if (!uri) {
        return null;
    }
    if (/^(https?:\/\/|file:\/\/|content:\/\/|data:image\/)/i.test(uri)) {
        return uri;
    }
    return null;
}

export default function ProfileScreen({ navigation }: Props) {
    const [profile, setProfile] = useState<UserProfile | null>(null);
    const [loading, setLoading] = useState(true);
    const [editing, setEditing] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [avatarLoadFailed, setAvatarLoadFailed] = useState(false);

    // Edit form state
    const [editName, setEditName] = useState('');
    const [editPhone, setEditPhone] = useState('');

    const { clearCart } = useCart();

    const fetchProfile = async () => {
        try {
            const data = await getUserProfile();
            const sessionProfile = await getCurrentUserProfile().catch(() => null);
            const mergedPicture = normalizeAvatarUri(data.picture) || normalizeAvatarUri(sessionProfile?.picture);
            setAvatarLoadFailed(false);
            setProfile({
                ...data,
                picture: mergedPicture || undefined,
            });
            setEditName(data.name || data.email?.split('@')[0] || sessionProfile?.displayName || '');
            setEditPhone(data.phone_number || '');
        } catch (error) {
            console.error('Failed to fetch profile:', error);
            // Fallback to session? No, we want to force API usage now.
            Alert.alert('Error', 'Failed to load profile');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchProfile();
    }, []);

    const handleSave = async () => {
        if (!editName.trim()) {
            Alert.alert('Error', 'Name cannot be empty');
            return;
        }

        setLoading(true);
        try {
            const updated = await updateUserProfile({
                name: editName,
                phone_number: editPhone
            });
            setProfile(updated);
            setEditing(false);
            Alert.alert('Success', 'Profile updated');
        } catch (error) {
            console.error('Update failed:', error);
            Alert.alert('Error', 'Failed to update profile');
        } finally {
            setLoading(false);
        }
    };

    const handlePickImage = async () => {
        const result = await ImagePicker.launchImageLibraryAsync({
            mediaTypes: ImagePicker.MediaTypeOptions.Images,
            allowsEditing: true,
            aspect: [1, 1],
            quality: 0.5,
        });

        if (!result.canceled && result.assets && result.assets.length > 0) {
            uploadImage(result.assets[0].uri);
        }
    };

    const uploadImage = async (uri: string) => {
        setUploading(true);
        try {
            // 1. Get Presigned URL
            const { upload_url, s3_key, bucket, region, public_url } = await getAvatarUploadUrl('image/jpeg');

            // 2. Upload to S3
            // Note: In real app, might need to detect mime type from uri. Assuming jpeg for now.
            await uploadAvatarToS3(upload_url, uri, 'image/jpeg');

            // 3. Construct Public URL (Assuming public bucket or we save key)
            // If bucket is public: https://{bucket}.s3.{region}.amazonaws.com/{key}
            // If we save key, we need frontend to know how to construct it.
            // Let's assume we save the key for now and construct URL in render, 
            // OR we save the full URL. Ideally backend logic.
            // Implementation Plan said "S3 URL or Key". 
            // Let's save the FULL URL if possible, or just the key.
            // Let's try to update with the KEY, and see if backend handles it?
            // Backend valid fields: picture.

            // Let's construct the URL to save.
            // Using generic S3 URL structure:
            const s3Url = public_url || `https://${bucket}.s3.${region}.amazonaws.com/${s3_key}`;

            // 4. Update Profile
            const updated = await updateUserProfile({ picture: s3Url });
            setAvatarLoadFailed(false);
            setProfile(updated);

            Alert.alert('Success', 'Profile picture updated');

        } catch (error) {
            console.error('Upload failed:', error);
            Alert.alert('Error', 'Failed to upload image');
        } finally {
            setUploading(false);
        }
    };

    const handleSignOut = () => {
        Alert.alert('Sign Out', 'Do you want to sign out?', [
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
                        console.warn('Sign-out error:', error);
                    } finally {
                        navigation.reset({ index: 0, routes: [{ name: 'Login' }] });
                    }
                },
            },
        ]);
    };

    if (loading && !profile) {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" color={theme.colors.primary} />
            </View>
        );
    }

    const displayName = profile?.name || profile?.email?.split('@')[0] || 'Customer';
    const avatarUri = normalizeAvatarUri(profile?.picture);
    const avatarInitial = displayName.trim().charAt(0).toUpperCase() || 'C';
    const shouldRenderAvatarImage = Boolean(avatarUri) && !avatarLoadFailed;

    return (
        <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.container}
        >
            <ScrollView contentContainerStyle={styles.scrollContent}>
                <View style={styles.card}>
                    <View style={styles.headerColumn}>
                        <TouchableOpacity onPress={handlePickImage} disabled={uploading || editing}>
                            <View style={styles.avatarContainer}>
                                {shouldRenderAvatarImage ? (
                                    <Image
                                        source={{ uri: avatarUri as string }}
                                        style={styles.avatarImage}
                                        resizeMode="cover"
                                        onError={() => setAvatarLoadFailed(true)}
                                    />
                                ) : (
                                    <View style={[styles.avatarImage, styles.avatarFallbackCircle]}>
                                        <Text style={styles.avatarFallbackText}>{avatarInitial}</Text>
                                    </View>
                                )}
                                <View style={styles.editIconBadge}>
                                    <Text style={styles.editIconText}>📷</Text>
                                </View>
                                {uploading && (
                                    <View style={styles.uploadOverlay}>
                                        <ActivityIndicator color="#fff" />
                                    </View>
                                )}
                            </View>
                        </TouchableOpacity>

                        {!editing ? (
                            <>
                                <Text style={styles.name}>{displayName}</Text>
                                <Text style={styles.meta}>{profile?.email}</Text>
                                {profile?.role && profile.role !== 'customer' && (
                                    <View style={styles.roleBadge}>
                                        <Text style={styles.roleText}>{profile?.role?.toUpperCase()}</Text>
                                    </View>
                                )}
                            </>
                        ) : (
                            <View style={styles.editForm}>
                                <Text style={styles.label}>Name</Text>
                                <TextInput
                                    style={styles.input}
                                    value={editName}
                                    onChangeText={setEditName}
                                    placeholder="Full Name"
                                />

                                <Text style={styles.label}>Phone</Text>
                                <TextInput
                                    style={styles.input}
                                    value={editPhone}
                                    onChangeText={setEditPhone}
                                    placeholder="+1234567890"
                                    keyboardType="phone-pad"
                                />
                            </View>
                        )}
                    </View>

                    <View style={styles.buttonRow}>
                        {!editing ? (
                            <TouchableOpacity style={styles.editButton} onPress={() => setEditing(true)}>
                                <Text style={styles.editButtonText}>Edit Profile</Text>
                            </TouchableOpacity>
                        ) : (
                            <View style={styles.saveCancelRow}>
                                <TouchableOpacity style={[styles.editButton, styles.cancelButton]} onPress={() => setEditing(false)}>
                                    <Text style={[styles.editButtonText, styles.cancelText]}>Cancel</Text>
                                </TouchableOpacity>
                                <TouchableOpacity style={[styles.editButton, styles.saveButton]} onPress={handleSave}>
                                    <Text style={[styles.editButtonText, styles.saveText]}>Save</Text>
                                </TouchableOpacity>
                            </View>
                        )}
                    </View>

                    <View style={styles.divider} />

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
            </ScrollView>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
    },
    scrollContent: {
        padding: theme.spacing.lg,
    },
    center: {
        flex: 1,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: theme.colors.background,
    },
    card: {
        ...theme.layout.card,
        padding: theme.spacing.lg,
    },
    headerColumn: {
        alignItems: 'center',
        marginBottom: theme.spacing.lg,
    },
    avatarContainer: {
        position: 'relative',
        marginBottom: theme.spacing.md,
    },
    avatarImage: {
        width: 100,
        height: 100,
        borderRadius: 50,
        borderWidth: 2,
        borderColor: theme.colors.primary,
    },
    avatarFallbackCircle: {
        backgroundColor: theme.colors.primary + '20',
        borderColor: theme.colors.border,
        alignItems: 'center',
        justifyContent: 'center',
    },
    avatarFallbackText: {
        ...theme.typography.h1,
        color: theme.colors.primary,
        fontWeight: '700',
    },
    editIconBadge: {
        position: 'absolute',
        bottom: 0,
        right: 0,
        backgroundColor: theme.colors.surface,
        borderRadius: 12,
        padding: 4,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    editIconText: {
        fontSize: 12,
    },
    uploadOverlay: {
        ...StyleSheet.absoluteFillObject,
        backgroundColor: 'rgba(0,0,0,0.4)',
        borderRadius: 50,
        alignItems: 'center',
        justifyContent: 'center',
    },
    name: {
        ...theme.typography.h2,
        color: theme.colors.text,
        marginBottom: 4,
    },
    meta: {
        ...theme.typography.body,
        color: theme.colors.textSecondary,
    },
    roleBadge: {
        marginTop: 8,
        backgroundColor: theme.colors.primary + '20',
        paddingHorizontal: 8,
        paddingVertical: 2,
        borderRadius: 4,
    },
    roleText: {
        ...theme.typography.caption,
        color: theme.colors.primary,
        fontWeight: '700',
    },
    editForm: {
        width: '100%',
        marginTop: 10,
    },
    label: {
        ...theme.typography.caption,
        color: theme.colors.textSecondary,
        marginBottom: 4,
        marginTop: 8,
    },
    input: {
        borderWidth: 1,
        borderColor: theme.colors.border,
        borderRadius: 8,
        padding: 10,
        fontSize: 16,
        color: theme.colors.text,
        backgroundColor: theme.colors.background,
    },
    buttonRow: {
        marginBottom: theme.spacing.xl,
    },
    editButton: {
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: 20,
        borderWidth: 1,
        borderColor: theme.colors.border,
        alignItems: 'center',
    },
    editButtonText: {
        ...theme.typography.body,
        fontWeight: '600',
    },
    saveCancelRow: {
        flexDirection: 'row',
        gap: 10,
        justifyContent: 'center',
        marginTop: 10,
    },
    cancelButton: {
        backgroundColor: theme.colors.error + '10',
        borderColor: theme.colors.error,
    },
    cancelText: {
        color: theme.colors.error,
    },
    saveButton: {
        backgroundColor: theme.colors.primary,
        borderColor: theme.colors.primary,
    },
    saveText: {
        color: '#fff',
    },
    divider: {
        height: 1,
        backgroundColor: theme.colors.border,
        marginBottom: theme.spacing.lg,
    },
    actionRow: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingVertical: theme.spacing.md,
        borderBottomWidth: 1,
        borderBottomColor: theme.colors.border + '40',
    },
    actionTitle: {
        ...theme.typography.body,
        fontSize: 16,
        color: theme.colors.text,
    },
    chevron: {
        ...theme.typography.h3,
        color: theme.colors.textSecondary,
    },
    signOutButton: {
        marginTop: theme.spacing.xl,
        alignItems: 'center',
        paddingVertical: theme.spacing.md,
    },
    signOutText: {
        ...theme.typography.body,
        color: theme.colors.error,
        fontWeight: '600',
    },
});
