/**
 * OrderTimeline — Real-time order list grouped by status phase.
 *
 * Replaces the Kanban board. Shows orders in 4 sections:
 *   ● Incoming — SENT_TO_DESTINATION (new orders needing acknowledgement)
 *   ● Active  — IN_PROGRESS, READY (being prepared)
 *   ● Pickup  — FULFILLING (customer is here)
 *   ● Done    — COMPLETED (collapsed, last 10)
 *
 * No manual "Move →" buttons. The only action: "Acknowledge" on incoming.
 */

export interface OrderItem {
    name?: string;
    id?: string;
    qty: number;
    price_cents?: number;
}

export interface Order {
    order_id: string;
    customer_name?: string;
    customer_id?: string;
    items?: OrderItem[];
    resources?: OrderItem[];
    status: string;
    created_at?: number;
    updated_at?: number;
}

/* ── Status badge config ──────────────────────────────────────────── */

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
    PENDING_NOT_SENT: { label: '⏳ Pending', className: 'badge-pending' },
    WAITING: { label: '⏰ Waiting', className: 'badge-waiting' },
    SENT_TO_DESTINATION: { label: '📨 New', className: 'badge-new' },
    IN_PROGRESS: { label: '👨‍🍳 Cooking', className: 'badge-cooking' },
    READY: { label: '✅ Ready', className: 'badge-ready' },
    FULFILLING: { label: '🍽️ Serving', className: 'badge-serving' },
    COMPLETED: { label: '🎉 Done', className: 'badge-done' },
    CANCELED: { label: '❌ Canceled', className: 'badge-canceled' },
} as const;

/* ── Helpers ──────────────────────────────────────────────────────── */

function timeAgo(epoch?: number): string {
    if (!epoch) return '';
    const diff = Math.floor(Date.now() / 1000 - epoch);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
}

/* ── Order card ───────────────────────────────────────────────────── */

interface OrderCardProps {
    order: Order;
    showAck: boolean;
    onAcknowledge?: (orderId: string) => void;
}

function TimelineCard({ order, showAck, onAcknowledge }: OrderCardProps) {
    const cfg = STATUS_CONFIG[order.status] || { label: order.status, className: 'badge-default' };
    const items = order.items || order.resources || [];

    return (
        <div className="timeline-card">
            <div className="timeline-card-head">
                <div className="timeline-card-meta">
                    <span className="timeline-customer">{order.customer_name || 'Guest'}</span>
                    <span className="timeline-order-num">#{order.order_id?.slice(-6)}</span>
                </div>
                <div className="timeline-card-right">
                    <span className={`timeline-badge ${cfg.className}`}>{cfg.label}</span>
                    <span className="timeline-time">{timeAgo(order.created_at || order.updated_at)}</span>
                </div>
            </div>

            <div className="timeline-items">
                {items.map((it, i) => (
                    <span key={i} className="timeline-item-chip">
                        {it.name || it.id} ×{it.qty}
                    </span>
                ))}
                {items.length === 0 && <span className="timeline-item-chip empty">No items</span>}
            </div>

            {showAck && onAcknowledge && (
                <button
                    className="btn-acknowledge"
                    onClick={() => onAcknowledge(order.order_id)}
                >
                    ✓ Acknowledge
                </button>
            )}
        </div>
    );
}

/* ── Skeleton loader ──────────────────────────────────────────────── */

function SkeletonCard() {
    return (
        <div className="timeline-card skeleton">
            <div className="skel-line skel-short" />
            <div className="skel-line skel-long" />
            <div className="skel-line skel-medium" />
        </div>
    );
}

/* ── Section with header + empty state ─────────────────────────── */

interface SectionProps {
    title: string;
    emoji: string;
    orders: Order[];
    showAck?: boolean;
    onAcknowledge?: (orderId: string) => void;
    loading?: boolean;
    emptyText: string;
    collapsed?: boolean;
    limit?: number;
}

function TimelineSection({
    title, emoji, orders, showAck = false, onAcknowledge,
    loading, emptyText, collapsed, limit,
}: SectionProps) {
    const display = limit ? orders.slice(0, limit) : orders;
    const hidden = limit && orders.length > limit ? orders.length - limit : 0;

    return (
        <div className={`timeline-section ${collapsed ? 'collapsed' : ''}`}>
            <div className="timeline-section-head">
                <span className="timeline-section-emoji">{emoji}</span>
                <h3>{title}</h3>
                <span className="timeline-section-count">{orders.length}</span>
            </div>

            <div className="timeline-section-body">
                {loading && orders.length === 0 && (
                    <>
                        <SkeletonCard />
                        <SkeletonCard />
                    </>
                )}

                {!loading && orders.length === 0 && (
                    <p className="timeline-empty">{emptyText}</p>
                )}

                {display.map(order => (
                    <TimelineCard
                        key={order.order_id}
                        order={order}
                        showAck={showAck}
                        onAcknowledge={onAcknowledge}
                    />
                ))}

                {hidden > 0 && (
                    <p className="timeline-more">+ {hidden} more completed orders</p>
                )}
            </div>
        </div>
    );
}

/* ── Main component ───────────────────────────────────────────────── */

interface OrderTimelineProps {
    orders: Order[];
    loading?: boolean;
    onAcknowledge?: (orderId: string) => void;
}

export default function OrderTimeline({ orders, loading, onAcknowledge }: OrderTimelineProps) {
    const incoming = orders.filter(o => o.status === 'SENT_TO_DESTINATION');
    const pending = orders.filter(o => o.status === 'PENDING_NOT_SENT' || o.status === 'WAITING');
    const active = orders.filter(o => o.status === 'IN_PROGRESS' || o.status === 'READY');
    const pickup = orders.filter(o => o.status === 'FULFILLING');
    const completed = orders.filter(o => o.status === 'COMPLETED');

    return (
        <div className="order-timeline">
            <TimelineSection
                title="Incoming"
                emoji="🔔"
                orders={incoming}
                showAck
                onAcknowledge={onAcknowledge}
                loading={loading}
                emptyText="No new orders right now"
            />

            <TimelineSection
                title="Pending"
                emoji="⏳"
                orders={pending}
                loading={loading}
                emptyText="No pending orders"
            />

            <TimelineSection
                title="Active"
                emoji="🔥"
                orders={active}
                loading={loading}
                emptyText="No orders in progress"
            />

            <TimelineSection
                title="Ready for Pickup"
                emoji="🍽️"
                orders={pickup}
                loading={loading}
                emptyText="No orders ready for pickup"
            />

            <TimelineSection
                title="Completed"
                emoji="✅"
                orders={completed}
                collapsed
                limit={10}
                loading={loading}
                emptyText="No completed orders yet"
            />
        </div>
    );
}
