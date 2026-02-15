import React, { useState } from 'react';
import {
    View,
    Text,
    TextInput,
    TouchableOpacity,
    StyleSheet,
    Alert,
    KeyboardAvoidingView,
    Platform,
    ActivityIndicator,
} from 'react-native';
import { fetchAuthSession, signIn, signOut } from 'aws-amplify/auth';
import { theme } from '../theme';

interface Props {
    navigation: any;
}

export default function LoginScreen({ navigation }: Props) {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);

    const handleLogin = async () => {
        if (!email.trim() || !password) {
            Alert.alert('Required', 'Please enter email and password');
            return;
        }

        setLoading(true);
        try {
            const { isSignedIn, nextStep } = await signIn({
                username: email.trim(),
                password: password,
            });

            if (isSignedIn) {
                const session = await fetchAuthSession();
                const claims = session.tokens?.idToken?.payload || {};
                const role = String(claims['custom:role'] || '');
                const groups = claims['cognito:groups'];
                const normalizedGroups = Array.isArray(groups)
                    ? groups.map(String)
                    : typeof groups === 'string'
                        ? [groups]
                        : [];

                const isCustomerAppBlockedRole = (
                    role === 'admin' ||
                    role === 'restaurant_admin' ||
                    normalizedGroups.includes('admin') ||
                    normalizedGroups.includes('restaurant_admin')
                );

                if (isCustomerAppBlockedRole) {
                    await signOut();
                    Alert.alert(
                        'Access Denied',
                        'This account is for restaurant/admin use. Please sign in from the admin portal.'
                    );
                    return;
                }

                navigation.navigate('Home', {
                    customerName: email.split('@')[0],
                });
            } else {
                Alert.alert('Login Incomplete', `Next Step: ${nextStep.signInStep}`);
            }
        } catch (error: any) {
            console.error(error);
            Alert.alert('Login Failed', error.message || 'Unknown error');
        } finally {
            setLoading(false);
        }
    };

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
            <View style={styles.backgroundAccent} />
            <View style={styles.content}>
                <Text style={styles.emoji}>🍔</Text>
                <Text style={styles.title}>AADI</Text>
                <Text style={styles.subtitle}>Order Ahead. Arrive Perfectly.</Text>

                <View style={styles.form}>
                    <Text style={styles.label}>Email</Text>
                    <TextInput
                        style={styles.input}
                        placeholder="user@example.com"
                        placeholderTextColor={theme.colors.textSecondary}
                        value={email}
                        onChangeText={setEmail}
                        autoCapitalize="none"
                        keyboardType="email-address"
                    />

                    <Text style={styles.label}>Password</Text>
                    <TextInput
                        style={styles.input}
                        placeholder="••••••••"
                        placeholderTextColor={theme.colors.textSecondary}
                        value={password}
                        onChangeText={setPassword}
                        secureTextEntry
                    />

                    <TouchableOpacity
                        style={[styles.button, loading && styles.buttonDisabled]}
                        onPress={handleLogin}
                        disabled={loading}
                    >
                        {loading ? (
                            <ActivityIndicator color="#fff" />
                        ) : (
                            <Text style={styles.buttonText}>Sign In</Text>
                        )}
                    </TouchableOpacity>
                </View>

            </View>
        </KeyboardAvoidingView>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: theme.colors.background,
    },
    backgroundAccent: {
        position: 'absolute',
        top: -100,
        right: -100,
        width: 300,
        height: 300,
        backgroundColor: theme.colors.teal3,
        opacity: 0.1,
        borderRadius: 150,
    },
    content: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        padding: 24,
    },
    emoji: {
        fontSize: 64,
        marginBottom: 16,
    },
    title: {
        fontSize: 32,
        fontWeight: '700',
        color: theme.colors.primary,
        marginBottom: 8,
        fontFamily: theme.typography.header.fontFamily,
    },
    subtitle: {
        fontSize: 16,
        color: theme.colors.textMuted,
        marginBottom: 40,
    },
    form: {
        width: '100%',
        maxWidth: 320,
        backgroundColor: 'rgba(255,255,255,0.8)',
        padding: 24,
        borderRadius: 24,
        borderWidth: 1,
        borderColor: '#e2e8f0',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.05,
        shadowRadius: 12,
    },
    label: {
        fontSize: 14,
        color: theme.colors.textMuted,
        marginBottom: 8,
        marginLeft: 4,
        fontWeight: '600',
    },
    input: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
        fontSize: 18,
        color: theme.colors.text,
        marginBottom: 20,
        borderWidth: 1,
        borderColor: '#cbd5e1',
    },
    button: {
        backgroundColor: theme.colors.primary,
        borderRadius: 50,
        padding: 16,
        alignItems: 'center',
        marginTop: 12,
        shadowColor: theme.colors.primary,
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
    },
    buttonDisabled: {
        backgroundColor: theme.colors.textMuted,
        shadowOpacity: 0,
    },
    buttonText: {
        color: '#fff',
        fontSize: 18,
        fontWeight: '600',
    },
});
