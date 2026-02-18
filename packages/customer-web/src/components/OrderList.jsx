import OrderCard from './OrderCard'

/**
 * List of customer's orders with actions.
 */
export default function OrderList({ orders, onVicinity, onCancel, onRefresh }) {
    if (orders.length === 0) return null

    return (
        <section className="orders-section" style={{ marginTop: '3rem' }}>
            <h2>📋 My Orders</h2>
            <div className="my-orders-list">
                {orders.map(order => (
                    <OrderCard
                        key={order.order_id}
                        order={order}
                        onVicinity={onVicinity}
                        onCancel={onCancel}
                        onRefresh={onRefresh}
                    />
                ))}
            </div>
        </section>
    )
}
