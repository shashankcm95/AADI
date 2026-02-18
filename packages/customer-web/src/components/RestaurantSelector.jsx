import './RestaurantSelector.css'

/**
 * Restaurant selector dropdown.
 * Shows available restaurants and lets the customer pick one.
 */
export default function RestaurantSelector({ restaurants, selectedId, onSelect }) {
    return (
        <section className="restaurant-section">
            <h2>📍 Select Restaurant</h2>
            <select
                value={selectedId || ''}
                onChange={(e) => onSelect(e.target.value)}
                className="restaurant-select"
            >
                <option value="">Choose a restaurant...</option>
                {restaurants.map(r => (
                    <option key={r.restaurant_id} value={r.restaurant_id}>
                        {r.name || r.restaurant_id}
                    </option>
                ))}
            </select>
        </section>
    )
}
