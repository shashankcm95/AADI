import { useState } from 'react'
import { API_BASE_URL } from '../aws-exports'

interface RestaurantFormProps {
    token: string | null;
    onSuccess: () => void;
    onCancel: () => void;
}

export default function RestaurantForm({ token, onSuccess, onCancel }: RestaurantFormProps) {
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
            const res = await fetch(`${API_BASE_URL}/v1/restaurants`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    name,
                    street,
                    city,
                    state,
                    zip,
                    contact_email: email,
                    operating_hours: hours,
                    cuisine: cuisine.trim() || 'Other',
                    tags,
                    price_tier: priceTier
                })
            })

            if (res.status === 409) {
                const data = await res.json()
                throw new Error(data.error || 'User already exists.')
            }

            if (!res.ok) {
                throw new Error(`Failed to create restaurant: ${res.statusText}`)
            }

            const data = await res.json()
            setUserStatus(data.user_status || 'CREATED') // Default to CREATED for backward compatibility
            setSuccessMsg(true)
        } catch (err: any) {
            setError(err.message)
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

            <style>{`
        .modal-overlay {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0,0,0,0.5);
          display: flex;
          justify-content: center;
          align-items: center;
          z-index: 1000;
        }
        .modal {
          background: white;
          padding: 2rem;
          border-radius: 8px;
          min-width: 400px;
          color: #333;
        }
        .form-group {
          margin-bottom: 1rem;
        }
        .form-group label {
          display: block;
          margin-bottom: 0.5rem;
          font-weight: bold;
        }
        .form-group input {
          width: 100%;
          padding: 0.5rem;
          border: 1px solid #ccc;
          border-radius: 4px;
        }
        .form-group select {
          width: 100%;
          padding: 0.5rem;
          border: 1px solid #ccc;
          border-radius: 4px;
          background: white;
        }
        .form-actions {
          display: flex;
          justify-content: flex-end;
          gap: 1rem;
          margin-top: 1.5rem;
        }
        .error-banner {
          background: #fee2e2;
          color: #dc2626;
          padding: 0.75rem;
          border-radius: 4px;
          margin-bottom: 1rem;
        }
      `}</style>
        </div>
    )
}
