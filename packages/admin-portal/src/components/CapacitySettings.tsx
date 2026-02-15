import { useState, useEffect } from 'react'
import { API_BASE_URL } from '../aws-exports'

interface CapacityConfig {
    max_concurrent_orders: number;
    capacity_window_seconds: number;
}

interface CapacitySettingsProps {
    restaurantId: string;
    token: string;
    onClose: () => void;
}

export default function CapacitySettings({ restaurantId, token, onClose }: CapacitySettingsProps) {
    const [config, setConfig] = useState<CapacityConfig>({ max_concurrent_orders: 10, capacity_window_seconds: 300 })
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [message, setMessage] = useState<string | null>(null)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        fetchConfig()
    }, [restaurantId])

    async function fetchConfig() {
        setLoading(true)
        try {
            const res = await fetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}/config`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
            if (res.ok) {
                const data = await res.json()
                setConfig({
                    max_concurrent_orders: data.max_concurrent_orders,
                    capacity_window_seconds: data.capacity_window_seconds
                })
            } else {
                setError("Failed to load settings")
            }
        } catch (err) {
            setError("Network error loading settings")
        } finally {
            setLoading(false)
        }
    }

    async function handleSave() {
        setSaving(true)
        setMessage(null)
        setError(null)
        try {
            const res = await fetch(`${API_BASE_URL}/v1/restaurants/${restaurantId}/config`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            })

            if (res.ok) {
                setMessage("Settings saved successfully!")
                setTimeout(onClose, 1500)
            } else {
                const errData = await res.json()
                setError(errData.error || "Failed to save settings")
            }
        } catch (err) {
            setError("Network error saving settings")
        } finally {
            setSaving(false)
        }
    }

    if (loading) return <div className="p-4">Loading settings...</div>

    return (
        <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000
        }}>
            <div style={{ background: 'white', padding: '2rem', borderRadius: '8px', width: '400px', maxWidth: '90%' }}>
                <h2 style={{ marginTop: 0 }}>Capacity Settings</h2>

                {error && <div style={{ color: 'red', marginBottom: '1rem' }}>{error}</div>}
                {message && <div style={{ color: 'green', marginBottom: '1rem' }}>{message}</div>}

                <div style={{ marginBottom: '1rem' }}>
                    <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '0.5rem' }}>
                        Max Concurrent Orders
                    </label>
                    <input
                        type="number"
                        value={config.max_concurrent_orders}
                        onChange={(e) => setConfig({ ...config, max_concurrent_orders: parseInt(e.target.value) || 0 })}
                        style={{ width: '100%', padding: '0.5rem', border: '1px solid #ccc', borderRadius: '4px' }}
                    />
                    <small style={{ color: '#666' }}>
                        Maximum active orders allowed in a window.
                    </small>
                </div>

                <div style={{ marginBottom: '1rem' }}>
                    <label style={{ display: 'block', fontWeight: 'bold', marginBottom: '0.5rem' }}>
                        Window Size (Seconds)
                    </label>
                    <select
                        value={config.capacity_window_seconds}
                        onChange={(e) => setConfig({ ...config, capacity_window_seconds: parseInt(e.target.value) })}
                        style={{ width: '100%', padding: '0.5rem', border: '1px solid #ccc', borderRadius: '4px' }}
                    >
                        <option value={300}>5 Minutes (300s)</option>
                        <option value={600}>10 Minutes (600s)</option>
                        <option value={900}>15 Minutes (900s)</option>
                        <option value={1800}>30 Minutes (1800s)</option>
                    </select>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '2rem' }}>
                    <button
                        onClick={onClose}
                        disabled={saving}
                        className="btn btn-secondary"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="btn btn-primary"
                    >
                        {saving ? 'Saving...' : 'Save Changes'}
                    </button>
                </div>
            </div>
        </div>
    )
}
