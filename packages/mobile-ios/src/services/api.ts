import { fetchAuthSession } from 'aws-amplify/auth';
import {
    ORDERS_API_BASE_URL,
    RESTAURANTS_API_BASE_URL,
} from '../config';

/**
 * API Service
 * Agent Kappa: Backend communication
 */

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
    latitude?: number;
    longitude?: number;
    price_tier?: number; // 1-4
    tags?: string[];
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
