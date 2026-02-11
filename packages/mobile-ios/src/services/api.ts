import { fetchAuthSession } from 'aws-amplify/auth';

/**
 * API Service
 * Agent Kappa: Backend communication
 */

// API Base URL — set via environment config per build target
// For physical device testing, use your Mac's IP instead of localhost
const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'https://f7mqfaxh8i.execute-api.us-east-1.amazonaws.com';

async function getAuthHeaders(): Promise<Record<string, string>> {
    try {
        const session = await fetchAuthSession();
        const token = session.tokens?.idToken?.toString();
        if (!token) {
            console.warn("No auth token found, request may fail");
            return {};
        }
        return {
            'Authorization': `Bearer ${token}`
        };
    } catch (e) {
        console.error("Auth Session Error", e);
        return {};
    }
}

export interface OrderItem {
    id: string;
    name: string;
    price_cents: number;
    qty: number;
}

export interface Order {
    order_id: string;
    restaurant_id: string;
    status: string;
    items: OrderItem[];
    total_cents: number;
    arrival_status?: string;
}

export interface Restaurant {
    restaurant_id: string;
    name: string;
    cuisine: string;
    rating: number;
    emoji: string;
    address: string;
}

/**
 * Get list of restaurants
 */
export async function getRestaurants(): Promise<Restaurant[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/v1/restaurants`, {
        headers: { ...headers }
    });
    if (!response.ok) {
        throw new Error('Failed to fetch restaurants');
    }
    const data = await response.json();
    return data.restaurants;
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
    const response = await fetch(`${API_BASE_URL}/v1/orders`, {
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
    const response = await fetch(`${API_BASE_URL}/v1/orders/${orderId}`, {
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
    const response = await fetch(`${API_BASE_URL}/v1/orders/${orderId}/vicinity`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...headers
        },
        body: JSON.stringify({ vicinity: true, event }),
    });

    if (!response.ok) {
        throw new Error('Failed to send arrival event');
    }

    return response.json();
}

/**
 * Add tip to order
 */
export async function addTip(
    orderId: string,
    tipCents: number
): Promise<{ success: boolean }> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/v1/orders/${orderId}/tip`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...headers
        },
        body: JSON.stringify({ tip_cents: tipCents }),
    });

    if (!response.ok) {
        throw new Error('Failed to add tip');
    }

    return response.json();
}

/**
 * Get my orders (authenticated user's order history)
 */
export async function getMyOrders(): Promise<Order[]> {
    const headers = await getAuthHeaders();
    const response = await fetch(`${API_BASE_URL}/v1/orders`, {
        headers: { ...headers }
    });
    if (!response.ok) {
        throw new Error('Failed to fetch orders');
    }
    const data = await response.json();
    return data.orders;
}
