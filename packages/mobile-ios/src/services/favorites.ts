import AsyncStorage from '@react-native-async-storage/async-storage';
import { addFavorite, Favorite, getFavorites, removeFavorite } from './api';
import { getCurrentUserProfile } from './session';

const FAVORITES_CACHE_PREFIX = 'aadi.favorites.cache.v1';
const FAVORITES_CACHE_TTL_MS = 2 * 60 * 1000;

interface CachedFavoritesPayload {
    userId: string;
    updatedAt: number;
    favoriteRestaurantIds: string[];
}

function cacheKey(userId: string): string {
    return `${FAVORITES_CACHE_PREFIX}:${userId}`;
}

function normalizeFavoriteIds(raw: unknown): string[] {
    if (!Array.isArray(raw)) {
        return [];
    }

    const ids = raw
        .map((item) => String(item || '').trim())
        .filter(Boolean);

    return Array.from(new Set(ids));
}

function toFavoriteIds(favorites: Favorite[]): string[] {
    const ids = favorites
        .map((item) => String(item?.restaurant_id || '').trim())
        .filter(Boolean);

    return Array.from(new Set(ids));
}

async function readCache(userId: string): Promise<CachedFavoritesPayload | null> {
    if (!userId) {
        return null;
    }

    try {
        const raw = await AsyncStorage.getItem(cacheKey(userId));
        if (!raw) {
            return null;
        }

        const parsed = JSON.parse(raw) as Partial<CachedFavoritesPayload>;
        const updatedAt = Number(parsed.updatedAt);

        if (!Number.isFinite(updatedAt)) {
            return null;
        }

        return {
            userId,
            updatedAt,
            favoriteRestaurantIds: normalizeFavoriteIds(parsed.favoriteRestaurantIds),
        };
    } catch (error) {
        console.warn('[favorites] Cache read failed:', error);
        return null;
    }
}

async function writeCache(userId: string, favoriteRestaurantIds: string[]): Promise<void> {
    if (!userId) {
        return;
    }

    const payload: CachedFavoritesPayload = {
        userId,
        updatedAt: Date.now(),
        favoriteRestaurantIds: normalizeFavoriteIds(favoriteRestaurantIds),
    };

    try {
        await AsyncStorage.setItem(cacheKey(userId), JSON.stringify(payload));
    } catch (error) {
        console.warn('[favorites] Cache write failed:', error);
    }
}

export function favoriteIdsToMap(favoriteRestaurantIds: string[]): Record<string, boolean> {
    return favoriteRestaurantIds.reduce<Record<string, boolean>>((acc, restaurantId) => {
        if (restaurantId) {
            acc[restaurantId] = true;
        }
        return acc;
    }, {});
}

export async function getFavoritesWithCache(options?: { forceRefresh?: boolean }): Promise<{
    userId: string;
    favoriteRestaurantIds: string[];
    fromCache: boolean;
}> {
    const forceRefresh = Boolean(options?.forceRefresh);
    const profile = await getCurrentUserProfile();
    const userId = profile.userId;

    const cached = await readCache(userId);
    const cacheFresh = Boolean(cached && Date.now() - cached.updatedAt < FAVORITES_CACHE_TTL_MS);

    if (!forceRefresh && cacheFresh && cached) {
        return {
            userId,
            favoriteRestaurantIds: cached.favoriteRestaurantIds,
            fromCache: true,
        };
    }

    try {
        const favorites = await getFavorites();
        const favoriteRestaurantIds = toFavoriteIds(favorites);
        await writeCache(userId, favoriteRestaurantIds);

        return {
            userId,
            favoriteRestaurantIds,
            fromCache: false,
        };
    } catch (error) {
        if (cached) {
            return {
                userId,
                favoriteRestaurantIds: cached.favoriteRestaurantIds,
                fromCache: true,
            };
        }

        throw error;
    }
}

export async function setFavoriteForCurrentUser(restaurantId: string, shouldFavorite: boolean): Promise<void> {
    if (!restaurantId) {
        return;
    }

    const profile = await getCurrentUserProfile();
    const userId = profile.userId;

    if (!userId) {
        throw new Error('No authenticated user');
    }

    if (shouldFavorite) {
        await addFavorite(restaurantId);
    } else {
        await removeFavorite(restaurantId);
    }

    const cached = await readCache(userId);
    const nextSet = new Set(cached?.favoriteRestaurantIds || []);

    if (shouldFavorite) {
        nextSet.add(restaurantId);
    } else {
        nextSet.delete(restaurantId);
    }

    await writeCache(userId, Array.from(nextSet));
}

export async function clearMyFavoritesCache(): Promise<void> {
    const profile = await getCurrentUserProfile();

    if (!profile.userId) {
        return;
    }

    try {
        await AsyncStorage.removeItem(cacheKey(profile.userId));
    } catch (error) {
        console.warn('[favorites] Cache clear failed:', error);
    }
}
