import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { Text, TouchableOpacity, View } from 'react-native';
import { CartProvider, useCart } from '../CartContext';

const restaurant = {
    restaurant_id: 'rest-1',
    name: 'Test Restaurant',
} as any;

function CartHarness() {
    const cart = useCart();

    const read = () => cart.cartItems.map((item) => ({
        id: item.id,
        name: item.name,
        qty: item.qty,
        key: item.cart_item_key,
    }));

    return (
        <View>
            <TouchableOpacity
                testID="add-burger"
                onPress={() => cart.addItemToCart({
                    id: '',
                    name: 'Burger',
                    price_cents: 1000,
                    qty: 1,
                    description: 'Classic',
                } as any, restaurant)}
            />
            <TouchableOpacity
                testID="add-fries"
                onPress={() => cart.addItemToCart({
                    id: '',
                    name: 'Fries',
                    price_cents: 400,
                    qty: 1,
                    description: 'Salted',
                } as any, restaurant)}
            />
            <TouchableOpacity
                testID="add-dup-a"
                onPress={() => cart.addItemToCart({
                    id: 'dup-id',
                    name: 'Soup',
                    price_cents: 600,
                    qty: 1,
                    description: 'Tomato',
                } as any, restaurant)}
            />
            <TouchableOpacity
                testID="add-dup-b"
                onPress={() => cart.addItemToCart({
                    id: 'dup-id',
                    name: 'Salad',
                    price_cents: 600,
                    qty: 1,
                    description: 'Greek',
                } as any, restaurant)}
            />
            <TouchableOpacity
                testID="set-first-qty-3"
                onPress={() => {
                    const first = cart.cartItems[0];
                    if (first) {
                        cart.setItemQty(first.cart_item_key, 3);
                    }
                }}
            />
            <TouchableOpacity
                testID="remove-first"
                onPress={() => {
                    const first = cart.cartItems[0];
                    if (first) {
                        cart.removeItem(first.cart_item_key);
                    }
                }}
            />
            <Text testID="cart-state">{JSON.stringify(read())}</Text>
        </View>
    );
}

describe('CartContext identity handling', () => {
    it('uses fallback IDs and distinct item keys when backend IDs are empty', () => {
        const { getByTestId } = render(
            <CartProvider>
                <CartHarness />
            </CartProvider>
        );

        fireEvent.press(getByTestId('add-burger'));
        fireEvent.press(getByTestId('add-fries'));

        const state = JSON.parse(getByTestId('cart-state').props.children);
        expect(state).toHaveLength(2);
        expect(state[0].id).not.toBe('');
        expect(state[1].id).not.toBe('');
        expect(state[0].key).not.toBe(state[1].key);
    });

    it('updates and removes by cart_item_key even when item IDs are duplicated', () => {
        const { getByTestId } = render(
            <CartProvider>
                <CartHarness />
            </CartProvider>
        );

        fireEvent.press(getByTestId('add-dup-a'));
        fireEvent.press(getByTestId('add-dup-b'));
        fireEvent.press(getByTestId('set-first-qty-3'));

        let state = JSON.parse(getByTestId('cart-state').props.children);
        expect(state).toHaveLength(2);
        expect(state[0].qty).toBe(3);
        expect(state[1].qty).toBe(1);

        fireEvent.press(getByTestId('remove-first'));

        state = JSON.parse(getByTestId('cart-state').props.children);
        expect(state).toHaveLength(1);
        expect(state[0].name).toBe('Salad');
    });
});
