/** Shared TypeScript interfaces for the admin portal. */

export interface OrderItem {
    name?: string;
    id?: string;
    qty?: number;
}

export interface Order {
    order_id: string;
    customer_name?: string;
    customer_id?: string;
    items?: OrderItem[];
    resources?: OrderItem[];
    status: string;
    created_at?: number;
    updated_at?: number;
}

export interface Restaurant {
    restaurant_id: string;
    name: string;
    cuisine?: string;
    address?: string;
    street?: string;
    city?: string;
    state?: string;
    zip?: string;
    contact_email?: string;
    operating_hours?: string;
    tags?: string[];
    price_tier?: number;
    active?: boolean;
    location?: { lat: string; lon: string };
    restaurant_image_keys?: string[];
    restaurant_images?: string[];
}

export interface RestaurantFormData {
    name: string;
    cuisine?: string;
    tags?: string[];
    price_tier?: number;
    street?: string;
    city?: string;
    state?: string;
    zip?: string;
    contact_email?: string;
    operating_hours?: string;
    restaurant_image_keys?: string[];
    active?: boolean;
}

export interface MenuItem {
    id?: string;
    name: string;
    price: string | number;
    description?: string;
    category?: string;
    prep_units?: number;
}

export interface MenuUploadRow {
    [key: string]: string | number | undefined;
    Name?: string;
    name?: string;
    Price?: string | number;
    price?: string | number;
    Category?: string;
    category?: string;
    Description?: string;
    description?: string;
}
