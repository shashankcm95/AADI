import {
    ORDERS_API_URL as DEFAULT_ORDERS_API_URL,
    RESTAURANTS_API_URL as DEFAULT_RESTAURANTS_API_URL,
} from './aws-exports';

function normalizeBaseUrl(url: string): string {
    return url.replace(/\/+$/, '');
}

export const RESTAURANTS_API_BASE_URL = normalizeBaseUrl(
    process.env.EXPO_PUBLIC_RESTAURANTS_API_URL || DEFAULT_RESTAURANTS_API_URL
);

export const ORDERS_API_BASE_URL = normalizeBaseUrl(
    process.env.EXPO_PUBLIC_ORDERS_API_URL || DEFAULT_ORDERS_API_URL
);
