import React, { useEffect, useState } from 'react';
import { getFavorites, removeFavorite } from '../services/api';
import { isSafeUrl } from '../utils';

export default function Favorites({ restaurants, onSelectRestaurant }) {
    const [favorites, setFavorites] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [statusMessage, setStatusMessage] = useState(null);
    const [confirmingRemove, setConfirmingRemove] = useState(null);

    useEffect(() => {
        loadFavorites();
    }, []);

    const loadFavorites = async () => {
        try {
            const favs = await getFavorites();
            setFavorites(favs); // List of { restaurant_id, ... }
        } catch (err) {
            console.error('Failed to load favorites', err);
            setError('Failed to load favorites. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handleRemove = async (e, restaurantId) => {
        e.stopPropagation();
        if (confirmingRemove !== restaurantId) {
            setConfirmingRemove(restaurantId);
            return;
        }
        setConfirmingRemove(null);
        try {
            await removeFavorite(restaurantId);
            setFavorites(prev => prev.filter(f => f.restaurant_id !== restaurantId));
        } catch (err) {
            setStatusMessage({ type: 'error', text: 'Failed to remove favorite' });
            console.error('Failed to remove favorite', err);
        }
    };

    // Map favorites to full restaurant objects
    const favoriteRestaurants = favorites.map(f => {
        return restaurants.find(r => r.restaurant_id === f.restaurant_id);
    }).filter(Boolean);

    if (loading) return <div className="p-4">Loading favorites...</div>;

    if (error) {
        return (
            <div className="empty-state">
                <h3>Error</h3>
                <p>{error}</p>
                <button className="btn btn-primary" onClick={() => { setError(null); setLoading(true); loadFavorites(); }}>Retry</button>
            </div>
        );
    }

    if (favoriteRestaurants.length === 0) {
        return (
            <div className="empty-state">
                <h3>No Favorites Yet</h3>
                <p>Mark restaurants as favorites to see them here.</p>
            </div>
        );
    }

    return (
        <div className="favorites-grid p-4">
            <h2>Your Favorites</h2>
            {statusMessage && (
                <div className={`status-message ${statusMessage.type}`} style={{ padding: '8px 12px', marginBottom: 12, borderRadius: 6, background: statusMessage.type === 'error' ? '#fce4ec' : '#e8f5e9', color: statusMessage.type === 'error' ? '#c62828' : '#2e7d32' }}>
                    {statusMessage.text}
                    <button onClick={() => setStatusMessage(null)} style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer' }}>✕</button>
                </div>
            )}
            <div className="grid">
                {favoriteRestaurants.map(restaurant => (
                    <div
                        key={restaurant.restaurant_id}
                        className="restaurant-card"
                        onClick={() => onSelectRestaurant(restaurant.restaurant_id)}
                    >
                        <div className="card-image" style={{ backgroundImage: `url(${isSafeUrl(restaurant.image_url) ? restaurant.image_url : '/logo_icon_stylized.png'})` }}>
                            <span className="card-emoji">{restaurant.emoji}</span>
                        </div>
                        <div className="card-content">
                            <h3>{restaurant.name}</h3>
                            <p>{restaurant.cuisine} • {restaurant.rating} ★</p>
                            {confirmingRemove === restaurant.restaurant_id ? (
                                <span style={{ display: 'inline-flex', gap: '0.5rem', alignItems: 'center' }}>
                                    <button
                                        className="btn-icon remove-fav"
                                        onClick={(e) => handleRemove(e, restaurant.restaurant_id)}
                                        title="Confirm remove"
                                        style={{ color: '#ef4444', fontWeight: 600, fontSize: '0.85rem' }}
                                    >
                                        Confirm?
                                    </button>
                                    <button
                                        className="btn-icon"
                                        onClick={(e) => { e.stopPropagation(); setConfirmingRemove(null); }}
                                        title="Cancel"
                                        style={{ fontSize: '0.85rem' }}
                                    >
                                        ✕
                                    </button>
                                </span>
                            ) : (
                                <button
                                    className="btn-icon remove-fav"
                                    onClick={(e) => handleRemove(e, restaurant.restaurant_id)}
                                    title="Remove from favorites"
                                >
                                    💔
                                </button>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
