import { QueuedEvent } from '../types';

/**
 * AsyncMutex: Ensures only one processLocationUpdate runs at a time.
 * If a GPS callback fires while the previous is still processing,
 * the new callback waits for the lock instead of racing on trackingState.
 */
export class AsyncMutex {
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
export class SerialEventQueue {
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
