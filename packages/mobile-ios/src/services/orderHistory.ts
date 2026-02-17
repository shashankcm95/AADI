import AsyncStorage from '@react-native-async-storage/async-storage';
import { getMyOrders, Order } from './api';
import { getCurrentUserProfile } from './session';

const ORDER_CACHE_PREFIX = 'aadi.orders.cache.v1';
const ORDER_CACHE_TTL_MS = 2 * 60 * 1000;

interface CachedOrdersPayload {
    userId: string;
    updatedAt: number;
    orders: Order[];
}

function cacheKey(userId: string): string {
    return `${ORDER_CACHE_PREFIX}:${userId}`;
}

function normalizeOrders(raw: unknown): Order[] {
    if (!Array.isArray(raw)) {
        return [];
    }

    return raw.filter((order): order is Order => Boolean(order && typeof order === 'object' && (order as any).order_id));
}

async function readCache(userId: string): Promise<CachedOrdersPayload | null> {
    if (!userId) {
        return null;
    }

    try {
        const raw = await AsyncStorage.getItem(cacheKey(userId));
        if (!raw) {
            return null;
        }

        const parsed = JSON.parse(raw) as Partial<CachedOrdersPayload>;
        const updatedAt = Number(parsed.updatedAt);
        if (!Number.isFinite(updatedAt)) {
            return null;
        }

        return {
            userId,
            updatedAt,
            orders: normalizeOrders(parsed.orders),
        };
    } catch (error) {
        console.warn('[orderHistory] Cache read failed:', error);
        return null;
    }
}

async function writeCache(userId: string, orders: Order[]): Promise<void> {
    if (!userId) {
        return;
    }

    const payload: CachedOrdersPayload = {
        userId,
        updatedAt: Date.now(),
        orders,
    };

    try {
        await AsyncStorage.setItem(cacheKey(userId), JSON.stringify(payload));
    } catch (error) {
        console.warn('[orderHistory] Cache write failed:', error);
    }
}

export async function getMyOrdersWithCache(options?: { forceRefresh?: boolean }): Promise<{
    userId: string;
    orders: Order[];
    fromCache: boolean;
}> {
    const forceRefresh = Boolean(options?.forceRefresh);
    const profile = await getCurrentUserProfile();
    const userId = profile.userId;

    const cached = await readCache(userId);
    const cacheFresh = Boolean(cached && Date.now() - cached.updatedAt < ORDER_CACHE_TTL_MS);

    if (!forceRefresh && cacheFresh && cached) {
        return {
            userId,
            orders: cached.orders,
            fromCache: true,
        };
    }

    try {
        const orders = await getMyOrders();
        await writeCache(userId, orders);

        return {
            userId,
            orders,
            fromCache: false,
        };
    } catch (error) {
        if (cached) {
            return {
                userId,
                orders: cached.orders,
                fromCache: true,
            };
        }
        throw error;
    }
}

export async function upsertOrderInCache(order: Order): Promise<void> {
    if (!order?.order_id) {
        return;
    }

    const profile = await getCurrentUserProfile();
    const userId = order.customer_id || profile.userId;
    if (!userId) {
        return;
    }

    const cached = await readCache(userId);
    const currentOrders = cached?.orders || [];

    const deduped = [order, ...currentOrders.filter((item) => item.order_id !== order.order_id)];
    await writeCache(userId, deduped);
}

export async function clearMyOrdersCache(): Promise<void> {
    const profile = await getCurrentUserProfile();
    if (!profile.userId) {
        return;
    }

    try {
        await AsyncStorage.removeItem(cacheKey(profile.userId));
    } catch (error) {
        console.warn('[orderHistory] Cache clear failed:', error);
    }
}
