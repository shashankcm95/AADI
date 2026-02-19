import React, { useEffect, useState } from 'react';
import { getFavorites, removeFavorite } from '../services/api';

export default function Favorites({ restaurants, onSelectRestaurant }) {
    const [favorites, setFavorites] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadFavorites();
    }, []);

    const loadFavorites = async () => {
        try {
            const favs = await getFavorites();
            setFavorites(favs); // List of { restaurant_id, ... }
        } catch (err) {
            console.error('Failed to load favorites', err);
        } finally {
            setLoading(false);
        }
    };

    const handleRemove = async (e, restaurantId) => {
        e.stopPropagation();
        if (!window.confirm('Remove from favorites?')) return;
        try {
            await removeFavorite(restaurantId);
            setFavorites(prev => prev.filter(f => f.restaurant_id !== restaurantId));
        } catch (err) {
            alert('Failed to remove favorite');
            console.error('Failed to remove favorite', err);
        }
    };

    // Map favorites to full restaurant objects
    const favoriteRestaurants = favorites.map(f => {
        return restaurants.find(r => r.restaurant_id === f.restaurant_id);
    }).filter(Boolean);

    if (loading) return <div className="p-4">Loading favorites...</div>;

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
            <div className="grid">
                {favoriteRestaurants.map(restaurant => (
                    <div
                        key={restaurant.restaurant_id}
                        className="restaurant-card"
                        onClick={() => onSelectRestaurant(restaurant.restaurant_id)}
                    >
                        <div className="card-image" style={{ backgroundImage: `url(${restaurant.image_url || '/placeholder_food.jpg'})` }}>
                            <span className="card-emoji">{restaurant.emoji}</span>
                        </div>
                        <div className="card-content">
                            <h3>{restaurant.name}</h3>
                            <p>{restaurant.cuisine} • {restaurant.rating} ★</p>
                            <button
                                className="btn-icon remove-fav"
                                onClick={(e) => handleRemove(e, restaurant.restaurant_id)}
                                title="Remove from favorites"
                            >
                                💔
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
