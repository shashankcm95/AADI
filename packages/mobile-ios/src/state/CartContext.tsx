import React, { createContext, useContext, useMemo, useState } from 'react';
import { OrderItem, Restaurant } from '../services/api';

export interface CartRestaurant {
    restaurant_id: string;
    name: string;
    latitude?: number;
    longitude?: number;
}

export interface CartItem extends OrderItem {
    description?: string;
}

type AddItemResult = 'added' | 'restaurant_mismatch';

interface CartContextValue {
    cartItems: CartItem[];
    cartRestaurant: CartRestaurant | null;
    cartCount: number;
    cartTotalCents: number;
    addItemToCart: (item: CartItem, restaurant: Restaurant) => AddItemResult;
    forceAddItemToCart: (item: CartItem, restaurant: Restaurant) => void;
    setItemQty: (itemId: string, qty: number) => void;
    removeItem: (itemId: string) => void;
    clearCart: () => void;
    isCartForRestaurant: (restaurantId?: string) => boolean;
}

const defaultCartContext: CartContextValue = {
    cartItems: [],
    cartRestaurant: null,
    cartCount: 0,
    cartTotalCents: 0,
    addItemToCart: () => 'added',
    forceAddItemToCart: () => undefined,
    setItemQty: () => undefined,
    removeItem: () => undefined,
    clearCart: () => undefined,
    isCartForRestaurant: () => false,
};

const CartContext = createContext<CartContextValue>(defaultCartContext);

function toCartRestaurant(restaurant: Restaurant): CartRestaurant {
    return {
        restaurant_id: restaurant.restaurant_id,
        name: restaurant.name,
        latitude: Number.isFinite(restaurant.latitude) ? Number(restaurant.latitude) : undefined,
        longitude: Number.isFinite(restaurant.longitude) ? Number(restaurant.longitude) : undefined,
    };
}

function upsertItem(items: CartItem[], item: CartItem): CartItem[] {
    const existing = items.find((entry) => entry.id === item.id);

    if (!existing) {
        const qty = Math.max(1, Number(item.qty) || 1);
        return [...items, { ...item, qty }];
    }

    return items.map((entry) => entry.id === item.id
        ? { ...entry, qty: entry.qty + 1 }
        : entry);
}

export const CartProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [cartItems, setCartItems] = useState<CartItem[]>([]);
    const [cartRestaurant, setCartRestaurant] = useState<CartRestaurant | null>(null);

    const cartCount = useMemo(() => {
        return cartItems.reduce((sum, item) => sum + Math.max(0, Number(item.qty) || 0), 0);
    }, [cartItems]);

    const cartTotalCents = useMemo(() => {
        return cartItems.reduce((sum, item) => sum + (Number(item.price_cents) || 0) * (Number(item.qty) || 0), 0);
    }, [cartItems]);

    const clearCart = () => {
        setCartItems([]);
        setCartRestaurant(null);
    };

    const addItemToCart = (item: CartItem, restaurant: Restaurant): AddItemResult => {
        const nextRestaurant = toCartRestaurant(restaurant);

        if (
            cartRestaurant
            && cartItems.length > 0
            && cartRestaurant.restaurant_id !== nextRestaurant.restaurant_id
        ) {
            return 'restaurant_mismatch';
        }

        setCartRestaurant(nextRestaurant);
        setCartItems((current) => upsertItem(current, item));
        return 'added';
    };

    const forceAddItemToCart = (item: CartItem, restaurant: Restaurant) => {
        const nextRestaurant = toCartRestaurant(restaurant);

        if (cartRestaurant && cartRestaurant.restaurant_id !== nextRestaurant.restaurant_id) {
            setCartItems([{ ...item, qty: Math.max(1, Number(item.qty) || 1) }]);
            setCartRestaurant(nextRestaurant);
            return;
        }

        setCartRestaurant(nextRestaurant);
        setCartItems((current) => upsertItem(current, item));
    };

    const setItemQty = (itemId: string, qty: number) => {
        if (!itemId) {
            return;
        }

        const normalized = Math.max(0, Math.floor(qty));

        setCartItems((current) => {
            const updated = current
                .map((item) => (item.id === itemId ? { ...item, qty: normalized } : item))
                .filter((item) => item.qty > 0);

            if (updated.length === 0) {
                setCartRestaurant(null);
            }

            return updated;
        });
    };

    const removeItem = (itemId: string) => {
        setCartItems((current) => {
            const updated = current.filter((item) => item.id !== itemId);
            if (updated.length === 0) {
                setCartRestaurant(null);
            }
            return updated;
        });
    };

    const isCartForRestaurant = (restaurantId?: string): boolean => {
        if (!restaurantId || !cartRestaurant) {
            return false;
        }
        return cartRestaurant.restaurant_id === restaurantId;
    };

    return (
        <CartContext.Provider
            value={{
                cartItems,
                cartRestaurant,
                cartCount,
                cartTotalCents,
                addItemToCart,
                forceAddItemToCart,
                setItemQty,
                removeItem,
                clearCart,
                isCartForRestaurant,
            }}
        >
            {children}
        </CartContext.Provider>
    );
};

export function useCart(): CartContextValue {
    return useContext(CartContext);
}
