/**
 * Location Tracking Service
 * Agent Kappa: iOS GPS Integration (Hybrid Geofencing)
 * 
 * Handles background location updates with "Hybrid" logic:
 * - Far (>15m TTA): Square Root Decay (Interval = sqrt(TTA))
 * - Mid (5-15m TTA): Constant 30s (Kitchen Prep Window)
 * - Near (<5m TTA): Constant 5s (Live Arrival)
 * - Privacy by Design: Low data retention, local TTA calculation.
 * 
 * Hysteresis: Zone boundaries have ±30s buffers to prevent rapid toggling.
 */
import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';

const LOCATION_TASK_NAME = 'arrive-background-location';

// --- Configuration ---
const CONFIG = {
    // Hybrid Zone Thresholds (in minutes)
    ZONE_FAR: 15,       // > 15 min -> Square Root Decay
    ZONE_MID: 5,        // 5 - 15 min -> Constant 30s
    // < 5 min -> Constant 5s (Arrival)

    // Hysteresis Buffer (in seconds)
    // Prevents rapid zone toggling when TTA oscillates near a boundary
    HYSTERESIS_BUFFER: 30, // 30s buffer on each side of zone boundary

    // Fixed Polling Intervals (in ms)
    INTERVAL_MID: 30000,    // 30 sec (Kitchen Prep zone)
    INTERVAL_ARRIVAL: 5000, // 5 sec (Live tracking)

    // Square Root Decay Clamps (in ms)
    SQRT_MIN: 60000,        // 1 min floor
    SQRT_MAX: 600000,       // 10 min ceiling

    // Reporting Thresholds (Drift in seconds)
    REPORT_DRIFT_FAR: 300,  // Report if ETA changes by > 5 min
    REPORT_DRIFT_MID: 120,  // Report if ETA changes by > 2 min
    HEARTBEAT: 900000,      // 15 min heartbeat

    // Speed Defaults (m/s)
    SPEED_FALLBACK: 5.0,    // 18 km/h - used when GPS speed is unavailable
    SPEED_FLOOR: 1.5,       // ~5 km/h - minimum speed to prevent TTA -> infinity (walking pace)

    // Debounce
    EVENT_DEBOUNCE_MS: 10000, // Don't re-send the same event within 10s
};

// Geofence radii for events (in meters)
export const GEOFENCE_RADII = {
    FIVE_MIN_OUT: 1500, // ~5 min driving at city speeds (approx)
    PARKING: 150,       // Parking lot detection
    AT_DOOR: 30,        // Hand-off proximity
};

// Zone names for logging & zone-transition events
type Zone = 'FAR' | 'MID' | 'ARRIVAL';

interface RestaurantLocation {
    latitude: number;
    longitude: number;
    restaurantId: string;
}

// Geofence event priority (higher index = higher priority)
const EVENT_PRIORITY: Record<string, number> = {
    '5_MIN_OUT': 1,
    'PARKING': 2,
    'AT_DOOR': 3,
};

interface TrackingState {
    lastLocationTs: number;
    lastReportedEvent: string; // The actual event name ('AT_DOOR', 'PARKING', etc.)
    lastReportedTta: number | null;
    lastReportTs: number;
    currentSpeed: number;       // m/s (smoothed)
    currentZone: Zone | null;   // Track zone for hysteresis & transition events
    isStarted: boolean;         // Guard against multiple startLocationTracking calls
    firedEvents: Set<string>;   // Events already fired this session (prevents cascade)
    highestFiredPriority: number; // Highest priority event that has fired
}

// Runtime State
let trackingState: TrackingState = {
    lastLocationTs: 0,
    lastReportedEvent: '',
    lastReportedTta: null,
    lastReportTs: 0,
    currentSpeed: 0,
    currentZone: null,
    isStarted: false,
    firedEvents: new Set(),
    highestFiredPriority: 0,
};

// Event callbacks
let onArrivalEvent: ((event: string, orderId: string, metadata?: any) => void) | null = null;

// ===== Concurrency Primitives =====

/**
 * AsyncMutex: Ensures only one processLocationUpdate runs at a time.
 * If a GPS callback fires while the previous is still processing,
 * the new callback waits for the lock instead of racing on trackingState.
 */
class AsyncMutex {
    private _lock: Promise<void> = Promise.resolve();
    private _locked = false;

    async acquire(): Promise<() => void> {
        let release: () => void;
        const newLock = new Promise<void>((resolve) => {
            release = resolve;
        });

        // Wait for the previous lock to release
        const prevLock = this._lock;
        this._lock = newLock;
        await prevLock;
        this._locked = true;

        return () => {
            this._locked = false;
            release!();
        };
    }

    get isLocked(): boolean {
        return this._locked;
    }
}

/**
 * Serial Event Queue with Retry
 * Ensures events are sent to the backend one-at-a-time, in order,
 * with exponential backoff retry (3 attempts).
 * 
 * Why serial: If 5_MIN_OUT and PARKING fire within 100ms of each other,
 * we want the backend to process 5_MIN_OUT FIRST (it triggers the kitchen).
 * Parallel requests would have no ordering guarantee.
 */
interface QueuedEvent {
    eventName: string;
    orderId: string;
    metadata: any;
    retries: number;
}

class SerialEventQueue {
    private queue: QueuedEvent[] = [];
    private processing = false;
    private sender: ((event: string, orderId: string, metadata?: any) => Promise<void>) | null = null;
    private maxRetries = 3;

    setSender(fn: (event: string, orderId: string, metadata?: any) => Promise<void>) {
        this.sender = fn;
    }

    enqueue(eventName: string, orderId: string, metadata: any) {
        this.queue.push({ eventName, orderId, metadata, retries: 0 });
        console.log(`[EventQueue] Enqueued: ${eventName} (queue depth: ${this.queue.length})`);
        this.drain();
    }

    private async drain() {
        if (this.processing || !this.sender) return;
        this.processing = true;

        while (this.queue.length > 0) {
            const event = this.queue[0];
            try {
                await this.sender(event.eventName, event.orderId, event.metadata);
                this.queue.shift(); // Success: remove from queue
                console.log(`[EventQueue] Sent: ${event.eventName} (remaining: ${this.queue.length})`);
            } catch (err) {
                event.retries++;
                if (event.retries >= this.maxRetries) {
                    console.error(`[EventQueue] DROPPED ${event.eventName} after ${this.maxRetries} retries:`, err);
                    this.queue.shift(); // Give up
                } else {
                    // Exponential backoff: 1s, 2s, 4s
                    const backoff = Math.pow(2, event.retries - 1) * 1000;
                    console.warn(`[EventQueue] Retry ${event.retries}/${this.maxRetries} for ${event.eventName} in ${backoff}ms`);
                    await new Promise(resolve => setTimeout(resolve, backoff));
                }
            }
        }

        this.processing = false;
    }

    clear() {
        this.queue = [];
        this.processing = false;
        this.sender = null;
    }
}

// Singleton instances
const processingMutex = new AsyncMutex();
const eventQueue = new SerialEventQueue();

/**
 * Request location permissions
 */
export async function requestPermissions(): Promise<boolean> {
    const { status: fgStatus } = await Location.requestForegroundPermissionsAsync();
    if (fgStatus !== 'granted') return false;

    const { status: bgStatus } = await Location.requestBackgroundPermissionsAsync();
    return bgStatus === 'granted' || fgStatus === 'granted';
}

/**
 * Start tracking with Hybrid Geofencing logic.
 * Idempotent: safe to call multiple times (will no-op if already running).
 */
export async function startLocationTracking(
    restaurant: RestaurantLocation,
    orderId: string,
    onEvent: (event: string, orderId: string, metadata?: any) => void
): Promise<void> {
    // Guard: Don't restart if already tracking
    if (trackingState.isStarted) {
        return;
    }
    trackingState.isStarted = true;
    onArrivalEvent = onEvent;
    console.log(`[Location] Starting Hybrid Geofencing for order ${orderId}`);

    // Set up the event queue sender (wraps the callback in a Promise)
    eventQueue.setSender(async (event, oid, meta) => {
        if (onArrivalEvent) {
            // Wrap in try/catch so the queue can retry on failure
            onArrivalEvent(event, oid, meta);
        }
    });

    // Define the background task (with mutex for serialization)
    await TaskManager.defineTask(LOCATION_TASK_NAME, async ({ data, error }: any) => {
        if (error) {
            console.error('[Location] Task error:', error);
            return;
        }

        if (data) {
            const { locations } = data;
            const location = locations[0]; // Process most recent

            if (location) {
                // Acquire mutex: ensures only one processLocationUpdate runs at a time
                const release = await processingMutex.acquire();
                try {
                    await processLocationUpdate(location, restaurant, orderId);
                } finally {
                    release(); // Always release, even on error
                }
            }
        }
    });

    // Initial Start - Aggressive to get a first fix, then we'll throttle
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
    eventQueue.clear(); // Drain pending events
    trackingState = {
        lastLocationTs: 0,
        lastReportedEvent: '',
        lastReportedTta: null,
        lastReportTs: 0,
        currentSpeed: 0,
        currentZone: null,
        isStarted: false,
        firedEvents: new Set(),
        highestFiredPriority: 0,
    };
}

/**
 * Determine Zone with Hysteresis
 * 
 * Without hysteresis: TTA oscillating between 14.9 and 15.1 min causes
 * rapid toggling between MID (30s poll) and FAR (sqrt poll), thrashing the GPS radio.
 * 
 * With hysteresis: Once in a zone, the user must cross the boundary by HYSTERESIS_BUFFER
 * seconds to transition. This creates a "dead zone" that absorbs noise.
 * 
 * Example (HYSTERESIS_BUFFER = 30s):
 *   - In FAR zone, boundary is at 15 min. Must drop to 14.5 min to enter MID.
 *   - In MID zone, boundary is at 15 min. Must rise to 15.5 min to re-enter FAR.
 */
function determineZone(ttaSeconds: number, currentZone: Zone | null): Zone {
    const ttaMinutes = ttaSeconds / 60;
    const bufferMinutes = CONFIG.HYSTERESIS_BUFFER / 60; // 0.5 min

    // If no prior zone, use raw boundaries
    if (currentZone === null) {
        if (ttaMinutes < CONFIG.ZONE_MID) return 'ARRIVAL';
        if (ttaMinutes < CONFIG.ZONE_FAR) return 'MID';
        return 'FAR';
    }

    // Apply hysteresis based on current zone
    switch (currentZone) {
        case 'FAR':
            // Must drop BELOW (threshold - buffer) to transition to MID
            if (ttaMinutes < CONFIG.ZONE_FAR - bufferMinutes) {
                // Could also jump straight to ARRIVAL if TTA dropped dramatically
                if (ttaMinutes < CONFIG.ZONE_MID - bufferMinutes) return 'ARRIVAL';
                return 'MID';
            }
            return 'FAR';

        case 'MID':
            // Must rise ABOVE (threshold + buffer) to go back to FAR
            if (ttaMinutes > CONFIG.ZONE_FAR + bufferMinutes) return 'FAR';
            // Must drop BELOW (threshold - buffer) to enter ARRIVAL
            if (ttaMinutes < CONFIG.ZONE_MID - bufferMinutes) return 'ARRIVAL';
            return 'MID';

        case 'ARRIVAL':
            // Must rise ABOVE (threshold + buffer) to go back to MID
            if (ttaMinutes > CONFIG.ZONE_MID + bufferMinutes) {
                // Could also jump straight to FAR
                if (ttaMinutes > CONFIG.ZONE_FAR + bufferMinutes) return 'FAR';
                return 'MID';
            }
            return 'ARRIVAL';

        default:
            return 'MID'; // Safe fallback
    }
}

/**
 * Core Logic: Hybrid Geofencing
 * Calculates TTA, determines Zone (with hysteresis), adjusts polling, and decides whether to report.
 */
async function processLocationUpdate(location: any, restaurant: RestaurantLocation, orderId: string) {
    const now = Date.now();
    const { latitude, longitude, speed } = location.coords;

    // 1. Calculate Distance & Smooth Speed
    const distanceMeters = calculateDistance(latitude, longitude, restaurant.latitude, restaurant.longitude);

    // Kalman-lite smoothing: weighted average (70% new, 30% old)
    const rawSpeed = (speed && speed > 0) ? speed : CONFIG.SPEED_FALLBACK;
    trackingState.currentSpeed = (trackingState.currentSpeed === 0)
        ? rawSpeed
        : (rawSpeed * 0.7) + (trackingState.currentSpeed * 0.3);

    // 2. Calculate TTA (Time To Arrival) in seconds
    const effectiveSpeed = Math.max(trackingState.currentSpeed, CONFIG.SPEED_FLOOR);
    const ttaSeconds = distanceMeters / effectiveSpeed;
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
    if (trackingState.currentZone !== null && trackingState.currentZone !== newZone) {
        console.log(`[Location] Zone transition: ${trackingState.currentZone} -> ${newZone} (TTA: ${Math.round(ttaSeconds)}s)`);
    }
    trackingState.currentZone = newZone;

    // 6. Cold Start Detection
    // If this is the FIRST location update (user just placed an order),
    // check if they're already inside a geofence. If so, fire ONLY the
    // most specific event and suppress lower-priority ones.
    const isColdStart = trackingState.lastLocationTs === 0;

    // 7. Evaluate Reporting Rules (Privacy Filter)
    let shouldReport = false;
    let eventName = 'LOCATION_UPDATE';

    // Rule A: Critical Spatial Events
    // Priority: AT_DOOR (3) > PARKING (2) > 5_MIN_OUT (1)
    // Only fire events that are HIGHER priority than what we've already fired.
    // This prevents: cold start at AT_DOOR -> next poll fires PARKING (wrong direction).
    if (distanceMeters < GEOFENCE_RADII.AT_DOOR) {
        eventName = 'AT_DOOR';
        shouldReport = true;
    } else if (distanceMeters < GEOFENCE_RADII.PARKING) {
        eventName = 'PARKING';
        shouldReport = true;
    } else if (distanceMeters < GEOFENCE_RADII.FIVE_MIN_OUT || ttaSeconds < 300) {
        eventName = '5_MIN_OUT';
        shouldReport = true;
    }

    // Suppress if this event is lower priority than one we've already fired
    // e.g., if AT_DOOR already fired, don't fire PARKING or 5_MIN_OUT
    if (shouldReport && eventName in EVENT_PRIORITY) {
        const eventPriority = EVENT_PRIORITY[eventName];
        if (eventPriority < trackingState.highestFiredPriority) {
            console.log(`[Location] Suppressed ${eventName} (priority ${eventPriority} < ${trackingState.highestFiredPriority})`);
            shouldReport = false;
        }
    }

    // Rule B: Significant Drift & Heartbeat (only if no spatial event was triggered)
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

    // 8. Execute Report (if needed)
    if (shouldReport && onArrivalEvent) {
        // Debounce: Don't re-send the same event name within the debounce window
        const isDuplicate = (
            trackingState.lastReportedEvent === eventName &&
            (now - trackingState.lastReportTs) < CONFIG.EVENT_DEBOUNCE_MS
        );

        if (!isDuplicate) {
            if (isColdStart) {
                console.log(`[Location] COLD START: User already inside geofence. Firing: ${eventName} (dist: ${Math.round(distanceMeters)}m)`);
            }
            console.log(`[Location] Reporting: ${eventName} (TTA: ${Math.round(ttaSeconds)}s, dist: ${Math.round(distanceMeters)}m, zone: ${newZone}, poll: ${nextInterval / 1000}s)`);
            // Enqueue event for serial delivery with retry
            eventQueue.enqueue(eventName, orderId, {
                tta: Math.round(ttaSeconds),
                distance: Math.round(distanceMeters),
                zone: newZone,
                cold_start: isColdStart,
                battery_save: newZone === 'FAR',
            });

            trackingState.lastReportTs = now;
            trackingState.lastReportedTta = ttaSeconds;
            trackingState.lastReportedEvent = eventName;

            // Track fired events for cascade suppression
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
    // Only update if interval changed significantly (>5s difference) to avoid thrashing native APIs
    const timeSinceLastUpdate = now - trackingState.lastLocationTs;
    if (trackingState.lastLocationTs === 0 || Math.abs(nextInterval - timeSinceLastUpdate) > 5000) {
        await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
            accuracy: accuracy,
            distanceInterval: accuracy === Location.Accuracy.BestForNavigation ? 5 : 50,
            deferredUpdatesInterval: nextInterval,
            showsBackgroundLocationIndicator: true,
        });
    }
    trackingState.lastLocationTs = now;
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

/**
 * Calculate distance between two points (Haversine formula)
 */
function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371e3; // Earth's radius in meters
    const φ1 = (lat1 * Math.PI) / 180;
    const φ2 = (lat2 * Math.PI) / 180;
    const Δφ = ((lat2 - lat1) * Math.PI) / 180;
    const Δλ = ((lon2 - lon1) * Math.PI) / 180;

    const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
        Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

    return R * c;
}
