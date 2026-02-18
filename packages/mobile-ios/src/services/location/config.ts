export const CONFIG = {
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

    // Circuity Factor: road distance ≈ 1.4x straight-line distance
    // Based on transportation research (Ballou et al., circuity ratio for US road networks)
    // This corrects the Haversine straight-line distance to approximate actual driving distance.
    CIRCUITY_FACTOR: 1.4,

    // Debounce
    EVENT_DEBOUNCE_MS: 10000, // Don't re-send the same event within 10s
};

// Geofence radii for events (in meters)
export const GEOFENCE_RADII = {
    FIVE_MIN_OUT: 1500, // ~5 min driving at city speeds (approx)
    PARKING: 150,       // Parking lot detection
    AT_DOOR: 30,        // Hand-off proximity
};

// Geofence event priority (higher index = higher priority)
export const EVENT_PRIORITY: Record<string, number> = {
    '5_MIN_OUT': 1,
    'PARKING': 2,
    'AT_DOOR': 3,
};
