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

export function clearAuthHeaderCache(): void {
    cachedAuthToken = null;
    cachedAuthTokenExpiryMs = 0;
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
}

export interface Order {
    order_id: string;
    restaurant_id: string;
    customer_id?: string;
    status: string;
    items: OrderItem[];
    total_cents: number;
    arrival_status?: string;
    created_at?: string;
    updated_at?: string;
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
    return data.restaurants;
}

/**
 * Get single restaurant details
 */
export async function getRestaurant(restaurantId: string): Promise<Restaurant> {
    // Note: The backend currently only has list_restaurants. 
    // Optimization: We should add a specific GET endpoint. 
    // for now, we filter from the list (inefficient but works for demo).
    const restaurants = await getRestaurants();
    const restaurant = restaurants.find(r => r.restaurant_id === restaurantId);
    if (!restaurant) {
        throw new Error('Restaurant not found');
    }
    return restaurant;
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
    return rawItems.map((item: any) => ({
        id: String(item.id || item.menu_item_id || item.sku || ''),
        name: item.name || 'Menu Item',
        description: item.description || '',
        price_cents: typeof item.price_cents === 'number'
            ? item.price_cents
            : Math.round(Number(item.price || 0) * 100),
        qty: typeof item.qty === 'number' && item.qty > 0 ? item.qty : 1,
    }));
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
    const response = await fetch(`${ORDERS_API_BASE_URL}/v1/orders`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...headers
        },
        body: JSON.stringify({
            restaurant_id: restaurantId,
            items,
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

    return response.json();
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
    return data.orders;
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
