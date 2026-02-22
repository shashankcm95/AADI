/**
 * Menu grid — shows menu items for the selected restaurant.
 * Each item has an "Add" button that calls onAddToCart.
 */
export default function MenuGrid({ menu, onAddToCart }) {
    if (!menu) return null
    const items = menu.items || []

    const groups = []
    const byCategory = new Map()
    for (const item of items) {
        const categoryName = String(item.category || '').trim() || 'Other'
        if (!byCategory.has(categoryName)) {
            byCategory.set(categoryName, [])
            groups.push([categoryName, byCategory.get(categoryName)])
        }
        byCategory.get(categoryName).push(item)
    }

    return (
        <section className="menu-section">
            <h2>🍽️ Menu</h2>
            {items.length > 0 ? (
                <div className="menu-categories">
                    {groups.map(([categoryName, categoryItems]) => (
                        <div key={categoryName} className="menu-category-block">
                            <h3 className="menu-category-title">{categoryName}</h3>
                            <div className="menu-grid">
                                {categoryItems.map((item, idx) => (
                                    <div key={`${categoryName}-${item.id || idx}`} className="menu-item organic-card">
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
                        </div>
                    ))}
                </div>
            ) : (
                <p className="empty-menu">No menu items available for this restaurant.</p>
            )}
        </section>
    )
}
