import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { Animated, StyleSheet, Text } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { theme } from '../../theme';

interface ToastContextValue {
    showToast: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue>({ showToast: () => undefined });

export function useToast(): ToastContextValue {
    return useContext(ToastContext);
}

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [message, setMessage] = useState('');
    const [visible, setVisible] = useState(false);
    const translateY = useRef(new Animated.Value(80)).current;
    const opacity = useRef(new Animated.Value(0)).current;
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const insets = useSafeAreaInsets();

    const showToast = useCallback((msg: string) => {
        if (timerRef.current) {
            clearTimeout(timerRef.current);
        }
        setMessage(msg);
        setVisible(true);
        translateY.setValue(80);
        opacity.setValue(0);

        Animated.parallel([
            Animated.spring(translateY, { toValue: 0, useNativeDriver: true, speed: 14, bounciness: 6 }),
            Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
        ]).start();

        timerRef.current = setTimeout(() => {
            Animated.parallel([
                Animated.timing(translateY, { toValue: 80, duration: 250, useNativeDriver: true }),
                Animated.timing(opacity, { toValue: 0, duration: 250, useNativeDriver: true }),
            ]).start(() => setVisible(false));
        }, 1500);
    }, [translateY, opacity]);

    useEffect(() => {
        return () => {
            if (timerRef.current) clearTimeout(timerRef.current);
        };
    }, []);

    return (
        <ToastContext.Provider value={{ showToast }}>
            {children}
            {visible && (
                <Animated.View
                    style={[
                        styles.toast,
                        { bottom: Math.max(insets.bottom, 16) + 60, transform: [{ translateY }], opacity },
                    ]}
                    pointerEvents="none"
                >
                    <Text style={styles.text}>{message}</Text>
                </Animated.View>
            )}
        </ToastContext.Provider>
    );
};

const styles = StyleSheet.create({
    toast: {
        position: 'absolute',
        left: 24,
        right: 24,
        backgroundColor: theme.colors.text,
        borderRadius: theme.radii.input,
        paddingHorizontal: theme.spacing.lg,
        paddingVertical: theme.spacing.md,
        alignItems: 'center',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.15,
        shadowRadius: 8,
        elevation: 6,
    },
    text: {
        ...theme.typography.body,
        color: theme.colors.white,
        fontWeight: '600',
    },
});
