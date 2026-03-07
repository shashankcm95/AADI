import { useState } from 'react'
import * as api from '../services/api'

interface RestaurantFormProps {
    onSuccess: () => void;
    onCancel: () => void;
}

export default function RestaurantForm({ onSuccess, onCancel }: RestaurantFormProps) {
    const [name, setName] = useState('')
    const [cuisine, setCuisine] = useState('')
    const [tagsInput, setTagsInput] = useState('')
    const [priceTier, setPriceTier] = useState(2)
    const [street, setStreet] = useState('')
    const [city, setCity] = useState('')
    const [state, setState] = useState('')
    const [zip, setZip] = useState('')
    const [email, setEmail] = useState('')
    const [hours, setHours] = useState('9:00-22:00')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [successMsg, setSuccessMsg] = useState(false)
    const [userStatus, setUserStatus] = useState<'CREATED' | 'LINKED' | null>(null)

    async function handleSubmit(e: React.FormEvent) {
        e.preventDefault()
        setLoading(true)
        setError(null)

        const tags = tagsInput
            .split(',')
            .map(tag => tag.trim())
            .filter(Boolean)

        try {
            const data = await api.createRestaurant({
                name,
                street,
                city,
                state,
                zip,
                contact_email: email,
                operating_hours: hours,
                cuisine: cuisine.trim() || 'Other',
                tags,
                price_tier: priceTier,
            })
            setUserStatus((data.user_status as 'CREATED' | 'LINKED') || 'CREATED')
            setSuccessMsg(true)
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to create restaurant')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="modal-overlay">
            <div className="modal">
                <h2>Add New Restaurant</h2>
                {error && <div className="error-banner">{error}</div>}

                <form onSubmit={handleSubmit}>
                    {successMsg ? (
                        <div className="success-message" style={{ textAlign: 'center', padding: '2rem 0' }}>
                            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🎉</div>
                            <h3>Restaurant Created!</h3>
                            {userStatus === 'CREATED' ? (
                                <p>An invitation email has been sent to <strong>{email}</strong>.</p>
                            ) : (
                                <div style={{ background: '#fffbeb', padding: '1rem', borderRadius: '4px', border: '1px solid #fcd34d', margin: '1rem 0', textAlign: 'left' }}>
                                    <p><strong>Note:</strong> The email <strong>{email}</strong> is already registered.</p>
                                    <p style={{ marginTop: '0.5rem', fontSize: '0.9em' }}>
                                        We have linked this new restaurant to their existing account.
                                        They can simply log in with their current password to manage it.
                                        <br />
                                        <em>No new invitation email was sent.</em>
                                    </p>
                                </div>
                            )}
                            <button
                                type="button"
                                onClick={onSuccess}
                                className="btn btn-primary"
                                style={{ marginTop: '1rem' }}
                            >
                                Close
                            </button>
                        </div>
                    ) : (
                        <>
                            <div className="form-group">
                                <label>Name</label>
                                <input
                                    value={name}
                                    onChange={e => setName(e.target.value)}
                                    required
                                    placeholder="Restaurant Name"
                                />
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
                                    <small style={{ color: '#666' }}>
                                        Used by customer search and discovery.
                                    </small>
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
                                <input
                                    value={street}
                                    onChange={e => setStreet(e.target.value)}
                                    placeholder="123 Main St"
                                />
                            </div>

                            <div className="form-row" style={{ display: 'flex', gap: '1rem' }}>
                                <div className="form-group" style={{ flex: 2 }}>
                                    <label>City</label>
                                    <input
                                        value={city}
                                        onChange={e => setCity(e.target.value)}
                                        placeholder="City"
                                    />
                                </div>
                                <div className="form-group" style={{ flex: 1 }}>
                                    <label>State</label>
                                    <input
                                        value={state}
                                        onChange={e => setState(e.target.value)}
                                        placeholder="State"
                                    />
                                </div>
                                <div className="form-group" style={{ flex: 1 }}>
                                    <label>Zip</label>
                                    <input
                                        value={zip}
                                        onChange={e => setZip(e.target.value)}
                                        placeholder="Zip"
                                    />
                                </div>
                            </div>

                            <div className="form-group">
                                <label>Contact Email (for Admin Invite)</label>
                                <input
                                    type="email"
                                    value={email}
                                    onChange={e => setEmail(e.target.value)}
                                    required
                                    placeholder="manager@example.com"
                                />
                                <small style={{ color: '#666' }}>
                                    We will send a temporary password to this email.
                                </small>
                            </div>

                            <div className="form-group">
                                <label>Operating Hours</label>
                                <input
                                    value={hours}
                                    onChange={e => setHours(e.target.value)}
                                    placeholder="9:00-22:00"
                                />
                                <small style={{ color: '#666' }}>
                                    After creation, upload up to 5 restaurant images from the Edit or Images panel.
                                </small>
                            </div>

                            <div className="form-actions">
                                <button type="button" onClick={onCancel} className="btn btn-secondary">Cancel</button>
                                <button type="submit" className="btn btn-primary" disabled={loading}>
                                    {loading ? 'Creating...' : 'Create Restaurant'}
                                </button>
                            </div>
                        </>
                    )}
                </form>
            </div>
        </div>
    )
}
