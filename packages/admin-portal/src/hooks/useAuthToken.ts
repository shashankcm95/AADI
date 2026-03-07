import { fetchAuthSession } from 'aws-amplify/auth';

/**
 * Returns a fresh ID token on every call.
 * Amplify caches the session internally and only contacts Cognito
 * when the token is near expiry — this is lightweight.
 */
export async function getToken(): Promise<string> {
    const session = await fetchAuthSession();
    const idToken = session.tokens?.idToken?.toString();
    if (!idToken) throw new Error('AUTH_TOKEN_MISSING');
    return idToken;
}
