import * as Location from 'expo-location';
import { CONFIG, GEOFENCE_RADII, EVENT_PRIORITY } from './config';
import { TrackingState, RestaurantLocation } from './types';
import { calculateDistance, applyCircuity, isUserApproaching, determineZone } from './utils/geo';
import { SerialEventQueue } from './utils/queue';

/**
 * Core Logic: Hybrid Geofencing
 * Calculates TTA, determines Zone (with hysteresis), adjusts polling, and decides whether to report.
 */
export async function processLocationUpdate(
    location: any,
    restaurant: RestaurantLocation,
    orderId: string,
    trackingState: TrackingState,
    eventQueue: SerialEventQueue,
    onArrivalEvent: ((event: string, orderId: string, metadata?: any) => void) | null
) {
    const now = Date.now();
    const { latitude, longitude, speed } = location.coords;
    const accuracyMeters = Number(location.coords?.accuracy);
    const hasReliableAccuracy = Number.isFinite(accuracyMeters) ? accuracyMeters <= 100 : false;
    const usedEstimatedSpeed = !(speed && speed > 0);

    // 1. Calculate Distance & Smooth Speed
    const straightLineMeters = calculateDistance(latitude, longitude, restaurant.latitude, restaurant.longitude);
    const distanceMeters = applyCircuity(straightLineMeters);

    // Kalman-lite smoothing: weighted average (70% new, 30% old)
    const rawSpeed = usedEstimatedSpeed ? CONFIG.SPEED_FALLBACK : speed;
    trackingState.currentSpeed = (trackingState.currentSpeed === 0)
        ? rawSpeed
        : (rawSpeed * 0.7) + (trackingState.currentSpeed * 0.3);

    // 2. Bearing/Direction Check
    const approaching = isUserApproaching(
        latitude, longitude,
        trackingState.lastLat, trackingState.lastLon,
        restaurant.latitude, restaurant.longitude
    );
    trackingState.lastLat = latitude;
    trackingState.lastLon = longitude;

    // 3. Calculate TTA (Time To Arrival) in seconds
    const effectiveSpeed = Math.max(trackingState.currentSpeed, CONFIG.SPEED_FLOOR);
    let ttaSeconds = distanceMeters / effectiveSpeed;

    // If user is moving AWAY from restaurant, inflate TTA to prevent false zone transitions
    if (!approaching && trackingState.lastLocationTs !== 0) {
        ttaSeconds = ttaSeconds * 2;
    }
    const ttaMinutes = ttaSeconds / 60;

    // 3. Determine Zone with Hysteresis
    const newZone = determineZone(ttaSeconds, trackingState.currentZone);

    // 4. Compute Polling Interval & Accuracy based on Zone
    let nextInterval: number;
    let accuracy: Location.Accuracy;

    switch (newZone) {
        case 'ARRIVAL':
            // < 5 min: Constant 5s, max GPS precision
            nextInterval = CONFIG.INTERVAL_ARRIVAL;
            accuracy = Location.Accuracy.BestForNavigation;
            break;
        case 'MID':
            // 5-15 min: Constant 30s, high GPS precision (Kitchen Prep Window)
            nextInterval = CONFIG.INTERVAL_MID;
            accuracy = Location.Accuracy.High;
            break;
        case 'FAR':
        default:
            // > 15 min: Square Root Decay, low GPS precision (Battery Saving)
            const intervalMinutes = Math.sqrt(ttaMinutes);
            nextInterval = intervalMinutes * 60 * 1000;
            nextInterval = Math.max(CONFIG.SQRT_MIN, Math.min(nextInterval, CONFIG.SQRT_MAX));
            accuracy = Location.Accuracy.Low;
            break;
    }

    // 5. Zone Transition Detection
    trackingState.currentZone = newZone;

    // 6. Evaluate Reporting Rules (Privacy Filter)
    let shouldReport = false;
    let eventName = 'LOCATION_UPDATE';

    // Rule A: Critical Spatial Events
    // Priority: AT_DOOR (3) > PARKING (2) > 5_MIN_OUT (1)
    if (straightLineMeters < GEOFENCE_RADII.AT_DOOR) {
        eventName = 'AT_DOOR';
        shouldReport = true;
    } else if (straightLineMeters < GEOFENCE_RADII.PARKING) {
        eventName = 'PARKING';
        shouldReport = true;
    } else if (straightLineMeters < GEOFENCE_RADII.FIVE_MIN_OUT || ttaSeconds < 300) {
        eventName = '5_MIN_OUT';
        shouldReport = true;
    }

    // Cascade Suppression
    const isGeofenceEvent = eventName in EVENT_PRIORITY;
    if (shouldReport && isGeofenceEvent) {
        const eventPriority = EVENT_PRIORITY[eventName];
        if (eventPriority < trackingState.highestFiredPriority) {
            console.log(`[Location] Suppressed ${eventName} (priority ${eventPriority} < ${trackingState.highestFiredPriority})`);
            shouldReport = false;
        }
    }

    // Rule B: Significant Drift & Heartbeat
    if (!shouldReport) {
        const drift = Math.abs(ttaSeconds - (trackingState.lastReportedTta || ttaSeconds));
        const timeSinceReport = now - trackingState.lastReportTs;

        if (ttaMinutes > CONFIG.ZONE_FAR && drift > CONFIG.REPORT_DRIFT_FAR) {
            shouldReport = true;
        } else if (ttaMinutes > CONFIG.ZONE_MID && drift > CONFIG.REPORT_DRIFT_MID) {
            shouldReport = true;
        } else if (timeSinceReport > CONFIG.HEARTBEAT) {
            eventName = 'HEARTBEAT';
            shouldReport = true;
        }
    }

    // 7. Execute Report (if needed)
    if (shouldReport && onArrivalEvent) {
        const isDuplicate = (
            trackingState.lastReportedEvent === eventName &&
            (now - trackingState.lastReportTs) < CONFIG.EVENT_DEBOUNCE_MS
        );

        if (!isDuplicate) {
            eventQueue.enqueue(eventName, orderId, undefined);

            trackingState.lastReportTs = now;
            trackingState.lastReportedTta = ttaSeconds;
            trackingState.lastReportedEvent = eventName;

            if (eventName in EVENT_PRIORITY) {
                trackingState.firedEvents.add(eventName);
                trackingState.highestFiredPriority = Math.max(
                    trackingState.highestFiredPriority,
                    EVENT_PRIORITY[eventName]
                );
            }
        }
    }

    // 8. Re-configure Polling (The "Tether")
    // Note: returning instructions would be cleaner, but we'll accept the side-effect here for now as planned
    return {
        nextInterval,
        accuracy,
        shouldUpdateConfig: (trackingState.lastConfiguredInterval === 0 || Math.abs(nextInterval - trackingState.lastConfiguredInterval) > 5000),
        ttaSeconds,
        usedEstimatedSpeed,
        hasReliableAccuracy,
    };
}
