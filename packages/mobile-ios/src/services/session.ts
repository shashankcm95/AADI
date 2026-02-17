import { fetchAuthSession } from 'aws-amplify/auth';

export interface UserProfile {
    userId: string;
    email: string;
    displayName: string;
    givenName?: string;
    familyName?: string;
    phoneNumber?: string;
    picture?: string;
}

export async function getCurrentUserProfile(): Promise<UserProfile> {
    try {
        const session = await fetchAuthSession();
        const rawPayload = session.tokens?.idToken?.payload as Record<string, unknown> | undefined;
        const payload = rawPayload || {};

        const userId = String(payload.sub || '');
        const email = String(payload.email || '');
        const givenName = payload.given_name ? String(payload.given_name) : undefined;
        const familyName = payload.family_name ? String(payload.family_name) : undefined;
        const fullName = payload.name ? String(payload.name) : undefined;

        const displayName = fullName
            || [givenName, familyName].filter(Boolean).join(' ').trim()
            || (email ? email.split('@')[0] : '')
            || 'Customer';

        return {
            userId,
            email,
            displayName,
            givenName,
            familyName,
            phoneNumber: payload.phone_number ? String(payload.phone_number) : undefined,
            picture: payload.picture ? String(payload.picture) : undefined,
        };
    } catch (error) {
        console.warn('[session] Failed to fetch auth session profile:', error);
        return {
            userId: '',
            email: '',
            displayName: 'Customer',
        };
    }
}
