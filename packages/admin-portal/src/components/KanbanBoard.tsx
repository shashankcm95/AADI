

export interface OrderItem {
    name?: string;
    id?: string;
    qty: number;
}

export interface Order {
    order_id: string;
    customer_name?: string;
    items?: OrderItem[];
    status: string;
}

interface KanbanCardProps {
    order: Order;
    onStatusUpdate: (orderId: string, newStatus: string) => void;
    nextStatus?: string;
}

export function KanbanCard({ order, onStatusUpdate, nextStatus }: KanbanCardProps) {
    return (
        <div className="kanban-card">
            <div className="kanban-card-header">
                <span className="customer">{order.customer_name || 'Guest'}</span>
                <span className="order-num">#{order.order_id?.slice(-4) || '??'}</span>
            </div>
            <div className="kanban-card-items">
                {order.items?.map((item, i) => (
                    <div key={i} className="item">{item.name || item.id} x{item.qty}</div>
                ))}
            </div>
            {nextStatus && (
                <button
                    className="kanban-action"
                    onClick={() => onStatusUpdate(order.order_id, nextStatus)}
                >
                    Move →
                </button>
            )}
        </div>
    )
}

interface KanbanBoardProps {
    orders: Order[];
    handleStatusUpdate: (orderId: string, newStatus: string) => void;
}

export default function KanbanBoard({ orders, handleStatusUpdate }: KanbanBoardProps) {
    return (
        <section className="kds-board">
            <h2>🍳 Kitchen Display System</h2>
            <div className="kanban-container">
                {/* Prep Lane */}
                <div className="kanban-lane lane-prep">
                    <h3>🔥 Prep</h3>
                    <div className="lane-cards">
                        {orders.filter(o => o.status === 'SENT_TO_DESTINATION').map(order => (
                            <KanbanCard key={order.order_id} order={order} onStatusUpdate={handleStatusUpdate} nextStatus="IN_PROGRESS" />
                        ))}
                    </div>
                </div>

                {/* Cook Lane */}
                <div className="kanban-lane lane-cook">
                    <h3>👨‍🍳 Cook</h3>
                    <div className="lane-cards">
                        {orders.filter(o => o.status === 'IN_PROGRESS').map(order => (
                            <KanbanCard key={order.order_id} order={order} onStatusUpdate={handleStatusUpdate} nextStatus="READY" />
                        ))}
                    </div>
                </div>

                {/* Plate Lane */}
                <div className="kanban-lane lane-plate">
                    <h3>🍽️ Plate</h3>
                    <div className="lane-cards">
                        {orders.filter(o => o.status === 'READY').map(order => (
                            <KanbanCard key={order.order_id} order={order} onStatusUpdate={handleStatusUpdate} nextStatus="FULFILLING" />
                        ))}
                    </div>
                </div>

                {/* Serve Lane */}
                <div className="kanban-lane lane-serve">
                    <h3>✅ Serve</h3>
                    <div className="lane-cards">
                        {orders.filter(o => o.status === 'FULFILLING').map(order => (
                            <KanbanCard key={order.order_id} order={order} onStatusUpdate={handleStatusUpdate} nextStatus="COMPLETED" />
                        ))}
                    </div>
                </div>
            </div>
        </section>
    )
}
