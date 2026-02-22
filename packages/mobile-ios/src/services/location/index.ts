/**
 * Location Tracking Service
 * Modularized Refactor (MB-1)
 * 
 * Facade for:
 * - config.ts (Thresholds)
 * - processor.ts (Hybrid Geofencing Logic)
 * - utils/queue.ts (Async Event Delivery)
 * - state.ts (Singleton State)
 */
import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import { Platform } from 'react-native';
import { AsyncMutex, SerialEventQueue } from './utils/queue';
import { getTrackingState, resetTrackingState } from './state';
import { processLocationUpdate } from './processor';
import { RestaurantLocation } from './types';
import {
    cancelEstimateArrivalNudge,
    EstimateNudgeReason,
    scheduleEstimateArrivalNudge,
} from '../notifications';

const LOCATION_TASK_NAME = 'arrive-background-location';
type TrackingMode = 'task' | 'foreground';
export type TrackingPermissionLevel = 'none' | 'foreground' | 'background';

interface PermissionRequestOptions {
    requestBackground?: boolean;
}

interface ForegroundWatchConfig {
    accuracy: Location.Accuracy;
    distanceInterval: number;
    timeInterval: number;
}

// Module-level context (must be top-level for Expo TaskManager)
let activeRestaurant: RestaurantLocation | null = null;
let activeOrderId: string | null = null;
let onArrivalEvent: ((event: string, orderId: string, metadata?: any) => void) | null = null;
let onLocationSample: ((orderId: string, sample: any) => void | Promise<void>) | null = null;
let activeTrackingMode: TrackingMode | null = null;
let foregroundSubscription: Location.LocationSubscription | null = null;

// Singleton instances
const processingMutex = new AsyncMutex();
const eventQueue = new SerialEventQueue();

function clearTrackingContext(): void {
    const trackedOrderId = activeOrderId;
    onArrivalEvent = null;
    onLocationSample = null;
    activeRestaurant = null;
    activeOrderId = null;
    activeTrackingMode = null;
    eventQueue.clear();
    resetTrackingState();
    if (trackedOrderId) {
        void cancelEstimateArrivalNudge(trackedOrderId);
    }
}

async function syncEstimateNudge(instructions: any): Promise<void> {
    if (!activeOrderId) {
        return;
    }

    if (activeTrackingMode !== 'foreground') {
        await cancelEstimateArrivalNudge(activeOrderId);
        return;
    }

    const reason: EstimateNudgeReason =
        instructions.hasReliableAccuracy ? 'foreground_only' : 'gps_estimate';

    await scheduleEstimateArrivalNudge(activeOrderId, instructions.ttaSeconds, reason);
}

async function startForegroundWatch(config: ForegroundWatchConfig): Promise<void> {
    if (foregroundSubscription) {
        foregroundSubscription.remove();
        foregroundSubscription = null;
    }

    foregroundSubscription = await Location.watchPositionAsync(
        {
            accuracy: config.accuracy,
            distanceInterval: config.distanceInterval,
            timeInterval: config.timeInterval,
            mayShowUserSettingsDialog: true,
        },
        (location) => {
            void processSingleLocation(location).catch((err) => {
                console.warn('[Location] Foreground processing error:', err);
            });
        }
    );
}

async function processSingleLocation(location: any): Promise<void> {
    if (!location || !activeRestaurant || !activeOrderId) {
        return;
    }

    if (onLocationSample) {
        const latitude = location.coords?.latitude;
        const longitude = location.coords?.longitude;
        const sample = {
            latitude,
            longitude,
            accuracy_m: location.coords?.accuracy,
            speed_mps: location.coords?.speed,
            heading_deg: location.coords?.heading,
            sample_time: location.timestamp,
        };
        if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
            Promise.resolve(onLocationSample(activeOrderId, sample)).catch((err) => {
                console.warn('[Location] Location sample callback failed:', err);
            });
        }
    }

    const release = await processingMutex.acquire();
    try {
        const trackingState = getTrackingState();

        const instructions = await processLocationUpdate(
            location,
            activeRestaurant,
            activeOrderId,
            trackingState,
            eventQueue,
            onArrivalEvent
        );

        if (instructions.shouldUpdateConfig) {
            const distanceInterval = instructions.accuracy === Location.Accuracy.BestForNavigation ? 5 : 50;

            if (activeTrackingMode === 'task') {
                await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
                    accuracy: instructions.accuracy,
                    distanceInterval,
                    deferredUpdatesInterval: instructions.nextInterval,
                    showsBackgroundLocationIndicator: true,
                    pausesUpdatesAutomatically: false,
                    activityType: Location.ActivityType.OtherNavigation,
                });
            } else if (activeTrackingMode === 'foreground') {
                await startForegroundWatch({
                    accuracy: instructions.accuracy,
                    distanceInterval,
                    timeInterval: instructions.nextInterval,
                });
            }

            trackingState.lastConfiguredInterval = instructions.nextInterval;
        }

        trackingState.lastLocationTs = Date.now();
        await syncEstimateNudge(instructions);
    } finally {
        release();
    }
}

// ===== Background Task Registration =====
TaskManager.defineTask(LOCATION_TASK_NAME, async ({ data, error }: any) => {
    if (error) {
        const message = String(error?.message || '');
        const isTransientIosCoreLocationError =
            Platform.OS === 'ios' && message.includes('kCLErrorDomain Code=0');
        const hasActiveTaskTracking = Boolean(activeRestaurant && activeOrderId && activeTrackingMode === 'task');

        if (isTransientIosCoreLocationError || !hasActiveTaskTracking) {
            console.warn('[Location] Task warning:', error);
        } else {
            console.error('[Location] Task error:', error);
        }
        return;
    }

    if (!data || !activeRestaurant || !activeOrderId || activeTrackingMode !== 'task') {
        return;
    }

    const { locations } = data;
    const location = locations?.[0];
    if (!location) {
        return;
    }

    await processSingleLocation(location);
});

export async function getPermissionLevel(): Promise<TrackingPermissionLevel> {
    try {
        const fg = await Location.getForegroundPermissionsAsync();
        if (fg.status !== 'granted') {
            return 'none';
        }

        const bg = await Location.getBackgroundPermissionsAsync();
        if (bg.status === 'granted') {
            return 'background';
        }
        return 'foreground';
    } catch (err) {
        console.warn('[Location] Failed to read permission level:', err);
        return 'none';
    }
}

/**
 * Request location permissions.
 * Returns true when foreground permission is granted.
 * Background permission is best-effort and optional.
 */
export async function requestPermissions(options: PermissionRequestOptions = {}): Promise<boolean> {
    const shouldRequestBackground = options.requestBackground ?? true;

    let fgStatus = (await Location.getForegroundPermissionsAsync()).status;
    if (fgStatus !== 'granted') {
        fgStatus = (await Location.requestForegroundPermissionsAsync()).status;
    }
    if (fgStatus !== 'granted') {
        return false;
    }

    if (shouldRequestBackground) {
        try {
            const bg = await Location.getBackgroundPermissionsAsync();
            if (bg.status !== 'granted' && bg.canAskAgain !== false) {
                await Location.requestBackgroundPermissionsAsync();
            }
        } catch (err) {
            console.warn('[Location] Background permission request failed (continuing foreground-only):', err);
        }
    }

    return true;
}

/**
 * Start tracking with Hybrid Geofencing logic.
 */
export async function startLocationTracking(
    restaurant: RestaurantLocation,
    orderId: string,
    onEvent: (event: string, orderId: string, metadata?: any) => void,
    onSample?: (orderId: string, sample: any) => void | Promise<void>
): Promise<void> {
    let trackingState = getTrackingState();

    if (trackingState.isStarted) {
        if (activeOrderId && activeOrderId !== orderId) {
            await stopLocationTracking();
            trackingState = getTrackingState();
        } else {
            activeRestaurant = restaurant;
            activeOrderId = orderId;
            onArrivalEvent = onEvent;
            onLocationSample = onSample || null;
            eventQueue.setSender(async (event, oid, meta) => {
                if (onArrivalEvent) {
                    await Promise.resolve(onArrivalEvent(event, oid, meta));
                }
            });
            return;
        }
    }

    if (trackingState.isStarted) {
        return;
    }

    onArrivalEvent = onEvent;
    onLocationSample = onSample || null;
    activeRestaurant = restaurant;
    activeOrderId = orderId;
    eventQueue.setSender(async (event, oid, meta) => {
        if (onArrivalEvent) {
            await Promise.resolve(onArrivalEvent(event, oid, meta));
        }
    });

    const permissionLevel = await getPermissionLevel();
    if (permissionLevel === 'none') {
        clearTrackingContext();
        throw new Error('Location permission is required to start tracking');
    }

    trackingState.isStarted = true;
    console.log(`[Location] Starting Hybrid Geofencing for order ${orderId}`);

    try {
        const canUseTaskTracking =
            permissionLevel === 'background' ||
            (Platform.OS === 'ios' && permissionLevel === 'foreground');

        if (canUseTaskTracking) {
            activeTrackingMode = 'task';
            await cancelEstimateArrivalNudge(orderId);
            try {
                await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
                    accuracy: Location.Accuracy.Balanced,
                    distanceInterval: 50,
                    deferredUpdatesInterval: 1000,
                    showsBackgroundLocationIndicator: true,
                    pausesUpdatesAutomatically: false,
                    activityType: Location.ActivityType.OtherNavigation,
                    foregroundService: {
                        notificationTitle: 'AADI',
                        notificationBody: 'Tracking your arrival...',
                        notificationColor: '#6366f1',
                    },
                });

                if (permissionLevel === 'foreground' && Platform.OS === 'ios') {
                    console.log('[Location] iOS session tracking active (blue location indicator expected while backgrounded).');
                }
            } catch (taskErr) {
                if (permissionLevel === 'foreground' && Platform.OS === 'ios') {
                    console.warn('[Location] iOS session tracking unavailable; falling back to foreground-only tracking:', taskErr);
                    activeTrackingMode = 'foreground';
                    await startForegroundWatch({
                        accuracy: Location.Accuracy.Balanced,
                        distanceInterval: 50,
                        timeInterval: 1000,
                    });
                } else {
                    throw taskErr;
                }
            }
        } else {
            activeTrackingMode = 'foreground';
            console.log('[Location] Background permission not granted; using foreground-only tracking.');
            await startForegroundWatch({
                accuracy: Location.Accuracy.Balanced,
                distanceInterval: 50,
                timeInterval: 1000,
            });
        }
    } catch (err) {
        clearTrackingContext();
        throw err;
    }
}

export async function triggerImmediateVicinityCheck(): Promise<'exact' | 'estimate' | 'skipped'> {
    if (!activeRestaurant || !activeOrderId || !getTrackingState().isStarted) {
        return 'skipped';
    }

    const permissionLevel = await getPermissionLevel();
    if (permissionLevel === 'none') {
        return 'skipped';
    }

    try {
        const current = await Location.getCurrentPositionAsync({
            accuracy: Location.Accuracy.High,
            mayShowUserSettingsDialog: false,
        });
        await processSingleLocation(current);
        return 'exact';
    } catch (liveErr) {
        try {
            const lastKnown = await Location.getLastKnownPositionAsync({
                maxAge: 5 * 60 * 1000,
                requiredAccuracy: 250,
            });
            if (lastKnown) {
                console.warn('[Location] Immediate check fell back to last known location estimate.');
                await processSingleLocation(lastKnown);
                return 'estimate';
            }
        } catch (lastKnownErr) {
            console.warn('[Location] Last-known location lookup failed:', lastKnownErr);
        }

        console.warn('[Location] Immediate vicinity check skipped; no usable location fix:', liveErr);
        return 'skipped';
    }
}

/**
 * Stop tracking. Resets all state.
 */
export async function stopLocationTracking(): Promise<void> {
    let stopped = false;

    try {
        const isTracking = await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK_NAME);
        if (isTracking) {
            await Location.stopLocationUpdatesAsync(LOCATION_TASK_NAME);
            stopped = true;
        }
    } catch (err) {
        console.warn('[Location] Stop error (non-fatal):', err);
    }

    if (foregroundSubscription) {
        foregroundSubscription.remove();
        foregroundSubscription = null;
        stopped = true;
    }

    if (stopped) {
        console.log('[Location] Tracking stopped.');
    }

    clearTrackingContext();
}

/**
 * Get current location (one-shot)
 */
export async function getCurrentLocation(): Promise<{ latitude: number; longitude: number } | null> {
    try {
        const location = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
        return {
            latitude: location.coords.latitude,
            longitude: location.coords.longitude,
        };
    } catch (error) {
        console.error('Failed to get current location:', error);
        return null;
    }
}

// Export internal utils for testing if needed
export { calculateDistance } from './utils/geo';
