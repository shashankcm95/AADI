/**
 * Order Screen
 * Agent Kappa: Real-time order tracking
 */
import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ActivityIndicator,
} from 'react-native';
import { getOrder, sendArrivalEvent, getRestaurant, getLeaveAdvisory, LeaveAdvisory } from '../services/api';
import { startLocationTracking, stopLocationTracking } from '../services/location';
import { theme } from '../theme';

const STATUS_LABELS: { [key: string]: { label: string; color: string; emoji: string } } = {
    'PENDING_NOT_SENT': { label: 'Order Confirmed', color: '#f59e0b', emoji: '📅' },
    'SENT_TO_DESTINATION': { label: 'Sent to kitchen', color: theme.colors.primary, emoji: '📨' },
    'WAITING_FOR_CAPACITY': { label: 'In Queue', color: '#f59e0b', emoji: '⏳' },
    'IN_PROGRESS': { label: 'Being prepared', color: '#8b5cf6', emoji: '👨‍🍳' },
    'READY': { label: 'Ready for pickup', color: '#22c55e', emoji: '✅' },
    'FULFILLING': { label: 'Being served', color: '#3b82f6', emoji: '🍽️' },
    'COMPLETED': { label: 'Enjoy your meal!', color: theme.colors.primary, emoji: '🎉' },
    'EXPIRED': { label: 'Order Expired', color: '#ef4444', emoji: '⚠️' },
    'CANCELED': { label: 'Order Canceled', color: '#ef4444', emoji: '❌' },
    'DECLINED': { label: 'Restaurant Declined', color: '#ef4444', emoji: '⛔' },
};

const ARRIVAL_LABELS: { [key: string]: string } = {
    '5_MIN_OUT': '📍 5 min away',
    'PARKING': '🅿️ Parking',
    'AT_DOOR': '🚪 At door',
    'EXIT_VICINITY': '👋 Left vicinity',
    'UNKNOWN': '📍 Tracking...',
};

interface Props {
    route: any;
}

export default function OrderScreen({ route }: Props) {
    const { orderId } = route.params;
    const [order, setOrder] = useState<any>(null);
    const [leaveAdvisory, setLeaveAdvisory] = useState<LeaveAdvisory | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let mounted = true;

        const init = async () => {
            await fetchOrder();
        };
        init();

        const interval = setInterval(() => {
            if (mounted) fetchOrder();
        }, 5000); // Poll every 5s

        return () => {
            mounted = false;
            clearInterval(interval);
            stopLocationTracking(); // Privacy: Stop tracking on unmount
        };
    }, []);

    const fetchOrder = async () => {
        try {
            const data = await getOrder(orderId);
            setOrder(data);
            setLoading(false);

            if (['PENDING_NOT_SENT', 'WAITING_FOR_CAPACITY'].includes(data.status)) {
                try {
                    const advisory = await getLeaveAdvisory(orderId);
                    setLeaveAdvisory(advisory);
                } catch (advisoryError) {
                    console.warn('[OrderScreen] Failed to fetch leave advisory:', advisoryError);
                    setLeaveAdvisory(null);
                }
            } else {
                setLeaveAdvisory(null);
            }

            // Manage Location Tracking based on status
            const activeStatuses = ['SENT_TO_DESTINATION', 'IN_PROGRESS', 'READY', 'FULFILLING'];
            const isCompleted = ['COMPLETED', 'CANCELED', 'DECLINED', 'EXPIRED'].includes(data.status);

            if (activeStatuses.includes(data.status)) {
                try {
                    const restaurant = await getRestaurant(data.restaurant_id);
                    const hasCoordinates = Number.isFinite(restaurant.latitude) && Number.isFinite(restaurant.longitude);
                    if (hasCoordinates) {
                        startLocationTracking(
                            {
                                latitude: Number(restaurant.latitude),
                                longitude: Number(restaurant.longitude),
                                restaurantId: data.restaurant_id
                            },
                            orderId,
                            (event, _orderId, meta) => {
                                console.log(`[OrderScreen] Event: ${event} Meta:`, meta);
                                if (['AT_DOOR', 'PARKING', '5_MIN_OUT'].includes(event)) {
                                    sendArrival(event);
                                }
                            }
                        );
                    } else {
                        stopLocationTracking();
                        console.warn('[OrderScreen] Restaurant coordinates unavailable; background arrival tracking skipped.');
                    }
                } catch (err) {
                    stopLocationTracking();
                    console.warn('[OrderScreen] Could not fetch restaurant coordinates:', err);
                }
            } else if (isCompleted) {
                stopLocationTracking();
            }
        } catch (error) {
            console.error('Failed to fetch order:', error);
        }
    };

    const sendArrival = async (event: string) => {
        try {
            await sendArrivalEvent(orderId, event);
            fetchOrder();
        } catch (error) {
            console.error('Failed to send arrival event:', error);
        }
    };

    if (loading) {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" color={theme.colors.primary} />
            </View>
        );
    }

    const statusInfo = STATUS_LABELS[order?.status] || STATUS_LABELS['PENDING_NOT_SENT'];
    const arrivalLabel = order?.arrival_status ? ARRIVAL_LABELS[order.arrival_status] : null;
    const estimatedWaitMinutes = leaveAdvisory
        ? Math.ceil(Math.max(0, Number(leaveAdvisory.estimated_wait_seconds || 0)) / 60)
        : 0;

    return (
        <View style={styles.container}>
            <View style={styles.card}>
                <Text style={styles.orderId}>Order #{orderId.slice(-6)}</Text>

                <View style={[styles.statusBadge, { backgroundColor: statusInfo.color + '20' }]}>
                    <Text style={styles.statusEmoji}>{statusInfo.emoji}</Text>
                    <Text style={[styles.statusLabel, { color: statusInfo.color }]}>{statusInfo.label}</Text>
                </View>

                {arrivalLabel && (
                    <Text style={styles.arrivalStatus}>{arrivalLabel}</Text>
                )}

                {leaveAdvisory && ['PENDING_NOT_SENT', 'WAITING_FOR_CAPACITY'].includes(order?.status) && (
                    <View style={styles.advisoryCard}>
                        <Text style={styles.advisoryTitle}>Leave-time estimate</Text>
                        <Text style={styles.advisoryBody}>
                            {leaveAdvisory.recommended_action === 'LEAVE_NOW'
                                ? 'Leave now. Capacity looks available right now.'
                                : `Wait about ${estimatedWaitMinutes} min before heading out.`}
                        </Text>
                        <Text style={styles.advisoryNote}>Estimate only. Capacity is reserved on arrival dispatch.</Text>
                    </View>
                )}

                {/* Order Items */}
                <View style={styles.itemsContainer}>
                    {order?.items?.map((item: any, index: number) => (
                        <Text key={index} style={styles.itemLine}>
                            {item.name} <Text style={{ fontWeight: '700', color: theme.colors.accent }}>x{item.qty}</Text>
                        </Text>
                    ))}
                </View>

                <Text style={styles.total}>
                    Total: ${((order?.total_cents || 0) / 100).toFixed(2)}
                </Text>
            </View>

            {['PENDING_NOT_SENT', 'WAITING_FOR_CAPACITY'].includes(order?.status) && (
                <View style={styles.simControls}>
                    <Text style={styles.simTitle}>📍 Arrival Update</Text>
                    <View style={styles.simButtons}>
                        <TouchableOpacity
                            style={styles.simButton}
                            onPress={() => sendArrival('5_MIN_OUT')}
                        >
                            <Text style={styles.simButtonText}>5 Min Out</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                            style={styles.simButton}
                            onPress={() => sendArrival('AT_DOOR')}
                        >
                            <Text style={styles.simButtonText}>I'm Here</Text>
                        </TouchableOpacity>
                    </View>
                </View>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: theme.colors.background, padding: 20 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: theme.colors.background },
    card: {
        ...theme.layout.card,
        backgroundColor: '#fff',
    },
    orderId: { color: theme.colors.textMuted, fontSize: 14, marginBottom: 16 },
    statusBadge: {
        flexDirection: 'row',
        alignItems: 'center',
        padding: 16,
        borderRadius: 12,
        marginBottom: 16,
    },
    statusEmoji: { fontSize: 24, marginRight: 12 },
    statusLabel: { fontSize: 18, fontWeight: '700' },
    arrivalStatus: { color: theme.colors.primary, fontSize: 16, marginBottom: 16, textAlign: 'center', fontWeight: 'bold' },
    advisoryCard: {
        borderWidth: 1,
        borderColor: '#fde68a',
        backgroundColor: '#fffbeb',
        borderRadius: 12,
        padding: 12,
        marginBottom: 16,
    },
    advisoryTitle: {
        color: '#92400e',
        fontSize: 14,
        fontWeight: '700',
        marginBottom: 4,
    },
    advisoryBody: {
        color: '#78350f',
        fontSize: 14,
    },
    advisoryNote: {
        color: '#a16207',
        fontSize: 12,
        marginTop: 6,
    },
    itemsContainer: { borderTopWidth: 1, borderTopColor: '#f1f5f9', paddingTop: 16 },
    itemLine: { color: theme.colors.text, fontSize: 16, marginBottom: 8 },
    total: { color: theme.colors.primary, fontSize: 18, fontWeight: '700', marginTop: 16, textAlign: 'right' },
    simControls: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
        borderWidth: 1,
        borderColor: '#e2e8f0',
        borderStyle: 'dashed',
    },
    simTitle: { color: theme.colors.textMuted, fontSize: 14, marginBottom: 12, textAlign: 'center' },
    simButtons: { flexDirection: 'row', gap: 12 },
    simButton: {
        flex: 1,
        backgroundColor: '#f1f5f9',
        padding: 12,
        borderRadius: 8,
        alignItems: 'center',
    },
    simButtonText: { color: theme.colors.text, fontWeight: '600' },
});
