/**
 * Location Tracking Service
 * Agent Kappa: iOS GPS Integration
 * 
 * Handles background location updates and geofence triggers.
 */
import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';

const LOCATION_TASK_NAME = 'arrive-background-location';

// Adaptive Tracking Config
const UPDATE_INTERVALS = {
    FAR: 300000, // 5 mins (ms)
    NEAR: 30000,  // 30 sec (ms)
};
const NEAR_THRESHOLD_METERS = 5000; // 5km

let lastUpdateTimestamp = 0;

// Geofence radii in meters
export const GEOFENCE_RADII = {
    FIVE_MIN: 1500,    // ~5 min driving
    PARKING: 100,      // Parking lot
    AT_DOOR: 20,       // At restaurant entrance
    EXIT: 500,         // Left the area
};

interface RestaurantLocation {
    latitude: number;
    longitude: number;
    restaurantId: string;
}

// Event callbacks
let onArrivalEvent: ((event: string, orderId: string) => void) | null = null;

/**
 * Request location permissions
 */
export async function requestPermissions(): Promise<boolean> {
    const { status: foregroundStatus } = await Location.requestForegroundPermissionsAsync();
    if (foregroundStatus !== 'granted') {
        console.log('Foreground permission denied');
        return false;
    }

    const { status: backgroundStatus } = await Location.requestBackgroundPermissionsAsync();
    if (backgroundStatus !== 'granted') {
        console.log('Background permission denied - limited tracking only');
        // Can still work with foreground only
    }

    return true;
}

/**
 * Start tracking location towards a restaurant
 */
export async function startLocationTracking(
    restaurant: RestaurantLocation,
    orderId: string,
    onEvent: (event: string, orderId: string) => void
): Promise<void> {
    onArrivalEvent = onEvent;

    // Store context for background task
    await TaskManager.defineTask(LOCATION_TASK_NAME, async ({ data, error }: any) => {
        if (error) {
            console.error('Location task error:', error);
            return;
        }

        if (data) {
            const { locations } = data;
            const location = locations[0];

            if (location) {
                const distance = calculateDistance(
                    location.coords.latitude,
                    location.coords.longitude,
                    restaurant.latitude,
                    restaurant.longitude
                );

                const now = Date.now();
                const isNear = distance < NEAR_THRESHOLD_METERS;
                const interval = isNear ? UPDATE_INTERVALS.NEAR : UPDATE_INTERVALS.FAR;

                // Adaptive Throttling
                if (now - lastUpdateTimestamp > interval) {
                    if (onArrivalEvent) {
                        // Send generic update for tracking map
                        onArrivalEvent('LOCATION_UPDATE', orderId);
                    }
                    lastUpdateTimestamp = now;
                }

                // Determine arrival status based on distance
                let event = null;
                if (distance < GEOFENCE_RADII.AT_DOOR) {
                    event = 'AT_DOOR';
                } else if (distance < GEOFENCE_RADII.PARKING) {
                    event = 'PARKING';
                } else if (distance < GEOFENCE_RADII.FIVE_MIN) {
                    event = '5_MIN_OUT';
                }

                if (event && onArrivalEvent) {
                    onArrivalEvent(event, orderId);
                }
            }
        }
    });

    await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
        accuracy: Location.Accuracy.Balanced,
        distanceInterval: 50, // Update every 50m
        deferredUpdatesInterval: 30000, // Or every 30 seconds
        showsBackgroundLocationIndicator: true,
        foregroundService: {
            notificationTitle: 'AADI',
            notificationBody: 'Tracking your arrival...',
            notificationColor: '#6366f1',
        },
    });

    console.log('Location tracking started');
}

/**
 * Stop tracking
 */
export async function stopLocationTracking(): Promise<void> {
    const isTracking = await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK_NAME);
    if (isTracking) {
        await Location.stopLocationUpdatesAsync(LOCATION_TASK_NAME);
        console.log('Location tracking stopped');
    }
    onArrivalEvent = null;
}

/**
 * Get current location (one-shot)
 */
export async function getCurrentLocation(): Promise<{ latitude: number; longitude: number } | null> {
    try {
        const location = await Location.getCurrentPositionAsync({
            accuracy: Location.Accuracy.Balanced,
        });
        return {
            latitude: location.coords.latitude,
            longitude: location.coords.longitude,
        };
    } catch (error) {
        console.error('Failed to get current location:', error);
        return null;
    }
}

/**
 * Calculate distance between two points (Haversine formula)
 */
function calculateDistance(
    lat1: number, lon1: number,
    lat2: number, lon2: number
): number {
    const R = 6371e3; // Earth's radius in meters
    const φ1 = (lat1 * Math.PI) / 180;
    const φ2 = (lat2 * Math.PI) / 180;
    const Δφ = ((lat2 - lat1) * Math.PI) / 180;
    const Δλ = ((lon2 - lon1) * Math.PI) / 180;

    const a =
        Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
        Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

    return R * c;
}
