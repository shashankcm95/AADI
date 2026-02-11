/**
 * Departure Screen
 * Agent Theta: "When to Leave" notification UI
 */
import React, { useState, useEffect } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    ActivityIndicator,
} from 'react-native';
import { theme } from '../theme';

interface DepartureRecommendation {
    leave_at: string;
    arrive_at: string;
    eta_minutes: number;
    wait_time_minutes: number;
    confidence: number;
    reason: string;
    is_urgent: boolean;
}

interface Props {
    route: any;
    navigation: any;
}

// Mock API call - in production this would call the backend
async function getDepartureRecommendation(
    orderId: string,
    userLat: number,
    userLong: number
): Promise<DepartureRecommendation> {
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 500));

    const now = new Date();
    const leaveAt = new Date(now.getTime() + 15 * 60000); // 15 min from now
    const arriveAt = new Date(now.getTime() + 35 * 60000); // 35 min from now

    return {
        leave_at: leaveAt.toISOString(),
        arrive_at: arriveAt.toISOString(),
        eta_minutes: 20,
        wait_time_minutes: 0,
        confidence: 0.9,
        reason: "Perfect timing! Leave at " + formatTime(leaveAt) + " for a seamless experience.",
        is_urgent: false,
    };
}

function formatTime(date: Date): string {
    return date.toLocaleTimeString('en-US', {
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
}

function formatCountdown(targetDate: Date): { minutes: number; seconds: number } {
    const now = new Date();
    const diff = targetDate.getTime() - now.getTime();

    if (diff <= 0) return { minutes: 0, seconds: 0 };

    const minutes = Math.floor(diff / 60000);
    const seconds = Math.floor((diff % 60000) / 1000);

    return { minutes, seconds };
}

export default function DepartureScreen({ route, navigation }: Props) {
    const { orderId, restaurantName } = route.params;
    const [recommendation, setRecommendation] = useState<DepartureRecommendation | null>(null);
    const [loading, setLoading] = useState(true);
    const [countdown, setCountdown] = useState({ minutes: 0, seconds: 0 });

    useEffect(() => {
        loadRecommendation();
    }, []);

    useEffect(() => {
        if (!recommendation) return;

        const leaveAt = new Date(recommendation.leave_at);
        const timer = setInterval(() => {
            setCountdown(formatCountdown(leaveAt));
        }, 1000);

        return () => clearInterval(timer);
    }, [recommendation]);

    const loadRecommendation = async () => {
        try {
            // Get user's current location (simplified - would use real GPS)
            const userLat = 30.285;  // Mock: slightly north of restaurant
            const userLong = -97.743;

            const rec = await getDepartureRecommendation(orderId, userLat, userLong);
            setRecommendation(rec);
            setLoading(false);
        } catch (error) {
            console.error('Failed to get departure recommendation:', error);
            setLoading(false);
        }
    };

    const handleLeaveNow = () => {
        // This would start GPS tracking and navigate to order screen
        navigation.navigate('Order', { orderId });
    };

    if (loading) {
        return (
            <View style={styles.center}>
                <ActivityIndicator size="large" color={theme.colors.primary} />
                <Text style={styles.loadingText}>Calculating perfect timing...</Text>
            </View>
        );
    }

    if (!recommendation) {
        return (
            <View style={styles.center}>
                <Text style={styles.errorText}>Unable to calculate departure time</Text>
            </View>
        );
    }

    const isTimeToLeave = countdown.minutes === 0 && countdown.seconds === 0;

    return (
        <View style={styles.container}>
            {/* Header */}
            <View style={styles.header}>
                <Text style={styles.emoji}>{recommendation.is_urgent ? '🚗' : '⏱️'}</Text>
                <Text style={styles.title}>
                    {recommendation.is_urgent ? 'Time to leave!' : 'Your Perfect Departure'}
                </Text>
                <Text style={styles.restaurant}>{restaurantName || 'Arrive Bistro'}</Text>
            </View>

            {/* Countdown or Leave Now */}
            <View style={styles.countdownCard}>
                {!isTimeToLeave && !recommendation.is_urgent ? (
                    <>
                        <Text style={styles.countdownLabel}>Leave in</Text>
                        <View style={styles.countdownRow}>
                            <View style={styles.countdownBox}>
                                <Text style={styles.countdownNumber}>{countdown.minutes}</Text>
                                <Text style={styles.countdownUnit}>min</Text>
                            </View>
                            <Text style={styles.countdownColon}>:</Text>
                            <View style={styles.countdownBox}>
                                <Text style={styles.countdownNumber}>
                                    {countdown.seconds.toString().padStart(2, '0')}
                                </Text>
                                <Text style={styles.countdownUnit}>sec</Text>
                            </View>
                        </View>
                        <Text style={styles.arrivalText}>
                            Arrive by {formatTime(new Date(recommendation.arrive_at))}
                        </Text>
                    </>
                ) : (
                    <>
                        <Text style={styles.leaveNowEmoji}>🚀</Text>
                        <Text style={styles.leaveNowText}>Leave Now!</Text>
                        <Text style={styles.arrivalText}>
                            Your food will be ready when you arrive
                        </Text>
                    </>
                )}
            </View>

            {/* Details */}
            <View style={styles.details}>
                <View style={styles.detailRow}>
                    <Text style={styles.detailIcon}>🛣️</Text>
                    <Text style={styles.detailLabel}>Travel time</Text>
                    <Text style={styles.detailValue}>{recommendation.eta_minutes} min</Text>
                </View>

                {recommendation.wait_time_minutes > 0 && (
                    <View style={styles.detailRow}>
                        <Text style={styles.detailIcon}>⏳</Text>
                        <Text style={styles.detailLabel}>Expected wait</Text>
                        <Text style={styles.detailValue}>{recommendation.wait_time_minutes} min</Text>
                    </View>
                )}

                <View style={styles.detailRow}>
                    <Text style={styles.detailIcon}>📊</Text>
                    <Text style={styles.detailLabel}>Confidence</Text>
                    <Text style={styles.detailValue}>
                        {Math.round(recommendation.confidence * 100)}%
                    </Text>
                </View>
            </View>

            {/* Reason */}
            <View style={styles.reasonCard}>
                <Text style={styles.reasonText}>{recommendation.reason}</Text>
            </View>

            {/* Action Button */}
            <TouchableOpacity
                style={[
                    styles.actionButton,
                    (isTimeToLeave || recommendation.is_urgent) && styles.actionButtonUrgent
                ]}
                onPress={handleLeaveNow}
            >
                <Text style={styles.actionButtonText}>
                    {isTimeToLeave || recommendation.is_urgent ? "I'm Leaving Now" : "Start Navigation"}
                </Text>
            </TouchableOpacity>

            {/* Notify Me Later */}
            {!isTimeToLeave && !recommendation.is_urgent && (
                <TouchableOpacity style={styles.notifyButton}>
                    <Text style={styles.notifyButtonText}>🔔 Notify me when it's time</Text>
                </TouchableOpacity>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: theme.colors.background, padding: 20 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: theme.colors.background },
    loadingText: { color: theme.colors.textMuted, marginTop: 16, fontSize: 16 },
    errorText: { color: theme.colors.error, fontSize: 16 },

    header: { alignItems: 'center', marginBottom: 24 },
    emoji: { fontSize: 48, marginBottom: 12 },
    title: { color: theme.colors.primary, fontSize: 24, fontWeight: '700', marginBottom: 8, fontFamily: theme.typography.header.fontFamily },
    restaurant: { color: theme.colors.accent, fontSize: 16 },

    countdownCard: {
        backgroundColor: '#fff',
        borderRadius: 20,
        padding: 32,
        alignItems: 'center',
        marginBottom: 24,
        ...theme.layout.card,
    },
    countdownLabel: { color: theme.colors.textMuted, fontSize: 16, marginBottom: 12 },
    countdownRow: { flexDirection: 'row', alignItems: 'center' },
    countdownBox: { alignItems: 'center', minWidth: 80 },
    countdownNumber: { color: theme.colors.text, fontSize: 56, fontWeight: '700' },
    countdownUnit: { color: theme.colors.textMuted, fontSize: 14, marginTop: 4 },
    countdownColon: { color: theme.colors.accent, fontSize: 48, fontWeight: '700', marginHorizontal: 8 },
    arrivalText: { color: theme.colors.textMuted, fontSize: 14, marginTop: 16 },

    leaveNowEmoji: { fontSize: 64, marginBottom: 16 },
    leaveNowText: { color: theme.colors.success, fontSize: 36, fontWeight: '700' },

    details: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
        marginBottom: 16,
        borderWidth: 1,
        borderColor: '#eee',
    },
    detailRow: {
        flexDirection: 'row',
        alignItems: 'center',
        paddingVertical: 8,
    },
    detailIcon: { fontSize: 20, marginRight: 12 },
    detailLabel: { flex: 1, color: theme.colors.textMuted, fontSize: 14 },
    detailValue: { color: theme.colors.text, fontSize: 14, fontWeight: '600' },

    reasonCard: {
        backgroundColor: theme.colors.primary,
        borderRadius: 12,
        padding: 16,
        marginBottom: 24,
        opacity: 0.9,
    },
    reasonText: { color: '#fff', fontSize: 14, textAlign: 'center', lineHeight: 20, fontWeight: '500' },

    actionButton: {
        backgroundColor: theme.colors.primary,
        padding: 18,
        borderRadius: 50,
        alignItems: 'center',
        marginBottom: 12,
        shadowColor: theme.colors.primary,
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
    },
    actionButtonUrgent: { backgroundColor: theme.colors.success },
    actionButtonText: { color: '#fff', fontSize: 18, fontWeight: '600' },

    notifyButton: {
        padding: 16,
        alignItems: 'center',
    },
    notifyButtonText: { color: theme.colors.primary, fontSize: 16 },
});
