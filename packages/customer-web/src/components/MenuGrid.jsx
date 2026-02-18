/**
 * Menu grid — shows menu items for the selected restaurant.
 * Each item has an "Add" button that calls onAddToCart.
 */
export default function MenuGrid({ menu, onAddToCart }) {
    if (!menu) return null

    return (
        <section className="menu-section">
            <h2>🍽️ Menu</h2>
            {menu.items?.length > 0 ? (
                <div className="menu-grid">
                    {menu.items.map((item, idx) => (
                        <div key={item.id || idx} className="menu-item organic-card">
                            <div className="item-info">
                                <span className="item-name">{item.name || item.id}</span>
                                <span className="item-price">${((item.price_cents || 0) / 100).toFixed(2)}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                                <button onClick={() => onAddToCart(item)} className="btn btn-add">+ Add</button>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <p className="empty-menu">No menu items available for this restaurant.</p>
            )}
        </section>
    )
}
