import type { TimeIntervalTriggerInput } from 'expo-notifications';

type NotificationsModule = typeof import('expo-notifications');

let Notifications: NotificationsModule | null = null;
try {
    Notifications = require('expo-notifications') as NotificationsModule;
} catch (err) {
    console.warn('[Nudge] expo-notifications native module unavailable; estimate nudges disabled.', err);
}

export type EstimateNudgeReason = 'foreground_only' | 'gps_estimate';

interface ScheduledNudge {
    notificationId: string;
    reason: EstimateNudgeReason;
    delayBucketSeconds: number;
}

const scheduledEstimateNudges = new Map<string, ScheduledNudge>();
let notificationHandlerConfigured = false;
let permissionCheckedAt = 0;
let permissionGranted = false;
const PERMISSION_CACHE_TTL_MS = 60_000;

export function configureNudgeNotifications(): void {
    if (!Notifications) {
        return;
    }
    if (notificationHandlerConfigured) {
        return;
    }
    Notifications.setNotificationHandler({
        handleNotification: async () => ({
            shouldShowBanner: true,
            shouldShowList: true,
            shouldPlaySound: false,
            shouldSetBadge: false,
        }),
    });
    notificationHandlerConfigured = true;
}

async function ensureNotificationPermission(): Promise<boolean> {
    if (!Notifications) {
        return false;
    }
    const now = Date.now();
    if (now - permissionCheckedAt < PERMISSION_CACHE_TTL_MS) {
        return permissionGranted;
    }

    try {
        let permission = await Notifications.getPermissionsAsync();
        if (permission.status !== 'granted' && permission.canAskAgain) {
            permission = await Notifications.requestPermissionsAsync();
        }
        permissionGranted = permission.status === 'granted';
        permissionCheckedAt = now;
        return permissionGranted;
    } catch (err) {
        permissionGranted = false;
        permissionCheckedAt = now;
        console.warn('[Nudge] Failed to obtain notifications permission:', err);
        return false;
    }
}

function computeDelaySeconds(ttaSeconds: number): number | null {
    if (!Number.isFinite(ttaSeconds) || ttaSeconds <= 0) {
        return 45;
    }

    // Keep nudges focused on the "likely arriving soon" window.
    if (ttaSeconds > 45 * 60) {
        return null;
    }

    // For imminent arrivals, nudge quickly.
    if (ttaSeconds <= 8 * 60) {
        return 45;
    }

    // Otherwise nudge roughly 5 minutes before estimated arrival.
    return Math.max(60, Math.round(ttaSeconds - 5 * 60));
}

function buildNudgeBody(reason: EstimateNudgeReason): string {
    if (reason === 'gps_estimate') {
        return 'Estimate only: GPS signal is limited. Open AADI to refresh live location and tap "I\'m Here" if you already arrived.';
    }
    return 'Estimate only: background tracking is off because Always Location is not enabled. Open AADI to refresh and confirm arrival.';
}

export async function scheduleEstimateArrivalNudge(
    orderId: string,
    ttaSeconds: number,
    reason: EstimateNudgeReason
): Promise<void> {
    if (!Notifications) {
        return;
    }
    if (!orderId) {
        return;
    }

    const delaySeconds = computeDelaySeconds(ttaSeconds);
    if (delaySeconds == null) {
        await cancelEstimateArrivalNudge(orderId);
        return;
    }

    const delayBucketSeconds = Math.round(delaySeconds / 60) * 60;
    const existing = scheduledEstimateNudges.get(orderId);
    if (
        existing &&
        existing.reason === reason &&
        Math.abs(existing.delayBucketSeconds - delayBucketSeconds) <= 60
    ) {
        return;
    }

    const hasPermission = await ensureNotificationPermission();
    if (!hasPermission) {
        return;
    }

    if (existing) {
        await Notifications.cancelScheduledNotificationAsync(existing.notificationId).catch(() => undefined);
    }

    const minutes = Math.max(1, Math.round(delaySeconds / 60));
    const notificationId = await Notifications.scheduleNotificationAsync({
        content: {
            title: 'Arrival estimate reminder',
            body: `${buildNudgeBody(reason)} Approx ETA: ${minutes} min.`,
            data: {
                type: 'estimate_arrival_nudge',
                orderId,
                estimateOnly: true,
            },
        },
        trigger: {
            seconds: delaySeconds,
            repeats: false,
        } as TimeIntervalTriggerInput,
    });

    scheduledEstimateNudges.set(orderId, {
        notificationId,
        reason,
        delayBucketSeconds,
    });
}

export async function cancelEstimateArrivalNudge(orderId: string): Promise<void> {
    if (!Notifications) {
        return;
    }
    const existing = scheduledEstimateNudges.get(orderId);
    if (!existing) {
        return;
    }
    scheduledEstimateNudges.delete(orderId);
    await Notifications.cancelScheduledNotificationAsync(existing.notificationId).catch(() => undefined);
}
