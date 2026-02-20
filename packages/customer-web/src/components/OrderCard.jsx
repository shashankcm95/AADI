/**
 * Single order card with status badge, vicinity, cancel and refresh actions.
 */

const STATUS_CONFIG = {
    'PENDING_NOT_SENT': { label: '⏳ Confirmed', color: '#f59e0b', canVicinity: true, canCancel: true },
    'WAITING_FOR_CAPACITY': { label: '⏰ Waiting', color: '#f59e0b', canVicinity: true, canCancel: true },
    'SENT_TO_DESTINATION': { label: '📨 Sent', color: '#3b82f6' },
    'IN_PROGRESS': { label: '👨‍🍳 Cooking', color: '#8b5cf6' },
    'READY': { label: '✅ Ready!', color: '#22c55e' },
    'FULFILLING': { label: '🍽️ Serving', color: '#10b981' },
    'COMPLETED': { label: '🎉 Done', color: '#6b7280' },
    'CANCELED': { label: '❌ Canceled', color: '#ef4444' },
    'EXPIRED': { label: '⏰ Expired', color: '#ef4444' },
}

export default function OrderCard({ order, onVicinity, onCancel, onRefresh }) {
    const config = STATUS_CONFIG[order.status] || { label: order.status, color: '#6b7280' }

    return (
        <div className="my-order-card organic-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <span className="order-id" style={{ color: 'var(--text-muted)' }}>#{order.order_id.slice(-8)}</span>
                <span className="order-status" style={{ backgroundColor: config.color, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
                    {config.label}
                </span>
            </div>
            <div className="order-actions">
                {config.canVicinity && (
                    <button onClick={() => onVicinity(order.order_id)} className="btn btn-vicinity" style={{ borderRadius: '20px' }}>
                        📍 I'm Here
                    </button>
                )}
                {config.canCancel && (
                    <button onClick={() => onCancel(order.order_id)} className="btn btn-cancel" style={{ borderRadius: '20px' }}>
                        ✕ Cancel
                    </button>
                )}
                <button onClick={() => onRefresh(order.order_id)} className="btn btn-small">
                    🔄
                </button>
            </div>
        </div>
    )
}
