export type Zone = 'FAR' | 'MID' | 'ARRIVAL';

export interface RestaurantLocation {
    latitude: number;
    longitude: number;
    restaurantId: string;
}

export interface TrackingState {
    lastLocationTs: number;
    lastReportedEvent: string; // The actual event name ('AT_DOOR', 'PARKING', etc.)
    lastReportedTta: number | null;
    lastReportTs: number;
    currentSpeed: number;       // m/s (smoothed)
    currentZone: Zone | null;   // Track zone for hysteresis & transition events
    isStarted: boolean;         // Guard against multiple startLocationTracking calls
    firedEvents: Set<string>;   // Events already fired this session (prevents cascade)
    highestFiredPriority: number; // Highest priority event that has fired
    lastConfiguredInterval: number; // Last polling interval set on the native API
    lastLat: number | null;     // Previous position for bearing calculation
    lastLon: number | null;     // Previous position for bearing calculation
}

export interface QueuedEvent {
    eventName: string;
    orderId: string;
    metadata: any;
    retries: number;
}
