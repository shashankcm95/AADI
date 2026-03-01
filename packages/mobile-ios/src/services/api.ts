import { fetchAuthSession } from 'aws-amplify/auth';
import {
    ORDERS_API_BASE_URL,
    RESTAURANTS_API_BASE_URL,
    USERS_API_BASE_URL,
} from '../config';

/**
 * API Service
 * Agent Kappa: Backend communication
 */

let cachedAuthToken: string | null = null;
let cachedAuthTokenExpiryMs = 0;
// BL-005: Timestamp-based cooldown replaces permanent circuit breaker.
let locationSampleDisabledUntil = 0;

export function clearAuthHeaderCache(): void {
    cachedAuthToken = null;
    cachedAuthTokenExpiryMs = 0;
    locationSampleDisabledUntil = 0;
}

async function getAuthHeaders(): Promise<Record<string, string>> {
    if (cachedAuthToken && Date.now() < cachedAuthTokenExpiryMs) {
        return {
            Authorization: `Bearer ${cachedAuthToken}`,
        };
    }

    try {
        const session = await fetchAuthSession();
        const token = session.tokens?.idToken?.toString();
        if (!token) {
            console.warn("No auth token found, request may fail");
            cachedAuthToken = null;
            cachedAuthTokenExpiryMs = 0;
            return {};
        }

        const expSecondsRaw = (session.tokens?.idToken as any)?.payload?.exp;
        const expSeconds = Number(expSecondsRaw);

        cachedAuthToken = token;
        if (Number.isFinite(expSeconds) && expSeconds > 0) {
            // Refresh one minute before actual token expiry.
            cachedAuthTokenExpiryMs = Math.max(Date.now() + 5000, expSeconds * 1000 - 60_000);
        } else {
            // Fallback short cache if exp claim is missing.
            cachedAuthTokenExpiryMs = Date.now() + 30_000;
        }

        return {
            Authorization: `Bearer ${token}`
        };
    } catch (e) {
        console.error("Auth Session Error", e);
        cachedAuthToken = null;
        cachedAuthTokenExpiryMs = 0;
        return {};
    }
}

export interface OrderItem {
    id: string;
    name: string;
    price_cents: number;
    qty: number;
    description?: string;
    category?: string;
}

export interface Order {
    order_id: string;
    restaurant_id: string;
    customer_id?: string;
    status: string;
    items: OrderItem[];
    total_cents: number;
    arrival_status?: string;
    created_at?: string | number;
    updated_at?: string | number;
}

export interface LeaveAdvisory {
    order_id: string;
    status: string;
    recommended_action: 'LEAVE_NOW' | 'WAIT' | 'FOLLOW_LIVE_STATUS';
    estimated_wait_seconds: number;
    suggested_leave_at: number;
    current_window_start?: number;
    next_window_start?: number;
    current_reserved?: number;
    available_slots?: number;
    max_concurrent?: number;
    window_seconds?: number;
    is_estimate: boolean;
    advisory_note?: string;
}

export interface LocationSample {
    latitude: number;
    longitude: number;
    sample_time?: number;
    accuracy_m?: number;
    speed_mps?: number;
    heading_deg?: number;
}

export interface Restaurant {
    restaurant_id: string;
    name: string;
    cuisine: string;
    rating: number;
    emoji: string;
    address: string;
    latitude?: number;
    longitude?: number;
    price_tier?: number; // 1-4
    tags?: string[];
    image_url?: string;
    banner_image_url?: string;
    restaurant_images?: string[];
    restaurant_image_keys?: string[];
}

export interface Favorite {
    customer_id: string;
    restaurant_id: string;
    created_at?: number;
}

function toFiniteNumber(value: unknown): number | undefined {
    const number = Number(value);
    return Number.isFinite(number) ? number : undefined;
}

function normalizeOrder(raw: any): Order {
    const orderId = String(raw?.order_id || raw?.session_id || '').trim();
    const restaurantId = String(raw?.restaurant_id || raw?.destination_id || '').trim();
    const items = Array.isArray(raw?.items) ? raw.items : [];

    return {
        ...raw,
        order_id: orderId,
        restaurant_id: restaurantId,
        status: String(raw?.status || 'PENDING_NOT_SENT'),
        items,
        total_cents: Math.max(0, Math.round(Number(raw?.total_cents) || 0)),
    };
}

function normalizeRestaurant(raw: any): Restaurant {
    const normalized: any = { ...raw };

    const topLevelLatitude = toFiniteNumber(raw?.latitude);
    const topLevelLongitude = toFiniteNumber(raw?.longitude);
    const locationLatitude = toFiniteNumber(raw?.location?.lat ?? raw?.location?.latitude);
    const locationLongitude = toFiniteNumber(raw?.location?.lon ?? raw?.location?.longitude);

    const latitude = topLevelLatitude ?? locationLatitude;
    const longitude = topLevelLongitude ?? locationLongitude;

    if (latitude !== undefined) {
        normalized.latitude = latitude;
    }
    if (longitude !== undefined) {
        normalized.longitude = longitude;
    }

    return normalized as Restaurant;
}

/**
 * Get list of restaurants
 */
export async function getRestaurants(): Promise<Restaurant[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${RESTAURANTS_API_BASE_URL}/v1/restaurants`, {
        headers: { ...headers }
    });
    if (!response.ok) {
        throw new Error('Failed to fetch restaurants');
    }
    const data = await response.json();
    const restaurants = Array.isArray(data.restaurants) ? data.restaurants : [];
    return restaurants.map(normalizeRestaurant);
}

/**
 * Get single restaurant details
 */
export async function getRestaurant(restaurantId: string): Promise<Restaurant> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${RESTAURANTS_API_BASE_URL}/v1/restaurants/${restaurantId}`, {
        headers: { ...headers }
    });
    if (!response.ok) {
        if (response.status === 404) {
            throw new Error('Restaurant not found');
        }
        throw new Error('Failed to fetch restaurant');
    }
    const data = await response.json();
    return normalizeRestaurant(data);
}

/**
 * Get authenticated customer's favorite restaurants
 */
export async function getFavorites(): Promise<Favorite[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${RESTAURANTS_API_BASE_URL}/v1/favorites`, {
        headers: { ...headers }
    });
    if (!response.ok) {
        throw new Error('Failed to fetch favorites');
    }
    const data = await response.json();
    return Array.isArray(data.favorites) ? data.favorites : [];
}

/**
 * Add a restaurant to authenticated customer's favorites
 */
export async function addFavorite(restaurantId: string): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${RESTAURANTS_API_BASE_URL}/v1/favorites/${restaurantId}`, {
        method: 'PUT',
        headers: { ...headers }
    });
    if (!response.ok) {
        throw new Error('Failed to add favorite');
    }
}

/**
 * Remove a restaurant from authenticated customer's favorites
 */
export async function removeFavorite(restaurantId: string): Promise<void> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${RESTAURANTS_API_BASE_URL}/v1/favorites/${restaurantId}`, {
        method: 'DELETE',
        headers: { ...headers }
    });
    if (!response.ok) {
        throw new Error('Failed to remove favorite');
    }
}

/**
 * Get restaurant menu
 */
export async function getRestaurantMenu(restaurantId: string): Promise<OrderItem[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${RESTAURANTS_API_BASE_URL}/v1/restaurants/${restaurantId}/menu`, {
        headers: { ...headers }
    });
    if (!response.ok) {
        throw new Error('Failed to fetch menu');
    }
    const data = await response.json();
    const rawItems = data.items || data.menu?.items || [];
    return rawItems.map((item: any, index: number) => {
        const rawId = String(item.id || item.menu_item_id || item.sku || '').trim();
        const fallbackToken = String(item.name || 'item').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'item';
        const fallbackId = `local-${restaurantId}-${fallbackToken}-${index}`;

        return {
            id: rawId || fallbackId,
            name: item.name || 'Menu Item',
            description: item.description || '',
            category: item.category || '',
            price_cents: typeof item.price_cents === 'number'
                ? item.price_cents
                : Math.round(Number(item.price || 0) * 100),
            qty: typeof item.qty === 'number' && item.qty > 0 ? item.qty : 1,
        };
    });
}

/**
 * Create a new order
 */
export async function createOrder(
    restaurantId: string,
    items: OrderItem[],
    customerName: string
): Promise<Order> {
    const headers = await getAuthHeaders();
    const sanitizedItems = (Array.isArray(items) ? items : []).map((item, index) => {
        const description = String(item?.description || '').trim();

        return {
            id: String(item?.id || '').trim() || `local-item-${index}`,
            name: String(item?.name || 'Menu Item'),
            price_cents: Math.max(0, Math.round(Number(item?.price_cents) || 0)),
            qty: Math.max(1, Math.round(Number(item?.qty) || 1)),
            ...(description ? { description } : {}),
        };
    });

    // BL-004: Generate idempotency key to prevent duplicate orders on double-tap.
    const idempotencyKey = crypto.randomUUID();

    const response = await fetch(`${ORDERS_API_BASE_URL}/v1/orders`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': idempotencyKey,
            ...headers
        },
        body: JSON.stringify({
            restaurant_id: restaurantId,
            items: sanitizedItems,
            customer_name: customerName,
        }),
    });

    if (!response.ok) {
        const err = await response.text();
        console.error("Create Order Failed:", err);
        throw new Error('Failed to create order');
    }

    return response.json();
}

/**
 * Get order status
 */
export async function getOrder(orderId: string): Promise<Order> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${ORDERS_API_BASE_URL}/v1/orders/${orderId}`, {
        headers: { ...headers }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch order');
    }

    const data = await response.json();
    return normalizeOrder(data);
}

/**
 * Send arrival event (vicinity trigger)
 */
export async function sendArrivalEvent(
    orderId: string,
    event: string
): Promise<{ status: string }> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${ORDERS_API_BASE_URL}/v1/orders/${orderId}/vicinity`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...headers
        },
        body: JSON.stringify({ event }),
    });

    if (!response.ok) {
        throw new Error('Failed to send arrival event');
    }

    return response.json();
}

/**
 * Send a raw location sample for backend telemetry / AWS Location ingestion.
 */
export async function sendLocationSample(
    orderId: string,
    sample: LocationSample
): Promise<{ received: boolean }> {
    if (Date.now() < locationSampleDisabledUntil) {
        return { received: false };
    }

    const headers = await getAuthHeaders();
    const response = await fetch(`${ORDERS_API_BASE_URL}/v1/orders/${orderId}/location`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...headers,
        },
        body: JSON.stringify(sample),
    });

    if (!response.ok) {
        let details = '';
        let body = '';
        try {
            body = await response.text();
            details = body ? ` ${body.slice(0, 300)}` : '';
        } catch {
            // Ignore body parse issues; status code is still useful.
        }

        if (response.status === 404 && body.includes('"message":"Not Found"')) {
            locationSampleDisabledUntil = Date.now() + 5 * 60 * 1000;
            console.warn('[API] Location sample route not found; retrying after 5-minute cooldown.');
            return { received: false };
        }

        throw new Error(`Failed to send location sample (HTTP ${response.status}).${details}`);
    }

    return response.json();
}

/**
 * Get non-reserving leave-time estimate for an order.
 */
export async function getLeaveAdvisory(orderId: string): Promise<LeaveAdvisory> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${ORDERS_API_BASE_URL}/v1/orders/${orderId}/advisory`, {
        headers: { ...headers }
    });
    if (!response.ok) {
        throw new Error('Failed to fetch leave advisory');
    }
    return response.json();
}



/**
 * Get my orders (authenticated user's order history)
 */
export async function getMyOrders(): Promise<Order[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${ORDERS_API_BASE_URL}/v1/orders`, {
        headers: { ...headers }
    });
    if (!response.ok) {
        throw new Error('Failed to fetch orders');
    }
    const data = await response.json();
    const orders = Array.isArray(data?.orders) ? data.orders : [];
    return orders.map((order: any) => normalizeOrder(order));
}


/**
 * Users Service
 */

export interface UserProfile {
    user_id: string;
    email?: string;
    role?: string;
    name?: string;
    phone_number?: string;
    picture?: string;
    created_at?: number;
    updated_at?: number;
}

export async function getUserProfile(): Promise<UserProfile> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${USERS_API_BASE_URL}/v1/users/me`, {
        headers: { ...headers }
    });

    if (!response.ok) {
        throw new Error('Failed to fetch profile');
    }

    return response.json();
}

export async function updateUserProfile(data: { name?: string; phone_number?: string; picture?: string }): Promise<UserProfile> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${USERS_API_BASE_URL}/v1/users/me`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            ...headers
        },
        body: JSON.stringify(data)
    });

    if (!response.ok) {
        throw new Error('Failed to update profile');
    }

    return response.json();
}

export async function getAvatarUploadUrl(contentType: string): Promise<{
    upload_url: string;
    s3_key: string;
    bucket?: string;
    region?: string;
    public_url?: string;
}> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${USERS_API_BASE_URL}/v1/users/me/avatar/upload-url`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...headers
        },
        body: JSON.stringify({ content_type: contentType })
    });

    if (!response.ok) {
        throw new Error('Failed to get upload URL');
    }

    return response.json();
}

export async function uploadAvatarToS3(uploadUrl: string, fileUri: string, contentType: string): Promise<void> {
    const response = await fetch(fileUri);
    const blob = await response.blob();

    const uploadResponse = await fetch(uploadUrl, {
        method: 'PUT',
        headers: {
            'Content-Type': contentType
        },
        body: blob
    });

    if (!uploadResponse.ok) {
        throw new Error('Failed to upload avatar to S3');
    }
}
