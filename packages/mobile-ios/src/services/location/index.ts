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
import { AsyncMutex, SerialEventQueue } from './utils/queue';
import { getTrackingState, resetTrackingState } from './state';
import { processLocationUpdate } from './processor';
import { RestaurantLocation } from './types';

const LOCATION_TASK_NAME = 'arrive-background-location';

// Module-level context (must be top-level for Expo TaskManager)
let activeRestaurant: RestaurantLocation | null = null;
let activeOrderId: string | null = null;
let onArrivalEvent: ((event: string, orderId: string, metadata?: any) => void) | null = null;

// Singleton instances
const processingMutex = new AsyncMutex();
const eventQueue = new SerialEventQueue();

// ===== Background Task Registration =====
TaskManager.defineTask(LOCATION_TASK_NAME, async ({ data, error }: any) => {
    if (error) {
        console.error('[Location] Task error:', error);
        return;
    }

    if (data && activeRestaurant && activeOrderId) {
        const { locations } = data;
        const location = locations[0];

        if (location) {
            const release = await processingMutex.acquire();
            try {
                const trackingState = getTrackingState();

                // Execute Logic
                const instructions = await processLocationUpdate(
                    location,
                    activeRestaurant,
                    activeOrderId,
                    trackingState,
                    eventQueue,
                    onArrivalEvent
                );

                // Apply Side Effects (Polling updates)
                if (instructions.shouldUpdateConfig) {
                    await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
                        accuracy: instructions.accuracy,
                        distanceInterval: instructions.accuracy === Location.Accuracy.BestForNavigation ? 5 : 50,
                        deferredUpdatesInterval: instructions.nextInterval,
                        showsBackgroundLocationIndicator: true,
                    });
                    trackingState.lastConfiguredInterval = instructions.nextInterval;
                }

                trackingState.lastLocationTs = Date.now();

            } finally {
                release();
            }
        }
    }
});

/**
 * Request location permissions
 */
export async function requestPermissions(): Promise<boolean> {
    const { status: fgStatus } = await Location.requestForegroundPermissionsAsync();
    if (fgStatus !== 'granted') return false;

    const { status: bgStatus } = await Location.requestBackgroundPermissionsAsync();
    return bgStatus === 'granted';
}

/**
 * Start tracking with Hybrid Geofencing logic.
 */
export async function startLocationTracking(
    restaurant: RestaurantLocation,
    orderId: string,
    onEvent: (event: string, orderId: string, metadata?: any) => void
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
    trackingState.isStarted = true;
    onArrivalEvent = onEvent;

    activeRestaurant = restaurant;
    activeOrderId = orderId;
    console.log(`[Location] Starting Hybrid Geofencing for order ${orderId}`);

    eventQueue.setSender(async (event, oid, meta) => {
        if (onArrivalEvent) {
            await Promise.resolve(onArrivalEvent(event, oid, meta));
        }
    });

    await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
        accuracy: Location.Accuracy.Balanced,
        distanceInterval: 50,
        deferredUpdatesInterval: 1000,
        showsBackgroundLocationIndicator: true,
        foregroundService: {
            notificationTitle: 'AADI',
            notificationBody: 'Tracking your arrival...',
            notificationColor: '#6366f1',
        },
    });
}

/**
 * Stop tracking. Resets all state.
 */
export async function stopLocationTracking(): Promise<void> {
    try {
        const isTracking = await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK_NAME);
        if (isTracking) {
            await Location.stopLocationUpdatesAsync(LOCATION_TASK_NAME);
            console.log('[Location] Tracking stopped.');
        }
    } catch (err) {
        console.warn('[Location] Stop error (non-fatal):', err);
    }
    onArrivalEvent = null;
    activeRestaurant = null;
    activeOrderId = null;
    eventQueue.clear();
    resetTrackingState();
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
