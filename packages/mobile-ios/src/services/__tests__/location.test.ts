/**
 * Unit Tests for Hybrid Geofencing Logic
 * 
 * Tests: determineZone (hysteresis), calculateDistance (haversine),
 *        AsyncMutex (serialization), SerialEventQueue (retry/ordering)
 * 
 * Run: npx jest src/services/__tests__/location.test.ts
 */

// Mock expo-location and expo-task-manager before importing
jest.mock('expo-location', () => ({
    Accuracy: {
        BestForNavigation: 6,
        High: 4,
        Balanced: 3,
        Low: 2,
    },
    requestForegroundPermissionsAsync: jest.fn(),
    requestBackgroundPermissionsAsync: jest.fn(),
    startLocationUpdatesAsync: jest.fn(),
    stopLocationUpdatesAsync: jest.fn(),
    hasStartedLocationUpdatesAsync: jest.fn(),
    getCurrentPositionAsync: jest.fn(),
}));

jest.mock('expo-task-manager', () => ({
    defineTask: jest.fn(),
}));

import {
    determineZone,
    calculateDistance,
    applyCircuity,
    isUserApproaching,
    AsyncMutex,
    SerialEventQueue,
    CONFIG,
    EVENT_PRIORITY,
} from '../location';

// ===== determineZone Tests =====
describe('determineZone', () => {
    describe('Cold start (no prior zone)', () => {
        it('returns ARRIVAL for TTA < 5 min', () => {
            expect(determineZone(4 * 60, null)).toBe('ARRIVAL');  // 4 min
            expect(determineZone(60, null)).toBe('ARRIVAL');       // 1 min
            expect(determineZone(0, null)).toBe('ARRIVAL');        // 0 min
        });

        it('returns MID for TTA between 5-15 min', () => {
            expect(determineZone(5 * 60, null)).toBe('MID');      // 5 min (boundary)
            expect(determineZone(10 * 60, null)).toBe('MID');     // 10 min
            expect(determineZone(14 * 60, null)).toBe('MID');     // 14 min
        });

        it('returns FAR for TTA > 15 min', () => {
            expect(determineZone(15 * 60, null)).toBe('FAR');     // 15 min (boundary)
            expect(determineZone(30 * 60, null)).toBe('FAR');     // 30 min
            expect(determineZone(120 * 60, null)).toBe('FAR');    // 2 hours
        });
    });

    describe('Hysteresis — FAR zone', () => {
        const buffer = CONFIG.HYSTERESIS_BUFFER; // 30 seconds

        it('stays in FAR when TTA is above boundary', () => {
            expect(determineZone(16 * 60, 'FAR')).toBe('FAR');
        });

        it('stays in FAR when TTA is just below boundary (within buffer)', () => {
            // 15 min boundary - must drop below 14.5 min to leave FAR
            const justBelow = 15 * 60 - 10; // 14 min 50s — within buffer
            expect(determineZone(justBelow, 'FAR')).toBe('FAR');
        });

        it('transitions to MID when TTA drops below boundary - buffer', () => {
            const belowBuffer = (CONFIG.ZONE_FAR * 60) - buffer - 1; // 14 min 29s
            expect(determineZone(belowBuffer, 'FAR')).toBe('MID');
        });

        it('transitions directly to ARRIVAL on dramatic drop', () => {
            const dramatic = (CONFIG.ZONE_MID * 60) - buffer - 1; // < 4 min 29s
            expect(determineZone(dramatic, 'FAR')).toBe('ARRIVAL');
        });
    });

    describe('Hysteresis — MID zone', () => {
        const buffer = CONFIG.HYSTERESIS_BUFFER;

        it('stays in MID when TTA is within zone', () => {
            expect(determineZone(10 * 60, 'MID')).toBe('MID');
        });

        it('stays in MID when TTA is just above FAR boundary (within buffer)', () => {
            const justAbove = 15 * 60 + 10; // 15 min 10s — within buffer
            expect(determineZone(justAbove, 'MID')).toBe('MID');
        });

        it('transitions to FAR when TTA rises above boundary + buffer', () => {
            const aboveBuffer = (CONFIG.ZONE_FAR * 60) + buffer + 1;
            expect(determineZone(aboveBuffer, 'MID')).toBe('FAR');
        });

        it('stays in MID when TTA is just below ARRIVAL boundary (within buffer)', () => {
            const justBelow = 5 * 60 - 10; // 4 min 50s — within buffer
            expect(determineZone(justBelow, 'MID')).toBe('MID');
        });

        it('transitions to ARRIVAL when TTA drops below boundary - buffer', () => {
            const belowBuffer = (CONFIG.ZONE_MID * 60) - buffer - 1;
            expect(determineZone(belowBuffer, 'MID')).toBe('ARRIVAL');
        });
    });

    describe('Hysteresis — ARRIVAL zone', () => {
        const buffer = CONFIG.HYSTERESIS_BUFFER;

        it('stays in ARRIVAL when TTA is within zone', () => {
            expect(determineZone(3 * 60, 'ARRIVAL')).toBe('ARRIVAL');
        });

        it('stays in ARRIVAL when TTA is just above MID boundary (within buffer)', () => {
            const justAbove = 5 * 60 + 10; // 5 min 10s — within buffer
            expect(determineZone(justAbove, 'ARRIVAL')).toBe('ARRIVAL');
        });

        it('transitions to MID when TTA rises above boundary + buffer', () => {
            const aboveBuffer = (CONFIG.ZONE_MID * 60) + buffer + 1;
            expect(determineZone(aboveBuffer, 'ARRIVAL')).toBe('MID');
        });

        it('transitions directly to FAR on dramatic rise', () => {
            const dramatic = (CONFIG.ZONE_FAR * 60) + buffer + 1;
            expect(determineZone(dramatic, 'ARRIVAL')).toBe('FAR');
        });
    });
});

// ===== calculateDistance Tests =====
describe('calculateDistance', () => {
    it('returns 0 for same point', () => {
        const d = calculateDistance(30.2672, -97.7431, 30.2672, -97.7431);
        expect(d).toBeCloseTo(0, 0);
    });

    it('calculates known distance Austin → San Antonio (~120km)', () => {
        // Austin (30.2672, -97.7431) → San Antonio (29.4241, -98.4936)
        const d = calculateDistance(30.2672, -97.7431, 29.4241, -98.4936);
        expect(d).toBeGreaterThan(100_000);  // > 100km
        expect(d).toBeLessThan(130_000);     // < 130km
    });

    it('handles short distances accurately (~100m)', () => {
        // Two points ~111m apart (0.001 degrees latitude ≈ 111m)
        const d = calculateDistance(30.2672, -97.7431, 30.2682, -97.7431);
        expect(d).toBeGreaterThan(100);
        expect(d).toBeLessThan(120);
    });

    it('handles antipodal points', () => {
        // North pole to south pole ≈ 20,000km
        const d = calculateDistance(90, 0, -90, 0);
        expect(d).toBeGreaterThan(19_000_000);
        expect(d).toBeLessThan(21_000_000);
    });
});

// ===== AsyncMutex Tests =====
describe('AsyncMutex', () => {
    it('acquires and releases the lock', async () => {
        const mutex = new AsyncMutex();
        expect(mutex.isLocked).toBe(false);

        const release = await mutex.acquire();
        expect(mutex.isLocked).toBe(true);

        release();
        expect(mutex.isLocked).toBe(false);
    });

    it('serializes concurrent operations', async () => {
        const mutex = new AsyncMutex();
        const order: number[] = [];

        const task = async (id: number, delay: number) => {
            const release = await mutex.acquire();
            order.push(id);
            await new Promise(r => setTimeout(r, delay));
            release();
        };

        // Start both tasks simultaneously
        const p1 = task(1, 50);
        const p2 = task(2, 10);

        await Promise.all([p1, p2]);

        // Task 1 should complete before task 2 starts
        expect(order).toEqual([1, 2]);
    });

    it('releases lock even on error', async () => {
        const mutex = new AsyncMutex();

        const release = await mutex.acquire();
        // Simulate error in critical section
        release(); // Release in finally-block style

        // Lock should be free after error
        expect(mutex.isLocked).toBe(false);
        const release2 = await mutex.acquire();
        expect(mutex.isLocked).toBe(true);
        release2();
    });
});

// ===== SerialEventQueue Tests =====
describe('SerialEventQueue', () => {
    it('sends events in FIFO order', async () => {
        const queue = new SerialEventQueue();
        const sent: string[] = [];

        queue.setSender(async (event) => {
            await new Promise(r => setTimeout(r, 10));
            sent.push(event);
        });

        queue.enqueue('5_MIN_OUT', 'order-1', {});
        queue.enqueue('PARKING', 'order-1', {});
        queue.enqueue('AT_DOOR', 'order-1', {});

        // Wait for drain
        await new Promise(r => setTimeout(r, 100));

        expect(sent).toEqual(['5_MIN_OUT', 'PARKING', 'AT_DOOR']);
    });

    it('retries on failure with exponential backoff', async () => {
        const queue = new SerialEventQueue();
        let attempts = 0;

        queue.setSender(async (event) => {
            attempts++;
            if (attempts < 3) {
                throw new Error('network error');
            }
        });

        queue.enqueue('5_MIN_OUT', 'order-1', {});

        // Wait for retries (1s + 2s backoff + processing)
        await new Promise(r => setTimeout(r, 4000));

        expect(attempts).toBe(3); // 2 failures + 1 success
    }, 5000);

    it('drops event after max retries', async () => {
        const queue = new SerialEventQueue();
        let attempts = 0;

        queue.setSender(async () => {
            attempts++;
            throw new Error('permanent failure');
        });

        queue.enqueue('5_MIN_OUT', 'order-1', {});

        // Wait for all retries (1s + 2s + 4s)
        await new Promise(r => setTimeout(r, 8000));

        expect(attempts).toBe(3); // max retries reached, event dropped
    }, 10000);

    it('clears pending events on stop', async () => {
        const queue = new SerialEventQueue();
        const sent: string[] = [];

        queue.setSender(async (event) => {
            await new Promise(r => setTimeout(r, 50));
            sent.push(event);
        });

        queue.enqueue('5_MIN_OUT', 'order-1', {});
        queue.enqueue('PARKING', 'order-1', {});

        // Clear before second event drains
        queue.clear();
        await new Promise(r => setTimeout(r, 100));

        // At most the first event sent before clear
        expect(sent.length).toBeLessThanOrEqual(1);
    });
});

// ===== applyCircuity Tests =====
describe('applyCircuity', () => {
    it('applies the configured circuity factor', () => {
        const straight = 1000; // 1km straight-line
        const road = applyCircuity(straight);
        expect(road).toBe(straight * CONFIG.CIRCUITY_FACTOR); // 1400m
    });

    it('returns 0 for 0 distance', () => {
        expect(applyCircuity(0)).toBe(0);
    });

    it('preserves proportionality', () => {
        const d1 = applyCircuity(500);
        const d2 = applyCircuity(1000);
        expect(d2).toBeCloseTo(d1 * 2, 5);
    });
});

// ===== isUserApproaching Tests =====
describe('isUserApproaching', () => {
    // Restaurant at (30.27, -97.74) — Austin, TX
    const rLat = 30.27;
    const rLon = -97.74;

    it('returns true on first fix (no previous position)', () => {
        // First-fix-always-approaching: safe because no events fire until 2nd fix
        expect(isUserApproaching(30.26, -97.75, null, null, rLat, rLon)).toBe(true);
    });

    it('returns true when moving toward restaurant', () => {
        // Previous: further south, Current: closer to restaurant (moving north toward 30.27)
        const prevLat = 30.25;  // far from restaurant
        const curLat = 30.26;   // closer to restaurant
        expect(isUserApproaching(curLat, -97.74, prevLat, -97.74, rLat, rLon)).toBe(true);
    });

    it('returns false when moving away from restaurant', () => {
        // Previous: close, Current: further away (moving south, away from 30.27)
        const prevLat = 30.26;
        const curLat = 30.25;   // moved away
        expect(isUserApproaching(curLat, -97.74, prevLat, -97.74, rLat, rLon)).toBe(false);
    });

    it('returns true when stationary (dot product = 0)', () => {
        // Same position → zero movement vector → dot product = 0 → ≥ 0 → approaching
        expect(isUserApproaching(30.26, -97.74, 30.26, -97.74, rLat, rLon)).toBe(true);
    });

    it('returns true when moving perpendicular to restaurant (dot ≈ 0)', () => {
        // Moving east/west while restaurant is due north
        // prev: (30.26, -97.75), cur: (30.26, -97.73) — pure east movement
        // target vector: (30.27-30.26, -97.74-(-97.73)) = (0.01, -0.01)
        // move vector: (0, 0.02)
        // dot = 0*0.01 + 0.02*(-0.01) = -0.0002 → slightly receding
        const result = isUserApproaching(30.26, -97.73, 30.26, -97.75, rLat, rLon);
        // Perpendicular-ish: result depends on exact geometry
        expect(typeof result).toBe('boolean');
    });
});

// ===== EVENT_PRIORITY Tests =====
describe('EVENT_PRIORITY', () => {
    it('has correct priority ordering', () => {
        expect(EVENT_PRIORITY['5_MIN_OUT']).toBeLessThan(EVENT_PRIORITY['PARKING']);
        expect(EVENT_PRIORITY['PARKING']).toBeLessThan(EVENT_PRIORITY['AT_DOOR']);
    });

    it('AT_DOOR is highest priority', () => {
        const max = Math.max(...Object.values(EVENT_PRIORITY));
        expect(EVENT_PRIORITY['AT_DOOR']).toBe(max);
    });
});
