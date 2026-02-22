
import { useState, useEffect } from 'react'
import { API_BASE_URL } from '../aws-exports'
import RestaurantForm from './RestaurantForm'
import RestaurantImageManager from './RestaurantImageManager'

// Reuse RestaurantForm for "Adding" but for "Editing" we might need a modified version or just reuse inputs.
// Simpler to build a small EditModal inside here or refactor RestaurantForm to handle edits.
// For MVP speed, let's build a dedicated EditModal here.

interface AdminDashboardProps {
    signOut: () => void;
}

type ZoneKey = 'ZONE_1' | 'ZONE_2' | 'ZONE_3';
type ZoneDistances = Record<ZoneKey, number>;
type ZoneLabels = Record<ZoneKey, string>;
const DEFAULT_ZONE_DISTANCES: ZoneDistances = {
    ZONE_1: 1500,
    ZONE_2: 150,
    ZONE_3: 30,
}
const DEFAULT_ZONE_LABELS: ZoneLabels = {
    ZONE_1: 'Zone 1',
    ZONE_2: 'Zone 2',
    ZONE_3: 'Zone 3',
}

import { fetchAuthSession } from 'aws-amplify/auth'

export default function AdminDashboard({ signOut }: AdminDashboardProps) {
    const [restaurants, setRestaurants] = useState<any[]>([])
    const [loading, setLoading] = useState(true)
    const [showAddModal, setShowAddModal] = useState(false)
    const [editingRestaurant, setEditingRestaurant] = useState<any | null>(null)
    const [token, setToken] = useState<string | null>(null)
    const [zoneDistances, setZoneDistances] = useState<ZoneDistances>(DEFAULT_ZONE_DISTANCES)
    const [zoneLabels, setZoneLabels] = useState<ZoneLabels>(DEFAULT_ZONE_LABELS)
    const [globalSaving, setGlobalSaving] = useState(false)
    const [globalMessage, setGlobalMessage] = useState<string | null>(null)
    const [globalError, setGlobalError] = useState<string | null>(null)

    useEffect(() => {
        initializeDashboard()
    }, [])

    async function initializeDashboard() {
        try {
            const session = await fetchAuthSession()
            const idToken = session.tokens?.idToken?.toString()

            if (idToken) {
                setToken(idToken)
                await Promise.all([
                    fetchRestaurants(idToken),
                    fetchGlobalConfig(idToken),
                ])
            } else {
                console.error("No ID token found")
                setLoading(false)
            }
        } catch (err) {
            console.error("Failed to fetch auth session:", err)
            setLoading(false)
        }
    }

    async function fetchRestaurants(authToken: string) {
        try {

            const res = await fetch(`${API_BASE_URL}/v1/restaurants`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            })
            const data = await res.json()

            setRestaurants(data.restaurants || [])
        } catch (err) {
            console.error("API Error:", err)
        } finally {
            setLoading(false)
        }
    }

    async function fetchGlobalConfig(authToken: string) {
        try {
            const res = await fetch(`${API_BASE_URL}/v1/admin/global-config`, {
                headers: { 'Authorization': `Bearer ${authToken}` }
            })
            if (!res.ok) {
                return
            }
            const data = await res.json()
            setZoneDistances({
                ZONE_1: Number(data.zone_distances_m?.ZONE_1 ?? DEFAULT_ZONE_DISTANCES.ZONE_1),
                ZONE_2: Number(data.zone_distances_m?.ZONE_2 ?? DEFAULT_ZONE_DISTANCES.ZONE_2),
                ZONE_3: Number(data.zone_distances_m?.ZONE_3 ?? DEFAULT_ZONE_DISTANCES.ZONE_3),
            })
            setZoneLabels({
                ZONE_1: String(data.zone_labels?.ZONE_1 ?? DEFAULT_ZONE_LABELS.ZONE_1),
                ZONE_2: String(data.zone_labels?.ZONE_2 ?? DEFAULT_ZONE_LABELS.ZONE_2),
                ZONE_3: String(data.zone_labels?.ZONE_3 ?? DEFAULT_ZONE_LABELS.ZONE_3),
            })
        } catch (err) {
            console.error("Global config load error:", err)
        }
    }

    async function handleDelete(restaurantId: string) {
        if (!confirm("Are you sure? This will delete the restaurant and the associated admin user.")) return;

        try {
            const res = await fetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                setRestaurants(restaurants.filter(r => r.restaurant_id !== restaurantId))
            } else {
                alert("Failed to delete restaurant")
            }
        } catch (err) {
            console.error(err)
            alert("Error deleting restaurant")
        }
    }

    async function handleUpdate(updatedData: any) {
        if (!editingRestaurant) return;

        try {
            const res = await fetch(`${API_BASE_URL}/v1/restaurants/${editingRestaurant.restaurant_id}`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(updatedData)
            })

            if (res.ok) {
                setEditingRestaurant(null)
                if (token) fetchRestaurants(token) // Refresh list
            } else {
                alert("Failed to update restaurant")
            }
        } catch (err) {
            console.error(err)
            alert("Error updating restaurant")
        }
    }

    async function handleToggleStatus(restaurantId: string, newStatus: boolean) {
        const action = newStatus ? "activate" : "deactivate";
        if (!confirm(`Are you sure you want to ${action} this restaurant?`)) return;

        try {
            const res = await fetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ active: newStatus })
            })

            if (res.ok) {
                if (token) fetchRestaurants(token)
            } else {
                alert(`Failed to ${action} restaurant`)
            }
        } catch (err) {
            console.error(`${action} failed:`, err)
            alert(`Error ${action}ing restaurant`)
        }
    }

    function updateZoneDistance(zone: ZoneKey, rawValue: string) {
        const parsed = parseInt(rawValue, 10)
        setZoneDistances(prev => ({
            ...prev,
            [zone]: Number.isFinite(parsed) ? parsed : 0,
        }))
    }

    function updateZoneLabel(zone: ZoneKey, rawValue: string) {
        setZoneLabels(prev => ({
            ...prev,
            [zone]: rawValue,
        }))
    }

    async function saveGlobalZones() {
        if (!token) return

        setGlobalSaving(true)
        setGlobalMessage(null)
        setGlobalError(null)

        try {
            const res = await fetch(`${API_BASE_URL}/v1/admin/global-config`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    zone_distances_m: zoneDistances,
                    zone_labels: zoneLabels,
                }),
            })

            if (!res.ok) {
                const payload = await res.json().catch(() => ({}))
                setGlobalError(payload.error || 'Failed to save global zone settings')
                return
            }

            const payload = await res.json()
            setZoneDistances({
                ZONE_1: Number(payload.zone_distances_m?.ZONE_1 ?? zoneDistances.ZONE_1),
                ZONE_2: Number(payload.zone_distances_m?.ZONE_2 ?? zoneDistances.ZONE_2),
                ZONE_3: Number(payload.zone_distances_m?.ZONE_3 ?? zoneDistances.ZONE_3),
            })
            setZoneLabels({
                ZONE_1: String(payload.zone_labels?.ZONE_1 ?? zoneLabels.ZONE_1),
                ZONE_2: String(payload.zone_labels?.ZONE_2 ?? zoneLabels.ZONE_2),
                ZONE_3: String(payload.zone_labels?.ZONE_3 ?? zoneLabels.ZONE_3),
            })
            setGlobalMessage('Global zone settings updated.')
        } catch (err) {
            console.error(err)
            setGlobalError('Network error saving global zone settings')
        } finally {
            setGlobalSaving(false)
        }
    }

    return (
        <div className="dashboard-container">
            <header className="dashboard-header">
                <div className="brand-head">
                    <img
                        src="/logo_icon_stylized.png"
                        alt="AADI logo"
                        className="brand-logo"
                    />
                    <div>
                        <h1>AADI Admin</h1>
                        <p className="brand-subline">Platform administration</p>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <span style={{ color: 'rgba(255,255,255,0.92)' }}>Welcome, Super Admin</span>
                    <button onClick={signOut} className="btn btn-secondary">Sign Out</button>
                </div>
            </header>

            <div className="main-content">
                <div style={{
                    background: '#ffffff',
                    borderRadius: '12px',
                    border: '1px solid #e5e7eb',
                    padding: '1rem',
                    marginBottom: '1.5rem'
                }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                        <h2 className="panel-subheader" style={{ margin: 0 }}>Global Arrival Zones</h2>
                        <button
                            onClick={saveGlobalZones}
                            className="btn btn-primary"
                            disabled={globalSaving || !token}
                        >
                            {globalSaving ? 'Saving...' : 'Save Zone Settings'}
                        </button>
                    </div>
                    <p style={{ margin: '0.5rem 0 1rem', color: '#4b5563' }}>
                        Zone labels and distances apply to all restaurants. Restaurant admins choose which zone triggers Pending → Incoming.
                    </p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem' }}>
                        {(['ZONE_1', 'ZONE_2', 'ZONE_3'] as ZoneKey[]).map((zone) => (
                            <div key={zone} style={{ display: 'grid', gap: '0.35rem', border: '1px solid #e5e7eb', borderRadius: '8px', padding: '0.65rem' }}>
                                <span style={{ fontWeight: 600 }}>{zone}</span>
                                <label style={{ display: 'grid', gap: '0.35rem' }}>
                                    <span style={{ color: '#374151', fontSize: '0.85rem' }}>Label</span>
                                    <input
                                        type="text"
                                        value={zoneLabels[zone]}
                                        onChange={(e) => updateZoneLabel(zone, e.target.value)}
                                        style={{ padding: '0.5rem', border: '1px solid #d1d5db', borderRadius: '6px' }}
                                    />
                                </label>
                                <label style={{ display: 'grid', gap: '0.35rem' }}>
                                    <span style={{ color: '#374151', fontSize: '0.85rem' }}>Distance (m)</span>
                                    <input
                                        type="number"
                                        min={10}
                                        value={zoneDistances[zone]}
                                        onChange={(e) => updateZoneDistance(zone, e.target.value)}
                                        style={{ padding: '0.5rem', border: '1px solid #d1d5db', borderRadius: '6px' }}
                                    />
                                </label>
                            </div>
                        ))}
                    </div>
                    {globalError && <div style={{ color: '#b91c1c', marginTop: '0.75rem' }}>{globalError}</div>}
                    {globalMessage && <div style={{ color: '#15803d', marginTop: '0.75rem' }}>{globalMessage}</div>}
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
                    <h2 className="panel-subheader">Restaurants</h2>
                    <button onClick={() => setShowAddModal(true)} className="btn btn-primary">
                        + Add Restaurant
                    </button>
                </div>

                {loading ? <p>Loading...</p> : (
                    <table className="admin-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Address</th>
                                <th>Admin Email</th>
                                <th>Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {restaurants.map(r => (
                                <tr key={r.restaurant_id}>
                                    <td>{r.name}</td>
                                    <td>
                                        {r.address}
                                        {r.location && <div style={{ fontSize: '0.8em', color: '#666' }}>
                                            📍 {parseFloat(r.location.lat).toFixed(4)}, {parseFloat(r.location.lon).toFixed(4)}
                                        </div>}
                                    </td>
                                    <td>{r.contact_email}</td>
                                    <td>
                                        <span className={`status-badge ${r.active ? 'active' : 'inactive'}`}>
                                            {r.active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td>
                                        <button
                                            onClick={() => setEditingRestaurant(r)}
                                            className="btn btn-small"
                                            style={{ marginRight: '0.5rem' }}
                                        >
                                            Edit
                                        </button>
                                        {!r.active ? (
                                            <button
                                                onClick={() => handleToggleStatus(r.restaurant_id, true)}
                                                className="btn btn-small btn-activate"
                                                style={{ marginRight: '0.5rem' }}
                                            >
                                                Activate
                                            </button>
                                        ) : (
                                            <button
                                                onClick={() => handleToggleStatus(r.restaurant_id, false)}
                                                className="btn btn-small btn-deactivate"
                                                style={{ marginRight: '0.5rem' }}
                                            >
                                                Deactivate
                                            </button>
                                        )}
                                        <button
                                            onClick={() => handleDelete(r.restaurant_id)}
                                            className="btn btn-small btn-danger"
                                        >
                                            Delete
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            {showAddModal && token && (
                <RestaurantForm
                    token={token}
                    onSuccess={() => { setShowAddModal(false); if (token) fetchRestaurants(token); }}
                    onCancel={() => setShowAddModal(false)}
                />
            )}

            {editingRestaurant && (
                <EditRestaurantModal
                    token={token}
                    restaurant={editingRestaurant}
                    onSave={handleUpdate}
                    onCancel={() => setEditingRestaurant(null)}
                />
            )}
        </div>
    )
}

function EditRestaurantModal({
    token,
    restaurant,
    onSave,
    onCancel,
}: {
    token: string | null,
    restaurant: any,
    onSave: (data: any) => void,
    onCancel: () => void
}) {
    const [name, setName] = useState(restaurant.name)
    const [cuisine, setCuisine] = useState(restaurant.cuisine || '')
    const [tagsInput, setTagsInput] = useState(Array.isArray(restaurant.tags) ? restaurant.tags.join(', ') : '')
    const [priceTier, setPriceTier] = useState(Number(restaurant.price_tier) || 2)
    const [street, setStreet] = useState(restaurant.street || '')
    const [city, setCity] = useState(restaurant.city || '')
    const [state, setState] = useState(restaurant.state || '')
    const [zip, setZip] = useState(restaurant.zip || '')
    const [hours, setHours] = useState(restaurant.operating_hours || '9:00-22:00')
    const [restaurantImageKeys, setRestaurantImageKeys] = useState<string[]>(
        Array.isArray(restaurant.restaurant_image_keys) ? restaurant.restaurant_image_keys : []
    )

    // Parse legacy full address if structured fields are missing
    useEffect(() => {
        if (!restaurant.street && restaurant.address) {
            // Very basic fallback parsing, or just leave empty and let user fill
            setStreet(restaurant.address)
        }
        setRestaurantImageKeys(Array.isArray(restaurant.restaurant_image_keys) ? restaurant.restaurant_image_keys : [])
    }, [restaurant])

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        const tags = tagsInput
            .split(',')
            .map((tag: string) => tag.trim())
            .filter(Boolean)

        onSave({
            name,
            cuisine: cuisine.trim() || 'Other',
            tags,
            price_tier: priceTier,
            street,
            city,
            state,
            zip,
            operating_hours: hours,
            contact_email: restaurant.contact_email, // Send back original email (immutable)
            restaurant_image_keys: restaurantImageKeys,
        })
    }

    return (
        <div className="modal-overlay">
            <div className="modal">
                <h2>Edit Restaurant</h2>
                <form onSubmit={handleSubmit}>
                    <div className="form-group">
                        <label>Name</label>
                        <input value={name} onChange={e => setName(e.target.value)} required />
                    </div>

                    <div className="form-row" style={{ display: 'flex', gap: '1rem' }}>
                        <div className="form-group" style={{ flex: 1 }}>
                            <label>Cuisine</label>
                            <input
                                value={cuisine}
                                onChange={e => setCuisine(e.target.value)}
                                placeholder="Indian, Pizza, Burgers..."
                            />
                        </div>
                        <div className="form-group" style={{ flex: 2 }}>
                            <label>Tags (comma separated)</label>
                            <input
                                value={tagsInput}
                                onChange={e => setTagsInput(e.target.value)}
                                placeholder="vegan, spicy, family-friendly"
                            />
                        </div>
                        <div className="form-group" style={{ flex: 1 }}>
                            <label>Price Tier</label>
                            <select
                                value={priceTier}
                                onChange={e => setPriceTier(Number(e.target.value))}
                            >
                                <option value={1}>$</option>
                                <option value={2}>$$</option>
                                <option value={3}>$$$</option>
                                <option value={4}>$$$$</option>
                            </select>
                        </div>
                    </div>

                    <div className="form-group">
                        <label>Street Address</label>
                        <input value={street} onChange={e => setStreet(e.target.value)} required />
                    </div>

                    <div className="form-row" style={{ display: 'flex', gap: '1rem' }}>
                        <div className="form-group" style={{ flex: 2 }}>
                            <label>City</label>
                            <input value={city} onChange={e => setCity(e.target.value)} required />
                        </div>
                        <div className="form-group" style={{ flex: 1 }}>
                            <label>State</label>
                            <input value={state} onChange={e => setState(e.target.value)} required />
                        </div>
                        <div className="form-group" style={{ flex: 1 }}>
                            <label>Zip</label>
                            <input value={zip} onChange={e => setZip(e.target.value)} required />
                        </div>
                    </div>

                    <div className="form-group">
                        <label>Contact Email (Read Only)</label>
                        <input value={restaurant.contact_email} disabled style={{ background: '#f3f4f6', cursor: 'not-allowed' }} />
                        <small>Email updates are disabled to maintain account integrity.</small>
                    </div>

                    <div className="form-group">
                        <label>Operating Hours</label>
                        <input value={hours} onChange={e => setHours(e.target.value)} />
                    </div>

                    <RestaurantImageManager
                        token={token}
                        restaurantId={restaurant.restaurant_id}
                        initialImageKeys={Array.isArray(restaurant.restaurant_image_keys) ? restaurant.restaurant_image_keys : []}
                        initialImageUrls={Array.isArray(restaurant.restaurant_images) ? restaurant.restaurant_images : []}
                        onKeysChange={setRestaurantImageKeys}
                    />

                    <div className="form-actions">
                        <button type="button" onClick={onCancel} className="btn btn-secondary">Cancel</button>
                        <button type="submit" className="btn btn-primary">Save Changes</button>
                    </div>
                </form>
            </div>
            <style>{`
                /* Reuse existing modal styles from RestaurantForm */
                .modal-overlay {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(0,0,0,0.5);
                    display: flex;
                    justify-content: center;
                    align-items: flex-start;
                    overflow-y: auto;
                    padding: 2rem 1rem;
                    z-index: 1000;
                }
                .modal {
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    min-width: 500px;
                    width: min(960px, 100%);
                    max-height: calc(100vh - 4rem);
                    overflow-y: auto;
                    color: #333;
                }
                .form-group { margin-bottom: 1rem; }
                .form-group label { display: block; margin-bottom: 0.5rem; font-weight: bold; }
                .form-group input { width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
                .form-group select { width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; background: white; }
                .form-actions { display: flex; justify-content: flex-end; gap: 1rem; margin-top: 1.5rem; }
                @media (max-width: 700px) {
                    .modal {
                        min-width: 0;
                    }
                }
            `}</style>
        </div>
    )
}
