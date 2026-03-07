import { useState, useEffect } from 'react'
import * as api from '../services/api'

interface PosConnection {
    connection_id: string;
    label: string;
    provider: string;
    webhook_url: string;
    webhook_secret: string;
    enabled: boolean;
    created_at?: number;
}

interface PosSettingsProps {
    restaurantId: string;
    onClose: () => void;
}

const PROVIDERS = [
    { value: 'square', label: '🟦 Square' },
    { value: 'toast', label: '🍞 Toast' },
    { value: 'clover', label: '🍀 Clover' },
    { value: 'custom', label: '🔧 Custom' },
]

const providerIcon = (p: string) =>
    PROVIDERS.find(pr => pr.value === p)?.label?.split(' ')[0] || '🔌'

export default function PosSettings({ restaurantId, onClose }: PosSettingsProps) {
    const [posEnabled, setPosEnabled] = useState(false)
    const [connections, setConnections] = useState<PosConnection[]>([])
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [message, setMessage] = useState<string | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [showAdd, setShowAdd] = useState(false)

    // New connection form state
    const [newLabel, setNewLabel] = useState('')
    const [newProvider, setNewProvider] = useState('custom')
    const [newUrl, setNewUrl] = useState('')
    const [newSecret, setNewSecret] = useState('')

    useEffect(() => { fetchConfig() }, [restaurantId])

    async function fetchConfig() {
        setLoading(true)
        try {
            const data = await api.fetchRestaurantConfig(restaurantId)
            setPosEnabled((data.pos_enabled as boolean) ?? false)
            setConnections((data.pos_connections as PosConnection[]) ?? [])
        } catch {
            setError('Failed to load POS settings')
        } finally {
            setLoading(false)
        }
    }

    async function handleSave(updatedConnections?: PosConnection[], updatedEnabled?: boolean) {
        if (saving) return
        setSaving(true)
        setMessage(null)
        setError(null)
        try {
            await api.updateRestaurantConfig(restaurantId, {
                pos_enabled: updatedEnabled ?? posEnabled,
                pos_connections: updatedConnections ?? connections,
            })
            setMessage('POS settings saved!')
            // Re-fetch to get masked secrets from server
            await fetchConfig()
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to save')
        } finally {
            setSaving(false)
        }
    }

    function handleAddConnection() {
        if (!newUrl.startsWith('https://')) {
            setError('Webhook URL must use HTTPS')
            return
        }
        if (connections.length >= 5) {
            setError('Maximum 5 POS connections allowed')
            return
        }

        const newConn: PosConnection = {
            connection_id: '', // Server will assign
            label: newLabel || `${newProvider.charAt(0).toUpperCase() + newProvider.slice(1)} POS`,
            provider: newProvider,
            webhook_url: newUrl,
            webhook_secret: newSecret,
            enabled: true,
        }
        const updated = [...connections, newConn]
        setConnections(updated)
        handleSave(updated)
        setShowAdd(false)
        setNewLabel('')
        setNewProvider('custom')
        setNewUrl('')
        setNewSecret('')
    }

    function handleRemove(idx: number) {
        const updated = connections.filter((_, i) => i !== idx)
        setConnections(updated)
        handleSave(updated)
    }

    function handleToggleConnection(idx: number) {
        const updated = connections.map((c, i) =>
            i === idx ? { ...c, enabled: !c.enabled } : c
        )
        setConnections(updated)
        handleSave(updated)
    }

    function handleToggleGlobal() {
        const next = !posEnabled
        setPosEnabled(next)
        handleSave(undefined, next)
    }

    if (loading) return <div style={overlayStyle}><div style={modalStyle}><p>Loading POS settings...</p></div></div>

    return (
        <div style={overlayStyle}>
            <div style={{ ...modalStyle, maxHeight: '80vh', overflowY: 'auto' }}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                    <h2 style={{ margin: 0 }}>🔌 POS Integrations</h2>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontSize: '0.9rem', color: posEnabled ? '#16a34a' : '#9ca3af' }}>
                            {posEnabled ? 'Enabled' : 'Disabled'}
                        </span>
                        <button
                            onClick={handleToggleGlobal}
                            disabled={saving}
                            style={{
                                ...toggleStyle,
                                background: posEnabled ? '#16a34a' : '#d1d5db',
                            }}
                        >
                            <span style={{
                                ...toggleKnob,
                                transform: posEnabled ? 'translateX(20px)' : 'translateX(0)',
                            }} />
                        </button>
                    </div>
                </div>

                {error && <div style={{ color: '#dc2626', background: '#fef2f2', padding: '0.75rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.9rem' }}>{error}</div>}
                {message && <div style={{ color: '#16a34a', background: '#f0fdf4', padding: '0.75rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.9rem' }}>{message}</div>}

                {/* Connections List */}
                {connections.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '2rem', color: '#9ca3af' }}>
                        <p style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>🔗</p>
                        <p>No POS connections yet.</p>
                        <p style={{ fontSize: '0.85rem' }}>Add a connection to start pushing orders to your POS system.</p>
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1rem' }}>
                        {connections.map((conn, idx) => (
                            <div key={conn.connection_id || idx} style={connCardStyle}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flex: 1, minWidth: 0 }}>
                                    <span style={{ fontSize: '1.5rem' }}>{providerIcon(conn.provider)}</span>
                                    <div style={{ minWidth: 0 }}>
                                        <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
                                            {conn.label}
                                        </div>
                                        <div style={{ fontSize: '0.8rem', color: '#6b7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>
                                            {conn.webhook_url}
                                        </div>
                                        <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '2px' }}>
                                            Secret: <code style={{ background: '#f3f4f6', padding: '1px 4px', borderRadius: '3px' }}>{conn.webhook_secret}</code>
                                        </div>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
                                    <button
                                        onClick={() => handleToggleConnection(idx)}
                                        disabled={saving}
                                        style={{
                                            ...toggleStyle,
                                            width: '36px', height: '20px',
                                            background: conn.enabled ? '#16a34a' : '#d1d5db',
                                        }}
                                    >
                                        <span style={{
                                            ...toggleKnob,
                                            width: '16px', height: '16px',
                                            transform: conn.enabled ? 'translateX(16px)' : 'translateX(0)',
                                        }} />
                                    </button>
                                    <button
                                        onClick={() => handleRemove(idx)}
                                        disabled={saving}
                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', fontSize: '1.1rem', padding: '4px' }}
                                        title="Remove connection"
                                    >
                                        🗑️
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Add Connection Form */}
                {showAdd ? (
                    <div style={{ border: '1px solid #e5e7eb', borderRadius: '8px', padding: '1rem', marginBottom: '1rem', background: '#fafafa' }}>
                        <h4 style={{ margin: '0 0 1rem 0' }}>New POS Connection</h4>

                        <div style={fieldStyle}>
                            <label style={labelStyle}>Provider</label>
                            <select value={newProvider} onChange={e => setNewProvider(e.target.value)} style={inputStyle}>
                                {PROVIDERS.map(p => (
                                    <option key={p.value} value={p.value}>{p.label}</option>
                                ))}
                            </select>
                        </div>

                        <div style={fieldStyle}>
                            <label style={labelStyle}>Label</label>
                            <input
                                type="text"
                                value={newLabel}
                                onChange={e => setNewLabel(e.target.value)}
                                placeholder="e.g. Square - Dine In"
                                style={inputStyle}
                            />
                        </div>

                        <div style={fieldStyle}>
                            <label style={labelStyle}>Webhook URL</label>
                            <input
                                type="url"
                                value={newUrl}
                                onChange={e => setNewUrl(e.target.value)}
                                placeholder="https://..."
                                style={inputStyle}
                            />
                            <small style={{ color: '#6b7280' }}>Must use HTTPS</small>
                        </div>

                        <div style={fieldStyle}>
                            <label style={labelStyle}>Webhook Secret</label>
                            <input
                                type="password"
                                value={newSecret}
                                onChange={e => setNewSecret(e.target.value)}
                                placeholder="whsec_..."
                                style={inputStyle}
                            />
                            <small style={{ color: '#6b7280' }}>Used for HMAC-SHA256 signature verification</small>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
                            <button onClick={() => setShowAdd(false)} className="btn btn-secondary" style={{ padding: '0.4rem 1rem' }}>Cancel</button>
                            <button onClick={handleAddConnection} disabled={saving || !newUrl} className="btn btn-primary" style={{ padding: '0.4rem 1rem' }}>
                                {saving ? 'Adding...' : 'Add Connection'}
                            </button>
                        </div>
                    </div>
                ) : (
                    <button
                        onClick={() => { setShowAdd(true); setError(null); setMessage(null) }}
                        className="btn btn-secondary"
                        disabled={connections.length >= 5}
                        style={{ width: '100%', padding: '0.6rem', marginBottom: '1rem' }}
                    >
                        + Add POS Connection {connections.length >= 5 && '(max reached)'}
                    </button>
                )}

                {/* Footer */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.5rem' }}>
                    <button onClick={onClose} className="btn btn-secondary">Close</button>
                </div>
            </div>
        </div>
    )
}

// ── Shared Styles ──
const overlayStyle: React.CSSProperties = {
    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
    background: 'rgba(0,0,0,0.5)', display: 'flex',
    alignItems: 'center', justifyContent: 'center', zIndex: 1000,
}
const modalStyle: React.CSSProperties = {
    background: 'white', padding: '2rem', borderRadius: '12px',
    width: '520px', maxWidth: '95%',
    boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
}
const toggleStyle: React.CSSProperties = {
    width: '44px', height: '24px', borderRadius: '12px', border: 'none',
    cursor: 'pointer', position: 'relative', transition: 'background 0.2s',
    padding: 0,
}
const toggleKnob: React.CSSProperties = {
    position: 'absolute', top: '2px', left: '2px',
    width: '20px', height: '20px', borderRadius: '50%',
    background: 'white', boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
    transition: 'transform 0.2s',
}
const connCardStyle: React.CSSProperties = {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '0.75rem 1rem', border: '1px solid #e5e7eb', borderRadius: '8px',
    background: '#fafafa',
}
const fieldStyle: React.CSSProperties = { marginBottom: '0.75rem' }
const labelStyle: React.CSSProperties = { display: 'block', fontWeight: 600, marginBottom: '0.3rem', fontSize: '0.9rem' }
const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem', border: '1px solid #d1d5db',
    borderRadius: '6px', fontSize: '0.9rem', boxSizing: 'border-box',
}
