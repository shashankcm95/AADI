/**
 * Centralized API layer for the admin portal.
 *
 * Every outbound request goes through `apiFetch`, which attaches a fresh
 * Cognito ID token (via getToken) and throws `ApiError` on non-2xx responses.
 */
import { getToken } from '../hooks/useAuthToken'
import { API_BASE_URL, ORDERS_API_URL } from '../aws-exports'
import { Restaurant, RestaurantFormData, MenuItem, Order } from '../types'

// ── Error type ──

export class ApiError extends Error {
    constructor(public status: number, message: string) {
        super(message)
        this.name = 'ApiError'
    }
}

// ── Core fetch wrapper ──

async function apiFetch(url: string, options?: RequestInit): Promise<Response> {
    const token = await getToken()
    const res = await fetch(url, {
        ...options,
        headers: {
            ...options?.headers,
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
        },
    })
    if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new ApiError(
            res.status,
            body?.error || body?.message || `Request failed (${res.status})`,
        )
    }
    return res
}

// ── Restaurants ──

export async function fetchRestaurants(): Promise<Restaurant[]> {
    const res = await apiFetch(`${API_BASE_URL}/v1/restaurants`)
    const data = await res.json()
    return data.restaurants || []
}

export async function createRestaurant(
    payload: Record<string, unknown>,
): Promise<{ restaurant_id: string; user_status?: string }> {
    const res = await apiFetch(`${API_BASE_URL}/v1/restaurants`, {
        method: 'POST',
        body: JSON.stringify(payload),
    })
    return res.json()
}

export async function updateRestaurant(
    restaurantId: string,
    data: Partial<RestaurantFormData>,
): Promise<void> {
    await apiFetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
    })
}

export async function deleteRestaurant(restaurantId: string): Promise<void> {
    await apiFetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}`, {
        method: 'DELETE',
    })
}

// ── Menu ──

export async function fetchMenu(restaurantId: string): Promise<MenuItem[]> {
    const res = await apiFetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}/menu`)
    const data = await res.json()
    return data.items || []
}

export async function importMenu(
    restaurantId: string,
    items: Record<string, string | number | undefined>[],
): Promise<void> {
    await apiFetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}/menu`, {
        method: 'POST',
        body: JSON.stringify({ items }),
    })
}

// ── Orders ──

export async function fetchOrders(restaurantId: string): Promise<Order[]> {
    const res = await apiFetch(`${ORDERS_API_URL}/v1/restaurants/${restaurantId}/orders`)
    const data = await res.json()
    return data.orders || []
}

export async function ackOrder(
    restaurantId: string,
    orderId: string,
): Promise<void> {
    await apiFetch(`${ORDERS_API_URL}/v1/restaurants/${restaurantId}/orders/${orderId}/ack`, {
        method: 'POST',
    })
}

export async function updateOrderStatus(
    restaurantId: string,
    orderId: string,
    status: string,
): Promise<void> {
    await apiFetch(`${ORDERS_API_URL}/v1/restaurants/${restaurantId}/orders/${orderId}/status`, {
        method: 'POST',
        body: JSON.stringify({ status }),
    })
}

// ── Restaurant Config ──

export async function fetchRestaurantConfig(
    restaurantId: string,
): Promise<Record<string, unknown>> {
    const res = await apiFetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}/config`)
    return res.json()
}

export async function updateRestaurantConfig(
    restaurantId: string,
    data: Record<string, unknown>,
): Promise<Record<string, unknown>> {
    const res = await apiFetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}/config`, {
        method: 'PUT',
        body: JSON.stringify(data),
    })
    return res.json()
}

// ── Global Config (Super Admin) ──

export async function fetchGlobalConfig(): Promise<Record<string, unknown>> {
    const res = await apiFetch(`${API_BASE_URL}/v1/admin/global-config`)
    return res.json()
}

export async function updateGlobalConfig(
    data: Record<string, unknown>,
): Promise<Record<string, unknown>> {
    const res = await apiFetch(`${API_BASE_URL}/v1/admin/global-config`, {
        method: 'PUT',
        body: JSON.stringify(data),
    })
    return res.json()
}

// ── Images ──

export interface UploadUrlResponse {
    upload_url: string;
    object_key: string;
    preview_url?: string;
}

export async function getImageUploadUrl(
    restaurantId: string,
    fileName: string,
    contentType: string,
): Promise<UploadUrlResponse> {
    const res = await apiFetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}/images/upload-url`, {
        method: 'POST',
        body: JSON.stringify({ file_name: fileName, content_type: contentType }),
    })
    return res.json()
}
