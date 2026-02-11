/**
 * Tip Screen
 * Agent Mu: Ambient Exit Tipping UX
 */
import React, { useState } from 'react';
import {
    View,
    Text,
    StyleSheet,
    TouchableOpacity,
    TextInput,
    Alert,
} from 'react-native';
import { addTip } from '../services/api';
import { theme } from '../theme';

interface Props {
    route: any;
    navigation: any;
}

// Standard tip percentages
const TIP_OPTIONS = [
    { percent: 15, emoji: '👍' },
    { percent: 18, emoji: '😊' },
    { percent: 20, emoji: '🌟' },
    { percent: 25, emoji: '💯' },
];

export default function TipScreen({ route, navigation }: Props) {
    const { order } = route.params;
    const [selectedTip, setSelectedTip] = useState<number | null>(18);
    const [customTip, setCustomTip] = useState('');
    const [isCustom, setIsCustom] = useState(false);
    const [rating, setRating] = useState(5);
    const [submitting, setSubmitting] = useState(false);

    const subtotal = order?.total_cents || 0;

    const getTipAmount = () => {
        if (isCustom && customTip) {
            return Math.round(parseFloat(customTip) * 100);
        }
        if (selectedTip) {
            return Math.round((subtotal * selectedTip) / 100);
        }
        return 0;
    };

    const handleSubmitTip = async () => {
        const tipAmount = getTipAmount();

        if (tipAmount <= 0) {
            navigation.goBack();
            return;
        }

        setSubmitting(true);
        try {
            await addTip(order.order_id, tipAmount);
            Alert.alert(
                '🙏 Thank You!',
                `Your $${(tipAmount / 100).toFixed(2)} tip has been added. See you next time!`,
                [{ text: 'Done', onPress: () => navigation.popToTop() }]
            );
        } catch (error) {
            Alert.alert('Error', 'Failed to add tip. Please try again.');
        } finally {
            setSubmitting(false);
        }
    };

    const handleSkip = () => {
        Alert.alert(
            'Skip Tip?',
            'You can add a tip later from your order history.',
            [
                { text: 'Go Back', style: 'cancel' },
                { text: 'Skip', onPress: () => navigation.popToTop() }
            ]
        );
    };

    return (
        <View style={styles.container}>
            {/* Header */}
            <View style={styles.header}>
                <Text style={styles.headerEmoji}>👋</Text>
                <Text style={styles.headerTitle}>Thanks for dining with us!</Text>
                <Text style={styles.headerSubtitle}>How was your experience?</Text>
            </View>

            {/* Star Rating */}
            <View style={styles.ratingContainer}>
                {[1, 2, 3, 4, 5].map((star) => (
                    <TouchableOpacity key={star} onPress={() => setRating(star)}>
                        <Text style={[styles.star, star <= rating && styles.starActive]}>
                            ⭐
                        </Text>
                    </TouchableOpacity>
                ))}
            </View>

            {/* Tip Section */}
            <View style={styles.tipSection}>
                <Text style={styles.tipTitle}>Add a tip for your server</Text>

                {/* Preset Tips */}
                <View style={styles.tipOptions}>
                    {TIP_OPTIONS.map((option) => {
                        const tipCents = Math.round((subtotal * option.percent) / 100);
                        const isSelected = !isCustom && selectedTip === option.percent;

                        return (
                            <TouchableOpacity
                                key={option.percent}
                                style={[styles.tipButton, isSelected && styles.tipButtonSelected]}
                                onPress={() => {
                                    setSelectedTip(option.percent);
                                    setIsCustom(false);
                                }}
                            >
                                <Text style={styles.tipEmoji}>{option.emoji}</Text>
                                <Text style={[styles.tipPercent, isSelected && styles.tipTextSelected]}>
                                    {option.percent}%
                                </Text>
                                <Text style={[styles.tipAmount, isSelected && styles.tipTextSelected]}>
                                    ${(tipCents / 100).toFixed(2)}
                                </Text>
                            </TouchableOpacity>
                        );
                    })}
                </View>

                {/* Custom Tip */}
                <TouchableOpacity
                    style={[styles.customTipButton, isCustom && styles.customTipActive]}
                    onPress={() => setIsCustom(true)}
                >
                    {isCustom ? (
                        <View style={styles.customInputRow}>
                            <Text style={styles.dollarSign}>$</Text>
                            <TextInput
                                style={styles.customInput}
                                value={customTip}
                                onChangeText={setCustomTip}
                                keyboardType="decimal-pad"
                                placeholder="0.00"
                                placeholderTextColor="#94a3b8"
                                autoFocus
                            />
                        </View>
                    ) : (
                        <Text style={styles.customTipText}>Custom Amount</Text>
                    )}
                </TouchableOpacity>
            </View>

            {/* Summary */}
            <View style={styles.summary}>
                <View style={styles.summaryRow}>
                    <Text style={styles.summaryLabel}>Subtotal</Text>
                    <Text style={styles.summaryValue}>${(subtotal / 100).toFixed(2)}</Text>
                </View>
                <View style={styles.summaryRow}>
                    <Text style={styles.summaryLabel}>Tip</Text>
                    <Text style={[styles.summaryValue, styles.tipValue]}>
                        ${(getTipAmount() / 100).toFixed(2)}
                    </Text>
                </View>
                <View style={[styles.summaryRow, styles.totalRow]}>
                    <Text style={styles.totalLabel}>Total</Text>
                    <Text style={styles.totalValue}>
                        ${((subtotal + getTipAmount()) / 100).toFixed(2)}
                    </Text>
                </View>
                <Text style={styles.cardNote}>
                    Will be charged to card ending in **4242
                </Text>
            </View>

            {/* Actions */}
            <View style={styles.actions}>
                <TouchableOpacity
                    style={styles.submitButton}
                    onPress={handleSubmitTip}
                    disabled={submitting}
                >
                    <Text style={styles.submitButtonText}>
                        {submitting ? 'Processing...' : 'Leave Tip'}
                    </Text>
                </TouchableOpacity>

                <TouchableOpacity style={styles.skipButton} onPress={handleSkip}>
                    <Text style={styles.skipButtonText}>Skip for now</Text>
                </TouchableOpacity>
            </View>
        </View>
    );
}

const styles = StyleSheet.create({
    container: { flex: 1, backgroundColor: theme.colors.background, padding: 20 },
    header: { alignItems: 'center', marginBottom: 24 },
    headerEmoji: { fontSize: 48, marginBottom: 12 },
    headerTitle: { color: theme.colors.text, fontSize: 24, fontWeight: '700', marginBottom: 8, fontFamily: theme.typography.header.fontFamily },
    headerSubtitle: { color: theme.colors.textMuted, fontSize: 16 },
    ratingContainer: { flexDirection: 'row', justifyContent: 'center', marginBottom: 32, gap: 8 },
    star: { fontSize: 32, opacity: 0.3 },
    starActive: { opacity: 1 },
    tipSection: { marginBottom: 24 },
    tipTitle: { color: theme.colors.text, fontSize: 18, fontWeight: '600', marginBottom: 16, textAlign: 'center' },
    tipOptions: { flexDirection: 'row', gap: 12, marginBottom: 12 },
    tipButton: {
        flex: 1,
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
        alignItems: 'center',
        borderWidth: 2,
        borderColor: '#e2e8f0',
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.05,
        shadowRadius: 4,
    },
    tipButtonSelected: { borderColor: theme.colors.primary, backgroundColor: theme.colors.background },
    tipEmoji: { fontSize: 24, marginBottom: 4 },
    tipPercent: { color: theme.colors.text, fontSize: 16, fontWeight: '600' },
    tipAmount: { color: theme.colors.textMuted, fontSize: 14 },
    tipTextSelected: { color: theme.colors.primary },
    customTipButton: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
        alignItems: 'center',
        borderWidth: 2,
        borderColor: '#e2e8f0',
    },
    customTipActive: { borderColor: theme.colors.primary },
    customTipText: { color: theme.colors.textMuted, fontSize: 16 },
    customInputRow: { flexDirection: 'row', alignItems: 'center' },
    dollarSign: { color: theme.colors.text, fontSize: 24, marginRight: 8 },
    customInput: { color: theme.colors.text, fontSize: 24, minWidth: 80, textAlign: 'center' },
    summary: {
        backgroundColor: '#fff',
        borderRadius: 12,
        padding: 16,
        marginBottom: 24,
        borderWidth: 1,
        borderColor: '#eee',
    },
    summaryRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
    summaryLabel: { color: theme.colors.textMuted, fontSize: 14 },
    summaryValue: { color: theme.colors.text, fontSize: 14 },
    tipValue: { color: theme.colors.success },
    totalRow: { borderTopWidth: 1, borderTopColor: '#f1f5f9', paddingTop: 12, marginTop: 8 },
    totalLabel: { color: theme.colors.text, fontSize: 18, fontWeight: '600' },
    totalValue: { color: theme.colors.text, fontSize: 18, fontWeight: '700' },
    cardNote: { color: theme.colors.textMuted, fontSize: 12, textAlign: 'center', marginTop: 12 },
    actions: { gap: 12 },
    submitButton: {
        backgroundColor: theme.colors.primary,
        padding: 16,
        borderRadius: 50,
        alignItems: 'center',
        shadowColor: theme.colors.primary,
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.2,
        shadowRadius: 8,
    },
    submitButtonText: { color: '#fff', fontSize: 18, fontWeight: '600' },
    skipButton: { alignItems: 'center', padding: 12 },
    skipButtonText: { color: theme.colors.textMuted, fontSize: 14 },
});
