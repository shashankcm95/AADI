import React, { useEffect, useState } from 'react';
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
    Image,
} from 'react-native';
import {
    confirmResetPassword,
    confirmSignUp,
    fetchAuthSession,
    resendSignUpCode,
    resetPassword,
    signIn,
    signOut,
    signUp,
} from 'aws-amplify/auth';
import { theme } from '../theme';

interface Props {
    navigation: any;
}

type AuthMode =
    | 'signIn'
    | 'signUp'
    | 'confirmSignUp'
    | 'resetPassword'
    | 'confirmResetPassword';

function normalizeEmail(value: string): string {
    return value.trim().toLowerCase();
}

function mapAuthError(error: any): string {
    const name = String(error?.name || error?.code || '');
    const message = String(error?.message || '');

    switch (name) {
        case 'UserNotFoundException':
            return 'No account found for this email. Please sign up first.';
        case 'NotAuthorizedException':
            return 'Incorrect email or password.';
        case 'UserNotConfirmedException':
            return 'Account is not verified yet. Enter your verification code.';
        case 'UsernameExistsException':
            return 'An account already exists for this email. Please sign in.';
        case 'CodeMismatchException':
            return 'The verification code is invalid.';
        case 'ExpiredCodeException':
            return 'The verification code has expired. Request a new code.';
        case 'LimitExceededException':
            return 'Too many attempts. Please wait a moment and try again.';
        case 'PasswordResetRequiredException':
            return 'Password reset required. Use Forgot password to set a new password.';
        case 'InvalidPasswordException':
            return 'Password does not meet policy requirements.';
        case 'NetworkError':
            return 'Network error. Check your connection and try again.';
        case 'Unknown':
            return 'Authentication failed. If this is a new account, sign up and verify your email.';
        default:
            if (message && message !== 'An unknown error has occurred.') {
                return message;
            }
            if (name) {
                return `Auth error: ${name}`;
            }
            return 'An unknown error has occurred.';
    }
}

function codeDeliveryMessage(details: any, fallbackEmail: string): string {
    const medium = details?.deliveryMedium || 'EMAIL';
    const destination = details?.destination || fallbackEmail;
    return `A verification code was sent via ${medium} to ${destination}.`;
}

export default function LoginScreen({ navigation }: Props) {
    const [mode, setMode] = useState<AuthMode>('signIn');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [verificationCode, setVerificationCode] = useState('');
    const [resetCode, setResetCode] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [pendingEmail, setPendingEmail] = useState('');
    const [loading, setLoading] = useState(false);

    const navigateCustomerHome = async (normalizedEmail: string) => {
        const session = await fetchAuthSession();
        const claims = session.tokens?.idToken?.payload || {};
        const role = String(claims['custom:role'] || '');
        const claimEmail = String(claims.email || '').toLowerCase();
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
            try {
                await signOut();
            } catch (err) {
                console.warn('[Auth] Sign-out after role block failed:', err);
            }
            Alert.alert(
                'Access Denied',
                'This account is for restaurant/admin use. Please sign in from the admin portal.'
            );
            return;
        }

        navigation.navigate('Home', {
            customerName: (claimEmail || normalizedEmail).split('@')[0] || 'Guest',
        });
    };

    const handleSignInNextStep = async (nextStep: any, normalizedEmail: string) => {
        if (nextStep.signInStep === 'CONFIRM_SIGN_UP') {
            setPendingEmail(normalizedEmail);
            setMode('confirmSignUp');
            Alert.alert(
                'Verification Required',
                codeDeliveryMessage(null, normalizedEmail)
            );
            return;
        }

        if (nextStep.signInStep === 'RESET_PASSWORD') {
            setPendingEmail(normalizedEmail);
            setMode('resetPassword');
            Alert.alert(
                'Password Reset Required',
                'Please request a reset code and set a new password.'
            );
            return;
        }

        Alert.alert('Sign In Incomplete', `Next Step: ${nextStep.signInStep}`);
    };

    useEffect(() => {
        let cancelled = false;

        const resumeExistingSession = async () => {
            try {
                const session = await fetchAuthSession();
                const token = session.tokens?.idToken;
                if (!token || cancelled) {
                    return;
                }
                const claimEmail = String(token.payload?.email || '');
                await navigateCustomerHome(claimEmail);
            } catch {
                // No active session; stay on login.
            }
        };

        resumeExistingSession();

        return () => {
            cancelled = true;
        };
    }, []);

    const handleSignIn = async () => {
        const normalizedEmail = normalizeEmail(email);
        if (!normalizedEmail || !password) {
            Alert.alert('Required', 'Please enter email and password');
            return;
        }

        setLoading(true);
        try {
            const { isSignedIn, nextStep } = await signIn({
                username: normalizedEmail,
                password,
                options: {
                    authFlowType: 'USER_PASSWORD_AUTH',
                },
            });

            if (isSignedIn) {
                await navigateCustomerHome(normalizedEmail);
                return;
            }

            await handleSignInNextStep(nextStep, normalizedEmail);
        } catch (error: any) {
            const errorName = String(error?.name || error?.code || '');
            if (errorName === 'UserAlreadyAuthenticatedException') {
                console.warn('[Auth] Session already active. Reusing existing session.');
                try {
                    await navigateCustomerHome(normalizedEmail);
                    return;
                } catch (resumeErr: any) {
                    console.warn('[Auth] Could not reuse session, signing out and retrying sign-in.', resumeErr);
                    try {
                        await signOut();
                        const retry = await signIn({
                            username: normalizedEmail,
                            password,
                            options: { authFlowType: 'USER_PASSWORD_AUTH' },
                        });

                        if (retry.isSignedIn) {
                            await navigateCustomerHome(normalizedEmail);
                            return;
                        }

                        await handleSignInNextStep(retry.nextStep, normalizedEmail);
                        return;
                    } catch (retryErr: any) {
                        console.error('[Auth] Retry sign-in failed:', retryErr);
                        Alert.alert('Sign In Failed', mapAuthError(retryErr));
                        return;
                    }
                }
            }
            console.error('[Auth] Sign-in failed:', error);
            Alert.alert('Sign In Failed', mapAuthError(error));
        } finally {
            setLoading(false);
        }
    };

    const handleSignUp = async () => {
        const normalizedEmail = normalizeEmail(email);
        if (!normalizedEmail || !password || !confirmPassword) {
            Alert.alert('Required', 'Please fill email, password, and confirm password.');
            return;
        }

        if (password !== confirmPassword) {
            Alert.alert('Password Mismatch', 'Password and confirm password must match.');
            return;
        }

        setLoading(true);
        try {
            const { isSignUpComplete, nextStep } = await signUp({
                username: normalizedEmail,
                password,
                options: {
                    userAttributes: {
                        email: normalizedEmail,
                    },
                },
            });

            setPendingEmail(normalizedEmail);
            setEmail(normalizedEmail);
            setPassword('');
            setConfirmPassword('');

            if (isSignUpComplete) {
                setMode('signIn');
                Alert.alert('Account Created', 'Your customer account is ready. Please sign in.');
                return;
            }

            if (nextStep.signUpStep === 'CONFIRM_SIGN_UP') {
                setMode('confirmSignUp');
                Alert.alert(
                    'Verify Your Email',
                    codeDeliveryMessage(nextStep?.codeDeliveryDetails, normalizedEmail)
                );
                return;
            }

            Alert.alert('Sign Up Incomplete', `Next Step: ${nextStep.signUpStep}`);
        } catch (error: any) {
            console.error('[Auth] Sign-up failed:', error);
            Alert.alert('Sign Up Failed', mapAuthError(error));
        } finally {
            setLoading(false);
        }
    };

    const handleConfirmSignUp = async () => {
        const username = pendingEmail || normalizeEmail(email);
        if (!username) {
            Alert.alert('Missing Email', 'Please provide the email used to sign up.');
            return;
        }
        if (!verificationCode.trim()) {
            Alert.alert('Required', 'Please enter the verification code.');
            return;
        }

        setLoading(true);
        try {
            const { isSignUpComplete, nextStep } = await confirmSignUp({
                username,
                confirmationCode: verificationCode.trim(),
            });

            if (isSignUpComplete) {
                setMode('signIn');
                setEmail(username);
                setVerificationCode('');
                Alert.alert(
                    'Verified',
                    'Account verified. Sign in with the same password you used during sign up.'
                );
                return;
            }

            Alert.alert('Verification Incomplete', `Next Step: ${nextStep.signUpStep}`);
        } catch (error: any) {
            console.error('[Auth] Confirm sign-up failed:', error);
            Alert.alert('Verification Failed', mapAuthError(error));
        } finally {
            setLoading(false);
        }
    };

    const handleResendCode = async () => {
        const username = pendingEmail || normalizeEmail(email);
        if (!username) {
            Alert.alert('Missing Email', 'Enter your email before requesting a new code.');
            return;
        }

        setLoading(true);
        try {
            const result = await resendSignUpCode({ username });
            Alert.alert('Code Sent', codeDeliveryMessage(result, username));
        } catch (error: any) {
            console.error('[Auth] Resend code failed:', error);
            Alert.alert('Resend Failed', mapAuthError(error));
        } finally {
            setLoading(false);
        }
    };

    const handleStartResetPassword = async (emailOverride?: string) => {
        const normalizedEmail = normalizeEmail(emailOverride ?? email);
        if (!normalizedEmail) {
            Alert.alert('Required', 'Please enter your email first.');
            return;
        }

        setLoading(true);
        try {
            const result = await resetPassword({ username: normalizedEmail });
            setPendingEmail(normalizedEmail);

            if (result.nextStep.resetPasswordStep === 'CONFIRM_RESET_PASSWORD_WITH_CODE') {
                setMode('confirmResetPassword');
                Alert.alert(
                    'Reset Code Sent',
                    codeDeliveryMessage(result.nextStep.codeDeliveryDetails, normalizedEmail)
                );
                return;
            }

            setMode('signIn');
            Alert.alert('Password Reset', 'Password reset flow completed. Please sign in.');
        } catch (error: any) {
            console.error('[Auth] Reset password request failed:', error);
            Alert.alert('Reset Request Failed', mapAuthError(error));
        } finally {
            setLoading(false);
        }
    };

    const handleConfirmResetPassword = async () => {
        const username = pendingEmail || normalizeEmail(email);
        if (!username) {
            Alert.alert('Missing Email', 'Please enter your email.');
            return;
        }
        if (!resetCode.trim() || !newPassword) {
            Alert.alert('Required', 'Please enter reset code and new password.');
            return;
        }

        setLoading(true);
        try {
            await confirmResetPassword({
                username,
                confirmationCode: resetCode.trim(),
                newPassword,
            });

            setMode('signIn');
            setEmail(username);
            setPassword('');
            setResetCode('');
            setNewPassword('');
            Alert.alert('Password Updated', 'Your password has been reset. Please sign in.');
        } catch (error: any) {
            console.error('[Auth] Confirm reset password failed:', error);
            Alert.alert('Reset Failed', mapAuthError(error));
        } finally {
            setLoading(false);
        }
    };

    const isConfirmSignUpMode = mode === 'confirmSignUp';
    const isSignUpMode = mode === 'signUp';
    const isResetMode = mode === 'resetPassword';
    const isConfirmResetMode = mode === 'confirmResetPassword';
    const isAnyConfirmMode = isConfirmSignUpMode || isConfirmResetMode;
    const lockedEmail = isAnyConfirmMode && Boolean(pendingEmail);
    const effectiveEmailValue = lockedEmail ? pendingEmail : email;

    const subtitle = isConfirmSignUpMode
        ? 'Confirm your customer account'
        : isSignUpMode
            ? 'Create a customer account'
            : isResetMode
                ? 'Reset your password'
                : isConfirmResetMode
                    ? 'Set a new password'
                    : 'Order Ahead. Arrive Perfectly.';

    const onPrimaryAction = () => {
        if (mode === 'signIn') {
            handleSignIn();
        } else if (mode === 'signUp') {
            handleSignUp();
        } else if (mode === 'confirmSignUp') {
            handleConfirmSignUp();
        } else if (mode === 'resetPassword') {
            handleStartResetPassword();
        } else {
            handleConfirmResetPassword();
        }
    };

    const primaryLabel = isConfirmSignUpMode
        ? 'Verify Code'
        : isSignUpMode
            ? 'Create Account'
            : isResetMode
                ? 'Send Reset Code'
                : isConfirmResetMode
                    ? 'Update Password'
                    : 'Sign In';

    return (
        <KeyboardAvoidingView
            style={styles.container}
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
            <View style={styles.backgroundAccent} />
            <View style={styles.content}>
                <View style={styles.brandRow}>
                    <Image
                        source={require('../../assets/logo_icon_stylized.png')}
                        style={styles.logo}
                        resizeMode="cover"
                    />
                    <Text style={styles.title}>AADI</Text>
                </View>
                <Text style={styles.subtitle}>{subtitle}</Text>

                <View style={styles.form}>
                    <Text style={styles.label}>Email</Text>
                    <TextInput
                        style={styles.input}
                        placeholder="user@example.com"
                        placeholderTextColor={theme.colors.textSecondary}
                        value={effectiveEmailValue}
                        onChangeText={setEmail}
                        editable={!lockedEmail}
                        autoCapitalize="none"
                        keyboardType="email-address"
                        autoCorrect={false}
                        autoComplete="email"
                    />

                    {(mode === 'signIn' || mode === 'signUp') && (
                        <>
                            <Text style={styles.label}>Password</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="••••••••"
                                placeholderTextColor={theme.colors.textSecondary}
                                value={password}
                                onChangeText={setPassword}
                                secureTextEntry
                                autoCapitalize="none"
                                autoCorrect={false}
                            />
                        </>
                    )}

                    {isSignUpMode && (
                        <>
                            <Text style={styles.label}>Confirm Password</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="••••••••"
                                placeholderTextColor={theme.colors.textSecondary}
                                value={confirmPassword}
                                onChangeText={setConfirmPassword}
                                secureTextEntry
                                autoCapitalize="none"
                                autoCorrect={false}
                            />
                        </>
                    )}

                    {isConfirmSignUpMode && (
                        <>
                            <Text style={styles.helperText}>
                                Enter the verification code sent to your email.
                            </Text>
                            <Text style={styles.label}>Verification Code</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="123456"
                                placeholderTextColor={theme.colors.textSecondary}
                                value={verificationCode}
                                onChangeText={setVerificationCode}
                                keyboardType="number-pad"
                                autoCapitalize="none"
                                autoCorrect={false}
                            />
                        </>
                    )}

                    {isConfirmResetMode && (
                        <>
                            <Text style={styles.helperText}>
                                Enter the reset code and choose a new password.
                            </Text>
                            <Text style={styles.label}>Reset Code</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="123456"
                                placeholderTextColor={theme.colors.textSecondary}
                                value={resetCode}
                                onChangeText={setResetCode}
                                keyboardType="number-pad"
                                autoCapitalize="none"
                                autoCorrect={false}
                            />
                            <Text style={styles.label}>New Password</Text>
                            <TextInput
                                style={styles.input}
                                placeholder="••••••••"
                                placeholderTextColor={theme.colors.textSecondary}
                                value={newPassword}
                                onChangeText={setNewPassword}
                                secureTextEntry
                                autoCapitalize="none"
                                autoCorrect={false}
                            />
                        </>
                    )}

                    <TouchableOpacity
                        style={[styles.button, loading && styles.buttonDisabled]}
                        onPress={onPrimaryAction}
                        disabled={loading}
                    >
                        {loading ? (
                            <ActivityIndicator color="#fff" />
                        ) : (
                            <Text style={styles.buttonText}>{primaryLabel}</Text>
                        )}
                    </TouchableOpacity>

                    {mode === 'signIn' && (
                        <>
                            <TouchableOpacity
                                style={styles.linkButton}
                                onPress={() => {
                                    setMode('signUp');
                                    setVerificationCode('');
                                }}
                                disabled={loading}
                            >
                                <Text style={styles.linkText}>New customer? Create account</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={styles.linkButton}
                                onPress={() => {
                                    setMode('resetPassword');
                                    setPendingEmail('');
                                    setResetCode('');
                                    setNewPassword('');
                                }}
                                disabled={loading}
                            >
                                <Text style={styles.linkText}>Forgot password?</Text>
                            </TouchableOpacity>
                        </>
                    )}

                    {mode === 'signUp' && (
                        <TouchableOpacity
                            style={styles.linkButton}
                            onPress={() => {
                                setMode('signIn');
                                setConfirmPassword('');
                                setVerificationCode('');
                            }}
                            disabled={loading}
                        >
                            <Text style={styles.linkText}>Already have an account? Sign in</Text>
                        </TouchableOpacity>
                    )}

                    {mode === 'confirmSignUp' && (
                        <>
                            <TouchableOpacity
                                style={styles.linkButton}
                                onPress={handleResendCode}
                                disabled={loading}
                            >
                                <Text style={styles.linkText}>Resend code</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={styles.linkButton}
                                onPress={() => {
                                    setMode('signIn');
                                    setVerificationCode('');
                                }}
                                disabled={loading}
                            >
                                <Text style={styles.linkText}>Back to sign in</Text>
                            </TouchableOpacity>
                        </>
                    )}

                    {mode === 'resetPassword' && (
                        <TouchableOpacity
                            style={styles.linkButton}
                            onPress={() => {
                                setMode('signIn');
                                setPendingEmail('');
                            }}
                            disabled={loading}
                        >
                            <Text style={styles.linkText}>Back to sign in</Text>
                        </TouchableOpacity>
                    )}

                    {mode === 'confirmResetPassword' && (
                        <>
                            <TouchableOpacity
                                style={styles.linkButton}
                                onPress={() => handleStartResetPassword(pendingEmail || email)}
                                disabled={loading}
                            >
                                <Text style={styles.linkText}>Resend reset code</Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                                style={styles.linkButton}
                                onPress={() => {
                                    setMode('signIn');
                                    setResetCode('');
                                    setNewPassword('');
                                }}
                                disabled={loading}
                            >
                                <Text style={styles.linkText}>Back to sign in</Text>
                            </TouchableOpacity>
                        </>
                    )}
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
    brandRow: {
        flexDirection: 'row',
        alignItems: 'center',
        marginBottom: 12,
        gap: theme.spacing.sm,
    },
    logo: {
        width: 52,
        height: 52,
        borderRadius: 14,
        borderWidth: 1,
        borderColor: theme.colors.border,
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
    linkButton: {
        alignItems: 'center',
        marginTop: 12,
    },
    linkText: {
        fontSize: 14,
        color: theme.colors.primary,
        fontWeight: '600',
    },
    helperText: {
        marginBottom: 12,
        color: theme.colors.textMuted,
        fontSize: 13,
    },
});
