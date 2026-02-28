/**
 * Shopping cart with item list, quantities, total, and place order button.
 */
export default function Cart({ cart, onRemove, onPlaceOrder }) {
    if (cart.length === 0) return null

    // Display-only total for cart UI. The authoritative total_cents is computed
    // server-side in create_session_model(). This value is never sent to the backend.
    const total = cart.reduce((sum, c) => sum + (c.price_cents || 0) * c.qty, 0)

    return (
        <section className="cart-section" style={{ marginTop: '3rem' }}>
            <h2>🛒 Your Cart</h2>
            <div className="cart-items organic-card">
                {cart.map(item => (
                    <div key={item.id} className="cart-item" style={{ borderBottom: '1px solid #eee', paddingBottom: '0.5rem', marginBottom: '0.5rem' }}>
                        <span>{item.name} <span style={{ color: 'var(--accent-gold)', fontWeight: 'bold' }}>x{item.qty}</span></span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                            <span>${((item.price_cents || 0) * item.qty / 100).toFixed(2)}</span>
                            <button onClick={() => onRemove(item.id)} className="btn btn-remove">✕</button>
                        </div>
                    </div>
                ))}
                <div className="cart-total" style={{ marginTop: '1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '2px solid var(--accent-gold)', paddingTop: '1rem' }}>
                    <strong style={{ fontSize: '1.2rem' }}>Total: ${(total / 100).toFixed(2)}</strong>
                    <button onClick={onPlaceOrder} className="btn btn-primary">
                        🚀 Place Order
                    </button>
                </div>
            </div>
        </section>
    )
}
