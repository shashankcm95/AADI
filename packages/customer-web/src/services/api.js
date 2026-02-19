import { RESTAURANTS_API_URL, USERS_API_URL } from '../config';
import { fetchAuthSession } from 'aws-amplify/auth';

async function getAuthHeaders() {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (!token) {
        throw new Error('Missing auth token');
    }
    return {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };
}

/* ── Users ── */

export async function getUserProfile() {
    const headers = await getAuthHeaders();
    const res = await fetch(`${USERS_API_URL}/v1/users/me`, { headers });
    if (!res.ok) throw new Error('Failed to fetch profile');
    return res.json();
}

export async function updateUserProfile(data) {
    const headers = await getAuthHeaders();
    const res = await fetch(`${USERS_API_URL}/v1/users/me`, {
        method: 'PUT',
        headers,
        body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to update profile');
    return res.json();
}

export async function getAvatarUploadUrl(contentType) {
    const headers = await getAuthHeaders();
    const res = await fetch(`${USERS_API_URL}/v1/users/me/avatar/upload-url`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ content_type: contentType })
    });
    if (!res.ok) throw new Error('Failed to get upload URL');
    return res.json();
}

export async function uploadAvatarToS3(uploadUrl, file, contentType = 'image/jpeg') {
    const res = await fetch(uploadUrl, {
        method: 'PUT',
        headers: {
            'Content-Type': contentType
        },
        body: file
    });
    if (!res.ok) throw new Error('Failed to upload avatar');
}

/* ── Favorites ── */

export async function getFavorites() {
    const headers = await getAuthHeaders();
    const res = await fetch(`${RESTAURANTS_API_URL}/v1/favorites`, { headers });
    if (!res.ok) throw new Error('Failed to fetch favorites');
    const data = await res.json();
    return data.favorites || [];
}

export async function addFavorite(restaurantId) {
    const headers = await getAuthHeaders();
    const res = await fetch(`${RESTAURANTS_API_URL}/v1/favorites/${restaurantId}`, {
        method: 'PUT',
        headers
    });
    if (!res.ok) throw new Error('Failed to add favorite');
}

export async function removeFavorite(restaurantId) {
    const headers = await getAuthHeaders();
    const res = await fetch(`${RESTAURANTS_API_URL}/v1/favorites/${restaurantId}`, {
        method: 'DELETE',
        headers
    });
    if (!res.ok) throw new Error('Failed to remove favorite');
}
