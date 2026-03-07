/**
 * Order Screen
 * Agent Kappa: Real-time order tracking
 */
import React, { useRef, useState, useEffect } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ActivityIndicator,
    AppState,
    AppStateStatus,
    ScrollView,
} from 'react-native';
import { getOrder, sendArrivalEvent, getRestaurant, getLeaveAdvisory, LeaveAdvisory, sendLocationSample } from '../services/api';
import {
    getPermissionLevel,
    requestPermissions,
    startLocationTracking,
    stopLocationTracking,
    triggerImmediateVicinityCheck,
    TrackingPermissionLevel,
} from '../services/location';
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

const TRACKABLE_STATUSES = ['PENDING_NOT_SENT', 'WAITING_FOR_CAPACITY', 'SENT_TO_DESTINATION', 'IN_PROGRESS', 'READY'];
const TERMINAL_STATUSES = ['COMPLETED', 'CANCELED', 'DECLINED', 'EXPIRED'];

function hasReachedRestaurant(order: any): boolean {
    const status = String(order?.status || '').toUpperCase();
    const arrivalStatus = String(order?.arrival_status || '').toUpperCase();

    return arrivalStatus === 'AT_DOOR' || status === 'FULFILLING' || TERMINAL_STATUSES.includes(status);
}

interface Props {
    navigation: any;
    route: any;
}

export default function OrderScreen({ navigation, route }: Props) {
    const orderId = String(route?.params?.orderId || '').trim();
    const [order, setOrder] = useState<any>(null);
    const [leaveAdvisory, setLeaveAdvisory] = useState<LeaveAdvisory | null>(null);
    const [loading, setLoading] = useState(true);
    const [trackingPermissionLevel, setTrackingPermissionLevel] = useState<TrackingPermissionLevel>('none');
    const [trackingPermissionEvaluated, setTrackingPermissionEvaluated] = useState(false);
    const locationPermissionResolvedRef = useRef(false);
    const locationPermissionGrantedRef = useRef(false);
    // BL-056 / BL-057: guard tracking setup so getRestaurant, startLocationTracking,
    // and triggerImmediateVicinityCheck run only once per order, not on every 5s poll.
    const trackingSetupDoneRef = useRef(false);
    const appStateRef = useRef<AppStateStatus>(AppState.currentState);

    useEffect(() => {
        if (!orderId) {
            setLoading(false);
            return;
        }

        let mounted = true;
        locationPermissionResolvedRef.current = false;
        locationPermissionGrantedRef.current = false;
        trackingSetupDoneRef.current = false;
        setTrackingPermissionEvaluated(false);

        const init = async () => {
            await fetchOrder();
        };
        init();

        const interval = setInterval(() => {
            if (mounted) fetchOrder();
        }, 5000); // Poll every 5s

        const appStateSubscription = AppState.addEventListener('change', (nextState) => {
            const wasBackground = appStateRef.current === 'background' || appStateRef.current === 'inactive';
            appStateRef.current = nextState;

            if (!mounted || !wasBackground || nextState !== 'active') {
                return;
            }

            void (async () => {
                await fetchOrder();
                const checkMode = await triggerImmediateVicinityCheck();
                if (checkMode === 'estimate') {
                    console.log('[OrderScreen] Resume check used estimate (last-known location).');
                }
            })();
        });

        return () => {
            mounted = false;
            clearInterval(interval);
            appStateSubscription.remove();
        };
    }, [orderId]);

    const fetchOrder = async () => {
        if (!orderId) {
            setLoading(false);
            return;
        }

        try {
            const data = await getOrder(orderId);
            setOrder(data);

            if (['PENDING_NOT_SENT', 'WAITING_FOR_CAPACITY', 'SENT_TO_DESTINATION'].includes(data.status)) {
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

            if (hasReachedRestaurant(data)) {
                await stopLocationTracking();
                return;
            }

            // Manage location tracking based on order lifecycle.
            const status = String(data.status || '').toUpperCase();

            if (TRACKABLE_STATUSES.includes(status)) {
                if (!locationPermissionResolvedRef.current) {
                    try {
                        locationPermissionGrantedRef.current = await requestPermissions({ requestBackground: false });
                        const level = await getPermissionLevel();
                        setTrackingPermissionLevel(level);
                        setTrackingPermissionEvaluated(true);
                    } catch (permissionError) {
                        locationPermissionGrantedRef.current = false;
                        setTrackingPermissionLevel('none');
                        setTrackingPermissionEvaluated(true);
                        console.warn('[OrderScreen] Failed to request location permission:', permissionError);
                    }
                    locationPermissionResolvedRef.current = true;
                }

                if (!locationPermissionGrantedRef.current) {
                    await stopLocationTracking();
                    return;
                }

                // BL-056 / BL-057: Only set up tracking once per order. Running getRestaurant
                // (which fetches all restaurants with no cache) and triggerImmediateVicinityCheck
                // (which requests a fresh GPS fix) on every 5s poll wastes network and battery.
                if (!trackingSetupDoneRef.current) {
                    try {
                        const restaurant = await getRestaurant(data.restaurant_id);
                        const hasCoordinates = Number.isFinite(restaurant.latitude) && Number.isFinite(restaurant.longitude);
                        if (hasCoordinates) {
                            try {
                                await startLocationTracking(
                                    {
                                        latitude: Number(restaurant.latitude),
                                        longitude: Number(restaurant.longitude),
                                        restaurantId: data.restaurant_id
                                    },
                                    orderId,
                                    async (event) => {
                                        if (['AT_DOOR', 'PARKING', '5_MIN_OUT'].includes(event)) {
                                            await sendArrival(event);
                                        }
                                    },
                                    async (sampleOrderId, sample) => {
                                        try {
                                            await sendLocationSample(sampleOrderId, sample);
                                        } catch (sampleError) {
                                            console.warn('[OrderScreen] Failed to send location sample:', sampleError);
                                        }
                                    },
                                );
                                await triggerImmediateVicinityCheck();
                                trackingSetupDoneRef.current = true;
                            } catch (trackingError) {
                                await stopLocationTracking();
                                console.warn('[OrderScreen] Could not start location tracking:', trackingError);
                            }
                        } else {
                            await stopLocationTracking();
                            trackingSetupDoneRef.current = true;
                            console.warn('[OrderScreen] Restaurant coordinates unavailable; background arrival tracking skipped.');
                        }
                    } catch (err) {
                        await stopLocationTracking();
                        console.warn('[OrderScreen] Could not fetch restaurant details:', err);
                    }
                }
            }
        } catch (error) {
            console.error('Failed to fetch order:', error);
        } finally {
            setLoading(false);
        }
    };

    const sendArrival = async (event: string) => {
        const normalizedEvent = String(event || '').toUpperCase();
        try {
            if (normalizedEvent === 'AT_DOOR') {
                await stopLocationTracking();
            }
            await sendArrivalEvent(orderId, normalizedEvent);
            await fetchOrder();
        } catch (error) {
            console.error('Failed to send arrival event:', error);
        }
    };

    if (!orderId) {
        return (
            <View style={styles.center}>
                <Text style={styles.emptyStateTitle}>Order not found</Text>
                <Text style={styles.emptyStateBody}>We couldn't load this order. Try opening it again from your order history.</Text>
                <TouchableOpacity style={styles.emptyStateButton} onPress={() => navigation.navigate('Orders')}>
                    <Text style={styles.emptyStateButtonText}>Back to Orders</Text>
                </TouchableOpacity>
            </View>
        );
    }

    if (loading) {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" color={theme.colors.primary} />
            </View>
        );
    }

    const statusInfo = STATUS_LABELS[order?.status] || STATUS_LABELS['PENDING_NOT_SENT'];
    const arrivalLabel = order?.arrival_status ? ARRIVAL_LABELS[order.arrival_status] : null;
    const locationNotice = !trackingPermissionEvaluated
        ? null
        : trackingPermissionLevel === 'none'
        ? 'Location not allowed. Allow Once or Allow While Using to enable vicinity estimates; otherwise use "I\'m Here" manual trigger.'
        : trackingPermissionLevel === 'foreground'
            ? 'Session mode: Allow Once/While Using can keep tracking in background while iOS shows the blue location indicator. If updates pause, we fall back to estimates until you reopen the app. Always Location is most reliable.'
            : null;
    const estimatedWaitMinutes = leaveAdvisory
        ? Math.ceil(Math.max(0, Number(leaveAdvisory.estimated_wait_seconds || 0)) / 60)
        : 0;

    const isTerminal = TERMINAL_STATUSES.includes(order?.status);
    const isCanceled = ['CANCELED', 'DECLINED', 'EXPIRED'].includes(order?.status);
    const showLeaveAdvisory = leaveAdvisory && ['PENDING_NOT_SENT', 'WAITING_FOR_CAPACITY', 'SENT_TO_DESTINATION'].includes(order?.status);
    const isLeaveNow = leaveAdvisory?.recommended_action === 'LEAVE_NOW';
    const isUrgent = !isLeaveNow && estimatedWaitMinutes > 0 && estimatedWaitMinutes <= 5;

    // Step indicator logic
    const STEPS = ['Confirmed', 'Preparing', 'Ready', 'Picked Up'] as const;
    const statusToStep: Record<string, number> = {
        PENDING_NOT_SENT: 0, SENT_TO_DESTINATION: 0, WAITING_FOR_CAPACITY: 0,
        IN_PROGRESS: 1,
        READY: 2,
        FULFILLING: 3, COMPLETED: 3,
    };
    const currentStep = isCanceled ? -1 : (statusToStep[order?.status] ?? 0);

    // Elapsed time
    const createdAt = order?.created_at;
    let elapsedText = '';
    if (createdAt) {
        const epoch = Number(createdAt) > 1e12 ? Number(createdAt) : Number(createdAt) * 1000;
        const elapsedMs = Date.now() - epoch;
        const elapsedMin = Math.max(0, Math.floor(elapsedMs / 60000));
        elapsedText = elapsedMin < 1 ? 'Just now' : `${elapsedMin} min ago`;
    }

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
            <View style={styles.card}>
                <Text style={styles.orderId}>Order #{orderId.slice(-6)}</Text>

                {/* Hero Leave Advisory */}
                {showLeaveAdvisory && (
                    <View style={[styles.heroAdvisory, isLeaveNow && styles.heroAdvisoryUrgent, isUrgent && styles.heroAdvisoryWarn]}>
                        {isLeaveNow ? (
                            <>
                                <Text style={styles.heroAdvisoryLabel}>Time to go!</Text>
                                <Text style={styles.heroAdvisoryNumber}>NOW</Text>
                                <Text style={styles.heroAdvisorySubtext}>Capacity is available — head out now</Text>
                            </>
                        ) : estimatedWaitMinutes > 0 ? (
                            <>
                                <Text style={[styles.heroAdvisoryLabel, isUrgent && styles.heroAdvisoryLabelUrgent]}>Leave in</Text>
                                <Text style={[styles.heroAdvisoryNumber, isUrgent && styles.heroAdvisoryNumberUrgent]}>
                                    {estimatedWaitMinutes}
                                </Text>
                                <Text style={[styles.heroAdvisoryUnit, isUrgent && styles.heroAdvisoryLabelUrgent]}>minutes</Text>
                                <Text style={styles.heroAdvisorySubtext}>We'll have your order ready when you arrive</Text>
                            </>
                        ) : (
                            <>
                                <Text style={styles.heroAdvisoryLabel}>Estimating</Text>
                                <Text style={styles.heroAdvisorySubtext}>Calculating the best time for you to leave</Text>
                            </>
                        )}
                    </View>
                )}

                {/* Step Indicator */}
                <View style={styles.stepContainer}>
                    <Text style={styles.stepMeta}>
                        {isCanceled ? statusInfo.label : `Step ${currentStep + 1} of 4`}
                        {elapsedText ? ` · ${elapsedText}` : ''}
                    </Text>
                    {STEPS.map((stepLabel, idx) => {
                        const isCompleted = !isCanceled && idx < currentStep;
                        const isActive = !isCanceled && idx === currentStep;
                        const isFuture = isCanceled || idx > currentStep;
                        const isLast = idx === STEPS.length - 1;

                        return (
                            <View key={stepLabel} style={styles.stepRow}>
                                <View style={styles.stepIndicatorCol}>
                                    <View style={[
                                        styles.stepDot,
                                        isCompleted && styles.stepDotCompleted,
                                        isActive && styles.stepDotActive,
                                        isCanceled && styles.stepDotCanceled,
                                        isFuture && !isCanceled && styles.stepDotFuture,
                                    ]}>
                                        <Text style={styles.stepDotText}>
                                            {isCanceled ? '✕' : isCompleted ? '✓' : isActive ? (idx + 1).toString() : (idx + 1).toString()}
                                        </Text>
                                    </View>
                                    {!isLast && (
                                        <View style={[
                                            styles.stepLine,
                                            isCompleted && styles.stepLineCompleted,
                                            (isFuture || isCanceled) && styles.stepLineFuture,
                                        ]} />
                                    )}
                                </View>
                                <View style={styles.stepLabelCol}>
                                    <Text style={[
                                        styles.stepLabel,
                                        isActive && styles.stepLabelActive,
                                        isCompleted && styles.stepLabelCompleted,
                                        (isFuture || isCanceled) && styles.stepLabelFuture,
                                    ]}>
                                        {stepLabel}
                                    </Text>
                                </View>
                            </View>
                        );
                    })}
                </View>

                {arrivalLabel && (
                    <Text style={styles.arrivalStatus}>{arrivalLabel}</Text>
                )}

                {locationNotice && (
                    <Text style={styles.locationNotice}>{locationNotice}</Text>
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
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: theme.colors.background },
    scrollContent: { padding: 20 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: theme.colors.background },
    card: {
        ...theme.layout.card,
        backgroundColor: '#fff',
    },
    orderId: { color: theme.colors.textMuted, fontSize: 14, marginBottom: 16 },
    // Hero leave advisory
    heroAdvisory: {
        backgroundColor: theme.colors.primary + '10',
        borderRadius: 16,
        padding: 24,
        marginBottom: 20,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: theme.colors.primary + '30',
    },
    heroAdvisoryUrgent: {
        backgroundColor: '#ef4444' + '15',
        borderColor: '#ef4444' + '40',
    },
    heroAdvisoryWarn: {
        backgroundColor: '#f59e0b' + '15',
        borderColor: '#f59e0b' + '40',
    },
    heroAdvisoryLabel: {
        fontSize: 14,
        fontWeight: '600',
        color: theme.colors.primary,
        textTransform: 'uppercase',
        letterSpacing: 1,
    },
    heroAdvisoryLabelUrgent: {
        color: '#f59e0b',
    },
    heroAdvisoryNumber: {
        fontSize: 56,
        fontWeight: '800',
        color: theme.colors.primary,
        lineHeight: 64,
        marginVertical: 4,
    },
    heroAdvisoryNumberUrgent: {
        color: '#f59e0b',
    },
    heroAdvisoryUnit: {
        fontSize: 18,
        fontWeight: '600',
        color: theme.colors.primary,
        marginBottom: 8,
    },
    heroAdvisorySubtext: {
        fontSize: 13,
        color: theme.colors.textSecondary,
        textAlign: 'center',
    },
    // Step indicator
    stepContainer: {
        marginBottom: 20,
        paddingLeft: 4,
    },
    stepMeta: {
        fontSize: 13,
        color: theme.colors.textSecondary,
        fontWeight: '600',
        marginBottom: 16,
    },
    stepRow: {
        flexDirection: 'row',
        alignItems: 'flex-start',
    },
    stepIndicatorCol: {
        alignItems: 'center',
        width: 32,
        marginRight: 12,
    },
    stepDot: {
        width: 28,
        height: 28,
        borderRadius: 14,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: theme.colors.border,
    },
    stepDotCompleted: {
        backgroundColor: theme.colors.primary,
    },
    stepDotActive: {
        backgroundColor: theme.colors.teal3,
        borderWidth: 2,
        borderColor: theme.colors.primary,
    },
    stepDotCanceled: {
        backgroundColor: '#ef4444',
    },
    stepDotFuture: {
        backgroundColor: theme.colors.overlayTopTint,
        borderWidth: 1,
        borderColor: theme.colors.border,
    },
    stepDotText: {
        color: '#fff',
        fontSize: 12,
        fontWeight: '700',
    },
    stepLine: {
        width: 2,
        height: 24,
        backgroundColor: theme.colors.border,
    },
    stepLineCompleted: {
        backgroundColor: theme.colors.primary,
    },
    stepLineFuture: {
        backgroundColor: theme.colors.border,
    },
    stepLabelCol: {
        flex: 1,
        paddingTop: 4,
        minHeight: 52,
    },
    stepLabel: {
        fontSize: 15,
        fontWeight: '600',
        color: theme.colors.text,
    },
    stepLabelActive: {
        color: theme.colors.primary,
        fontWeight: '700',
    },
    stepLabelCompleted: {
        color: theme.colors.textSecondary,
    },
    stepLabelFuture: {
        color: theme.colors.textMuted,
        fontWeight: '400',
    },
    arrivalStatus: { color: theme.colors.primary, fontSize: 16, marginBottom: 16, textAlign: 'center', fontWeight: 'bold' },
    locationNotice: {
        marginBottom: 14,
        paddingHorizontal: 12,
        paddingVertical: 10,
        borderRadius: 10,
        backgroundColor: '#fef3c7',
        color: '#92400e',
        fontSize: 13,
        lineHeight: 18,
        fontWeight: '600',
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
        marginTop: 16,
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
    emptyStateTitle: {
        ...theme.typography.h3,
        color: theme.colors.text,
        textAlign: 'center',
    },
    emptyStateBody: {
        ...theme.typography.bodySm,
        color: theme.colors.textSecondary,
        textAlign: 'center',
        marginTop: theme.spacing.sm,
        marginBottom: theme.spacing.lg,
        paddingHorizontal: theme.spacing.lg,
    },
    emptyStateButton: {
        borderWidth: 1,
        borderColor: theme.colors.border,
        borderRadius: theme.radii.button,
        backgroundColor: theme.colors.surface,
        paddingHorizontal: theme.spacing.lg,
        paddingVertical: theme.spacing.md,
    },
    emptyStateButtonText: {
        ...theme.typography.body,
        color: theme.colors.text,
        fontWeight: '700',
    },
});
