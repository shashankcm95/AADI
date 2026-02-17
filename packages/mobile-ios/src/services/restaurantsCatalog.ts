import AsyncStorage from '@react-native-async-storage/async-storage';
import { getRestaurants, Restaurant } from './api';
import { getCurrentUserProfile } from './session';

const RESTAURANTS_CACHE_PREFIX = 'aadi.restaurants.cache.v1';
const RESTAURANTS_CACHE_TTL_MS = 5 * 60 * 1000;

interface CachedRestaurantsPayload {
    userId: string;
    updatedAt: number;
    restaurants: Restaurant[];
}

function cacheKey(userId: string): string {
    return `${RESTAURANTS_CACHE_PREFIX}:${userId || 'anonymous'}`;
}

function normalizeRestaurants(raw: unknown): Restaurant[] {
    if (!Array.isArray(raw)) {
        return [];
    }

    return raw.filter((restaurant): restaurant is Restaurant => {
        return Boolean(restaurant && typeof restaurant === 'object' && (restaurant as any).restaurant_id);
    });
}

async function readCache(userId: string): Promise<CachedRestaurantsPayload | null> {
    try {
        const raw = await AsyncStorage.getItem(cacheKey(userId));
        if (!raw) {
            return null;
        }

        const parsed = JSON.parse(raw) as Partial<CachedRestaurantsPayload>;
        const updatedAt = Number(parsed.updatedAt);
        if (!Number.isFinite(updatedAt)) {
            return null;
        }

        return {
            userId,
            updatedAt,
            restaurants: normalizeRestaurants(parsed.restaurants),
        };
    } catch (error) {
        console.warn('[restaurantsCatalog] Cache read failed:', error);
        return null;
    }
}

async function writeCache(userId: string, restaurants: Restaurant[]): Promise<void> {
    const payload: CachedRestaurantsPayload = {
        userId,
        updatedAt: Date.now(),
        restaurants,
    };

    try {
        await AsyncStorage.setItem(cacheKey(userId), JSON.stringify(payload));
    } catch (error) {
        console.warn('[restaurantsCatalog] Cache write failed:', error);
    }
}

export async function getRestaurantsWithCache(options?: { forceRefresh?: boolean }): Promise<{
    userId: string;
    restaurants: Restaurant[];
    fromCache: boolean;
}> {
    const forceRefresh = Boolean(options?.forceRefresh);
    const profile = await getCurrentUserProfile();
    const userId = profile.userId || 'anonymous';

    const cached = await readCache(userId);
    const cacheFresh = Boolean(cached && Date.now() - cached.updatedAt < RESTAURANTS_CACHE_TTL_MS);

    if (!forceRefresh && cacheFresh && cached) {
        return {
            userId,
            restaurants: cached.restaurants,
            fromCache: true,
        };
    }

    try {
        const restaurants = await getRestaurants();
        await writeCache(userId, restaurants);

        return {
            userId,
            restaurants,
            fromCache: false,
        };
    } catch (error) {
        if (cached) {
            return {
                userId,
                restaurants: cached.restaurants,
                fromCache: true,
            };
        }
        throw error;
    }
}

export async function clearRestaurantsCache(): Promise<void> {
    const profile = await getCurrentUserProfile();
    const userId = profile.userId || 'anonymous';

    try {
        await AsyncStorage.removeItem(cacheKey(userId));
    } catch (error) {
        console.warn('[restaurantsCatalog] Cache clear failed:', error);
    }
}
