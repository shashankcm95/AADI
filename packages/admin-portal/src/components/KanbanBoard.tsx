export interface OrderItem {
    name?: string;
    id?: string;
    qty?: number;
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

interface KanbanBoardProps {
    orders: Order[];
    loading?: boolean;
    onCompleteOrder: (order: Order) => void;
    orderActionState: Record<string, boolean>;
}

interface LaneConfig {
    key: string;
    title: string;
    emptyText: string;
    statuses: string[];
}

interface KanbanAction {
    label: string;
    kind: 'primary';
    onClick: () => void;
}

const LANE_CONFIGS: LaneConfig[] = [
    {
        key: 'pending',
        title: 'Pending',
        emptyText: 'No pending orders',
        statuses: ['PENDING_NOT_SENT', 'WAITING_FOR_CAPACITY'],
    },
    {
        key: 'incoming',
        title: 'Incoming',
        emptyText: 'No incoming orders',
        statuses: ['SENT_TO_DESTINATION'],
    },
    {
        key: 'active',
        title: 'Active',
        emptyText: 'No active orders',
        statuses: ['IN_PROGRESS', 'READY', 'FULFILLING'],
    },
    {
        key: 'completed',
        title: 'Completed',
        emptyText: 'No completed orders',
        statuses: ['COMPLETED'],
    },
]

const STATUS_LABELS: Record<string, string> = {
    PENDING_NOT_SENT: 'Pending',
    WAITING_FOR_CAPACITY: 'Waiting',
    SENT_TO_DESTINATION: 'Incoming',
    IN_PROGRESS: 'Cooking',
    READY: 'Ready',
    FULFILLING: 'Pickup',
    COMPLETED: 'Completed',
}

function timeAgo(epoch?: number): string {
    if (!epoch) return ''
    const diff = Math.floor(Date.now() / 1000 - epoch)
    if (diff < 60) return `${diff}s ago`
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    return `${Math.floor(diff / 3600)}h ago`
}

function getCardActions(
    order: Order,
    onCompleteOrder: (order: Order) => void,
): KanbanAction[] {
    if (['IN_PROGRESS', 'READY', 'FULFILLING'].includes(order.status)) {
        return [{
            label: 'Mark Complete',
            kind: 'primary',
            onClick: () => onCompleteOrder(order),
        }]
    }

    return []
}

function KanbanCard({
    order,
    orderActionState,
    onCompleteOrder,
}: {
    order: Order;
    orderActionState: Record<string, boolean>;
    onCompleteOrder: (order: Order) => void;
}) {
    const items = order.items && order.items.length > 0 ? order.items : (order.resources || [])
    const actions = getCardActions(order, onCompleteOrder)
    const isBusy = Boolean(orderActionState[order.order_id])
    const statusLabel = STATUS_LABELS[order.status] || order.status

    return (
        <article className="kanban-card">
            <div className="kanban-card-header">
                <div className="kanban-card-meta">
                    <span className="kanban-customer">{order.customer_name || 'Guest'}</span>
                    <span className="kanban-order-id">#{order.order_id.slice(-6)}</span>
                </div>
                <div className="kanban-card-right">
                    <span className="kanban-status-pill">{statusLabel}</span>
                    <span className="kanban-time">{timeAgo(order.updated_at || order.created_at)}</span>
                </div>
            </div>

            <div className="kanban-items">
                {items.length > 0 ? (
                    items.map((item, idx) => (
                        <div key={`${order.order_id}-${idx}`} className="kanban-item">
                            {item.name || item.id || 'Item'} x{item.qty || 1}
                        </div>
                    ))
                ) : (
                    <div className="kanban-item kanban-item-empty">No items</div>
                )}
            </div>

            {actions.length > 0 && (
                <div className="kanban-actions">
                    {actions.map((action, idx) => (
                        <button
                            key={`${order.order_id}-${idx}`}
                            type="button"
                            className={`kanban-action-btn ${action.kind}`}
                            disabled={isBusy}
                            onClick={action.onClick}
                        >
                            {isBusy ? 'Working...' : action.label}
                        </button>
                    ))}
                </div>
            )}
        </article>
    )
}

function KanbanLane({
    lane,
    laneOrders,
    loading,
    orderActionState,
    onCompleteOrder,
}: {
    lane: LaneConfig;
    laneOrders: Order[];
    loading: boolean;
    orderActionState: Record<string, boolean>;
    onCompleteOrder: (order: Order) => void;
}) {
    return (
        <section className="kanban-lane" data-lane={lane.key}>
            <header className="kanban-lane-header">
                <h3>{lane.title}</h3>
                <span className="kanban-lane-count">{laneOrders.length}</span>
            </header>

            <div className="kanban-lane-body">
                {loading && laneOrders.length === 0 && <p className="kanban-empty">Loading...</p>}
                {!loading && laneOrders.length === 0 && <p className="kanban-empty">{lane.emptyText}</p>}
                {laneOrders.map((order) => (
                    <KanbanCard
                        key={order.order_id}
                        order={order}
                        orderActionState={orderActionState}
                        onCompleteOrder={onCompleteOrder}
                    />
                ))}
            </div>
        </section>
    )
}

export default function KanbanBoard({
    orders,
    loading = false,
    onCompleteOrder,
    orderActionState,
}: KanbanBoardProps) {
    return (
        <div className="kanban-board">
            <div className="kanban-grid">
                {LANE_CONFIGS.map((lane) => {
                    const laneOrders = orders.filter((order) => lane.statuses.includes(order.status))
                    return (
                        <KanbanLane
                            key={lane.key}
                            lane={lane}
                            laneOrders={laneOrders}
                            loading={loading}
                            orderActionState={orderActionState}
                            onCompleteOrder={onCompleteOrder}
                        />
                    )
                })}
            </div>
        </div>
    )
}
