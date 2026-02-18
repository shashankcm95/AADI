import { CONFIG } from '../config';
import { Zone } from '../types';

/**
 * Calculate distance between two points (Haversine formula)
 */
export function calculateDistance(lat1: number, lon1: number, lat2: number, lon2: number): number {
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

/**
 * Apply circuity factor to convert straight-line distance to approximate road distance.
 * Road networks are typically ~1.4x the Haversine distance (Ballou et al.).
 */
export function applyCircuity(straightLineMeters: number): number {
    return straightLineMeters * CONFIG.CIRCUITY_FACTOR;
}

/**
 * Determine if the user is approaching the restaurant using a dot product of:
 *   movement vector (previous → current position) · target vector (current → restaurant)
 * 
 * Returns true (approaching) if:
 *   - No previous position exists (first GPS fix). This is safe because the first fix
 *     only sets the initial zone — no events fire until the second fix confirms direction.
 *     Worst case: one extra poll at the "wrong" interval, corrected 5s later.
 *   - The dot product is >= 0 (vectors point in the same general direction)
 */
export function isUserApproaching(
    currentLat: number, currentLon: number,
    prevLat: number | null, prevLon: number | null,
    restaurantLat: number, restaurantLon: number,
): boolean {
    // First fix: no prior position, assume approaching (see docstring for rationale)
    if (prevLat === null || prevLon === null) return true;

    // Movement vector (user's travel direction)
    const dxMove = currentLat - prevLat;
    const dyMove = currentLon - prevLon;
    // Target vector (direction to restaurant from current position)
    const dxTarget = restaurantLat - currentLat;
    const dyTarget = restaurantLon - currentLon;
    // Dot product: positive = approaching, negative = receding
    const dot = (dxMove * dxTarget) + (dyMove * dyTarget);
    return dot >= 0;
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
export function determineZone(ttaSeconds: number, currentZone: Zone | null): Zone {
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
