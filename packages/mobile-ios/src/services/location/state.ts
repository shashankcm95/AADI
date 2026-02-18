import { TrackingState } from './types';

export const INITIAL_STATE: TrackingState = {
    lastLocationTs: 0,
    lastReportedEvent: '',
    lastReportedTta: null,
    lastReportTs: 0,
    currentSpeed: 0,
    currentZone: null,
    isStarted: false,
    firedEvents: new Set(),
    highestFiredPriority: 0,
    lastConfiguredInterval: 0,
    lastLat: null,
    lastLon: null,
};

// Singleton state instance
let trackingState: TrackingState = { ...INITIAL_STATE };

export function getTrackingState(): TrackingState {
    return trackingState;
}

export function resetTrackingState(): void {
    trackingState = { ...INITIAL_STATE, firedEvents: new Set() };
}

// Allow direct mutation for performance/simplicity in the processor
// (Alternatively, we could use reducers, but this is a high-frequency loop)
export { trackingState };
